import os
import time
import logging
from typing import List
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate

from app.config.qwen import create_qwen_chat_model, get_qwen_chat_model_name

logger = logging.getLogger(__name__)

class QAGenerator:
    def __init__(self, model_name=None, tier: str = "turbo"):
        """
        初始化 Qwen 大模型调用。

        参数:
            model_name: 直接指定模型名（优先于 tier）
            tier: 档位选择 "turbo" / "plus" / "max"，默认 "turbo"
        """
        if tier not in {"turbo", "plus", "max"}:
            raise ValueError(f"不支持的 Qwen 模型档位: {tier}")
        actual_model = model_name or get_qwen_chat_model_name(tier)
        logger.info(f"🔑 [QAGenerator] 使用 Qwen 模型: {actual_model}")

        self.llm = create_qwen_chat_model(
            tier,
            model_name=model_name,
            max_retries=2,
            request_timeout=60,
        )
        self.prompt = ChatPromptTemplate.from_template(
            "你是一个专业的医学助理。请阅读以下由多个连续医学文档片段组合而成的长文本，提取出其中最重要的关联信息，生成3到5个高质量的问答对(Q&A)。\n"
            "这能够帮助建立倒排检索的向量库。\n\n"
            "输出格式要求，请严格按照：\n"
            "Q: [问题1]\n"
            "A: [答案1]\n\n"
            "Q: [问题2]\n"
            "A: [答案2]\n\n"
            "文档片段集合：\n{text}"
        )
        self.chain = self.prompt | self.llm

    def generate_qa_for_chunks(self, chunks: List[Document], batch_size: int = 10) -> List[Document]:
        """
        将多个 chunk 合并打批传给大模型生成 QA，从而大幅节省接口请求次数并提升速度。

        内置批次间延迟，防止短时间内大量请求触发百炼并发限制。
        """
        qa_docs = []
        total_chunks = len(chunks)
        total_batches = (total_chunks + batch_size - 1) // batch_size

        _BATCH_DELAY = float(os.getenv("QA_BATCH_DELAY_SEC", "0.5"))

        logger.info(f"🧠 开始为 {total_chunks} 个 chunk 生成 QA 对")
        logger.info(f"   批次大小: {batch_size} | 总批次数: {total_batches} | 批次延迟: {_BATCH_DELAY}s")
        logger.info(f"{'─' * 50}")

        start_time = time.time()

        for i in range(0, total_chunks, batch_size):
            batch_chunks = chunks[i:i + batch_size]
            batch_num = i // batch_size + 1

            # 将这 N 个片段合并为一段大文本交由大模型一次性处理
            combined_text = "\n\n--- 片段分隔 ---\n\n".join([c.page_content for c in batch_chunks])

            # 诊断：记录合并后文本长度，方便排查是否因超长导致超时
            logger.debug(f"  批次 {batch_num}: 合并 {len(batch_chunks)} 个 chunk，总长度 {len(combined_text)} 字符")

            # 使用集合去重这批 chunk 的来源与页码信息
            sources = list(set([c.metadata.get("source", "未知") for c in batch_chunks]))
            pages = list(set([str(c.metadata.get("page", "")) for c in batch_chunks]))

            merged_meta = {
                "source": ", ".join(sources),
                "page": ", ".join(pages),
                "doc_type": "qa_generated_batch",
                "original_chunk_count": len(batch_chunks)
            }

            try:
                response = self.chain.invoke({"text": combined_text})
                qa_content = response.content.strip()

                # 若生成的文本为空或者非常短则跳过
                if len(qa_content) < 10:
                    logger.warning(f"  ⚠️ 批次 {batch_num} 生成内容过短（{len(qa_content)} 字符），跳过")
                else:
                    qa_doc = Document(page_content=qa_content, metadata=merged_meta)
                    qa_docs.append(qa_doc)

                    # 每生成 5 个 QA 对或最后一批时，打印一次示例内容
                    if len(qa_docs) % 5 == 0 or batch_num == total_batches:
                        logger.info(f"  📝 批次 {batch_num} 生成的 QA 示例 (来源: {merged_meta['source']}):")
                        # 只打印前 200 字符作为预览
                        preview = qa_content[:200] + "..." if len(qa_content) > 200 else qa_content
                        logger.info(f"     {preview}")
                        logger.info(f"{'─' * 50}")

            except Exception as e:
                logger.error(f"❌ 生成 QA 失败 (批次 {batch_num}): {e}")

            # API 调用之后打印进度（带进度条、百分比、速度、ETA）
            current_processed = min(i + batch_size, total_chunks)
            elapsed = time.time() - start_time
            pct = current_processed / total_chunks * 100
            speed = current_processed / elapsed if elapsed > 0 else 0

            # ETA（预估剩余时间）
            if speed > 0:
                eta_sec = (total_chunks - current_processed) / speed
                eta_str = f"{eta_sec:.0f}s" if eta_sec < 120 else f"{eta_sec / 60:.1f}min"
            else:
                eta_str = "计算中..."

            # 简单进度条（20 格）
            bar_length = 20
            filled = int(bar_length * current_processed / total_chunks)
            bar = "█" * filled + "░" * (bar_length - filled)

            logger.info(
                f"  [{bar}] {pct:5.1f}% | 批次 {batch_num}/{total_batches} | "
                f"chunk {current_processed}/{total_chunks} | "
                f"耗时 {elapsed:.0f}s | 速度 {speed:.1f} chunk/s | ETA {eta_str}"
            )

            # 最后一批不需要延迟。
            if batch_num < total_batches and _BATCH_DELAY > 0:
                time.sleep(_BATCH_DELAY)

        total_elapsed = time.time() - start_time
        logger.info(f"✅ QA 生成完成！共 {len(qa_docs)} 个 QA 集合，总耗时 {total_elapsed:.1f}s")
        return qa_docs
