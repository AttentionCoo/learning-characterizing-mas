"""
RAGAS 评测对比：递归字符分块 vs 语义分块

评测指标:
  - Context Precision:   检索到的上下文有多少比例与问题相关
  - Context Recall:      标准答案所需信息是否都被检索到
  - Faithfulness:        生成的答案是否忠实于检索到的上下文
  - Answer Relevancy:    生成的答案与问题的相关程度

用法:
  python -m tests.compare_chunking          # 构建向量库 + 评测
  python -m tests.compare_chunking --skip-build  # 跳过构建，直接评测"""
import os
import sys
import json
import time
import logging
import argparse

# 修复 Windows GBK 终端无法打印 emoji 的问题
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from typing import List, Dict
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
from dotenv import load_dotenv
from datasets import Dataset
from langchain_openai import ChatOpenAI
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from openai import OpenAI

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.rag.data_loader import load_pdfs_from_dir, split_documents, clean_text_preserve_nl
from app.rag.retrievers import (
    QwenEmbeddings,
    QwenReranker,
    HybridRetriever,
    build_or_load_vectorstore,
    reciprocal_rank_fusion,
    CONFIG,
)

# RAGAS (0.4.x API: 兼容旧版 metrics 和 evaluate())
from ragas import evaluate, EvaluationDataset
from ragas.metrics import (
    context_precision,
    context_recall,
    faithfulness,
    answer_relevancy,
)

load_dotenv()

# 日志配置（降低第三方库日志级别，避免刷屏）
logging.basicConfig(
    level=logging.WARNING,  # 设为 WARNING，避免 DEBUG 噪音
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("compare_chunking")
logger.setLevel(logging.INFO)

# 路径配置（自动定位到项目根目录下的 data 和 chroma_db 目录）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data", "documents")

RECURSIVE_PERSIST = os.path.join(BASE_DIR, "chroma_db_recursive")
SEMANTIC_PERSIST = os.path.join(BASE_DIR, "chroma_db_semantic")

# 评测用 LLM 模型（通义千问 + RAGAS 评测）
EVAL_LLM_MODEL = "qwen-plus"
EMBEDDING_MODEL = "qwen3.7-text-embedding"

# 检索配置
SEARCH_TOP_K = 5  # 检索返回 5 个文档给 RAGAS 评测

# 测试问题集（基于医学知识库的常见问题）
# 每个条目包含 question, ground_truth，用于 RAGAS 评测
TEST_QUESTIONS = [
    {
        "question": "脑梗死后出血转化的主要危险因素有哪些？",
        "ground_truth": "主要危险因素包括：大面积脑梗死、心源性栓塞、高血糖、高血压、高龄、抗凝或抗血小板药物使用、NIHSS评分高等。CT低密度区大于1/3大脑中动脉供血区是重要预测指标。"
    },
    {
        "question": "急性脑梗死静脉溶栓的时间窗是多少？",
        "ground_truth": "标准静脉溶栓时间窗为发病4.5小时内。前循环大血管闭塞且符合DAWN/DEFUSE-3标准者可延长至24小时。时间窗内越早治疗预后越好，黄金时间为发病90分钟内。"
    },
    {
        "question": "急性脑梗死t-PA静脉溶栓的剂量和用法是什么？",
        "ground_truth": "t-PA剂量为0.9mg/kg（最大90mg），其中10%在1分钟内静脉推注，剩余90%在60分钟内持续静脉滴注。治疗期间需严密监测血压和神经功能变化。"
    },
    {
        "question": "急性大血管闭塞性脑梗死的血管内治疗适应症是什么？",
        "ground_truth": "适应症包括：前循环大血管闭塞（颈内动脉、M1/M2段）、发病24小时内、ASPECTS评分≥6分、NIHSS评分≥6分、CTA/MRA证实大血管闭塞、发病前mRS评分0-1分。后循环闭塞可放宽至24小时。"
    },
    {
        "question": "脑梗死急性期的血压管理目标是什么？",
        "ground_truth": "未接受溶栓/取栓的患者，若血压<220/120mmHg，发病24小时内一般不急于降压。拟行溶栓者需将血压控制在<185/110mmHg。溶栓后24小时内维持<180/105mmHg。取栓术后血压目标通常为<180/105mmHg。长期控制目标为<140/90mmHg。"
    },
    {
        "question": "静脉溶栓前的血压控制目标是什么？",
        "ground_truth": "溶栓前必须将血压控制在185/110mmHg以下，溶栓后24小时内维持在180/105mmHg以下。若血压持续高于目标值，应使用静脉降压药物（如拉贝洛尔、尼卡地平）控制。"
    },
    {
        "question": "NIHSS评分的临床意义和分级标准是什么？",
        "ground_truth": "NIHSS评分范围为0-42分，用于评估脑卒中神经功能缺损严重程度。0-1分基本正常，1-4分轻度卒中，5-15分中度卒中，15-20分中重度卒中，21-42分重度卒中。NIHSS评分≥6分提示大血管闭塞可能性大，需紧急行血管影像学检查。"
    },
    {
        "question": "急性脑梗死患者血糖管理目标是什么？",
        "ground_truth": "急性期血糖控制目标为7.8-10.0mmol/L。发病4-48小时内应避免低血糖（<3.3mmol/L）和严重高血糖（>10.0mmol/L）。高血糖与不良预后相关，但过于激进的降糖可能加重脑损伤。低血糖需立即纠正，静脉推注50%葡萄糖。"
    },
    {
        "question": "脑梗死二级预防的抗血小板治疗方案是什么？",
        "ground_truth": "非心源性脑梗死推荐抗血小板治疗：阿司匹林50-325mg/d或氯吡格雷75mg/d。轻型卒中（NIHSS≤4分）发病24小时内可启动双抗（阿司匹林+氯吡格雷）治疗21天，之后改为单药维持。心源性栓塞需抗凝治疗（华法林或新型口服抗凝药）。"
    },
    {
        "question": "脑梗死后出血转化的ECASS分型标准是什么？",
        "ground_truth": "ECASS分型将出血转化分为：HI-1（出血性脑梗死1型，沿梗死边缘小点状出血）、HI-2（出血性脑梗死2型，梗死区内融合点状出血但无占位效应）、PH-1（脑实质出血1型，血肿≤30%梗死区，轻度占位效应）、PH-2（脑实质出血2型，血肿>30%梗死区，明显占位效应或远离梗死区的出血）。"
    },
]


# 全局 DashScope 客户端（兼容 OpenAI-compatible 接口）
# 用于 RAGAS 评测时通过 LangchainEmbeddingsWrapper 直接调用
_dashscope_client = None


def _get_dashscope_client():
    """获取 OpenAI-compatible client，用于 RAGAS 调用 DashScope 评测"""
    global _dashscope_client
    if _dashscope_client is None:
        _dashscope_client = OpenAI(
            api_key=os.getenv("DASHSCOPE_API_KEY"),
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
    return _dashscope_client

def build_vectorstore(docs_dir: str, persist_dir: str, use_semantic: bool):
    """
    构建向量库，use_semantic=True 时使用语义分块，否则使用递归字符分块"""
    logger.info(f"\n{'='*60}")
    logger.info(f"Building vectorstore: {persist_dir}")
    logger.info(f"   Strategy: {'Semantic (0.80 + overlap)' if use_semantic else 'Recursive'}")
    logger.info(f"{'='*60}")

    # 加载文档（语义分块需要保留换行符以保持语义完整性）
    if use_semantic:
        raw_docs = load_pdfs_from_dir(docs_dir, clean_fn=clean_text_preserve_nl)
    else:
        raw_docs = load_pdfs_from_dir(docs_dir)
    logger.info(f"Loaded {len(raw_docs)} pages")

    # 分块
    if use_semantic:
        embeddings = QwenEmbeddings(model=EMBEDDING_MODEL)
        chunks = split_documents(
            raw_docs,
            embeddings=embeddings,
            similarity_threshold=0.80,   # 语义相似度阈值，越高分块越细
            min_chunk_size=100,
            max_chunk_size=800,
            overlap_ratio=0.25,           # 语义块重叠比例
            strategy="semantic",          # 语义分块策略
        )
    else:
        chunks = split_documents(raw_docs)  # 默认 hybrid（递归字符分块）

    logger.info(f"共切分为 {len(chunks)} 个块")

    # 构建/加载向量库（不生成 QA 数据集，仅用于检索评测）
    vectordb = build_or_load_vectorstore(
        chunks, persist_dir, enable_qa=False
    )

    # 创建混合检索器
    retriever = HybridRetriever(
        vectordb, raw_docs,
        recall_k=CONFIG.get("recall_k", 20),
        rrf_top_k=CONFIG.get("rrf_top_k", 20),
    )

    return retriever, chunks


def generate_answer(query: str, contexts: List[Document], llm) -> str:
    """基于检索到的上下文生成答案"""
    if not contexts:
        return "当前资料中未找到相关信息"

    context_text = "\n\n---\n\n".join(
        f"[来源: {d.metadata.get('source', '?')} p.{d.metadata.get('page', '?')}]\n{d.page_content}"
        for d in contexts
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", "你是一位循证医学教育专家。请严格基于以下参考资料回答问题。如果资料中找不到答案，请说明'当前资料中未找到相关信息'，不要编造。"),
        ("human", "参考资料：\n{context}\n\n问题：{question}\n\n请基于上述资料回答：")
    ])

    chain = prompt | llm
    response = chain.invoke({"context": context_text, "question": query})
    return response.content.strip()


def run_evaluation(
    retriever: HybridRetriever,
    llm,
    strategy_name: str,
) -> Dict:
    """
    对指定策略进行 RAGAS 评测，返回各项指标得分"""
    eval_data = []
    retrieval_times = []

    logger.info(f"\n>> [{strategy_name}] 开始评测...")

    for i, item in enumerate(TEST_QUESTIONS):
        question = item["question"]
        ground_truth = item["ground_truth"]

        # 检索
        t0 = time.time()
        contexts = retriever.search(question, top_k_final=SEARCH_TOP_K)
        retrieval_times.append(time.time() - t0)

        # 生成答案
        answer = generate_answer(question, contexts, llm)

        context_texts = [d.page_content for d in contexts]

        eval_data.append({
            "user_input": question,
            "response": answer,
            "retrieved_contexts": context_texts,
            "reference": ground_truth,
        })

        logger.info(f"  Q{i+1}: {question[:40]}... 检索{len(contexts)} contexts, {len(answer)} chars")

    # 构建 RAGAS Dataset
    hf_dataset = Dataset.from_list(eval_data)
    eval_dataset = EvaluationDataset.from_hf_dataset(hf_dataset)

    # RAGAS 评测
    # 使用 LangchainEmbeddingsWrapper 包装 QwenEmbeddings 以兼容 RAGAS
    # 也可用 ragas.embeddings.OpenAIEmbeddings 直接传 embed_query 参数
    logger.info(f">> [{strategy_name}] 执行 RAGAS 评测...")
    from ragas.embeddings import LangchainEmbeddingsWrapper

    ragas_emb = LangchainEmbeddingsWrapper(
        QwenEmbeddings(model=EMBEDDING_MODEL)
    )

    result = evaluate(
        dataset=eval_dataset,
        metrics=[
            context_precision,
            context_recall,
            faithfulness,
            answer_relevancy,
        ],
        llm=llm,
        embeddings=ragas_emb,
    )

    # 提取各项指标得分
    scores = {}
    metric_df = result.to_pandas()
    for metric_name in ["context_precision", "context_recall", "faithfulness", "answer_relevancy"]:
        if metric_name in metric_df.columns:
            values = [v for v in metric_df[metric_name].dropna().tolist() if v is not None]
            scores[metric_name] = float(np.mean(values)) if values else 0.0
        else:
            scores[metric_name] = 0.0

    scores["avg_retrieval_time_ms"] = float(np.mean(retrieval_times) * 1000)

    return scores


# ==================== 主流程：两种策略 A/B 对比 ====================
def main():
    parser = argparse.ArgumentParser(description="RAGAS 评测对比：递归分块 vs 语义分块")
    parser.add_argument("--skip-build", action="store_true",
                        help="跳过向量库构建（适用于已构建好的场景）")
    parser.add_argument("--force-rebuild", action="store_true",
                        help="强制重新构建向量库（删除旧数据）")
    parser.add_argument("--output", type=str, default=None,
                        help="输出结果到 JSON 文件")
    args = parser.parse_args()

    import shutil

    # 强制重建
    if args.force_rebuild:
        for d in [RECURSIVE_PERSIST, SEMANTIC_PERSIST]:
            if os.path.exists(d):
                shutil.rmtree(d)
                logger.info(f"已删除旧向量库: {d}")

    # 创建 LLM 实例（通义千问 + RAGAS 评测）
    llm = ChatOpenAI(
        model=EVAL_LLM_MODEL,
        api_key=os.getenv("DASHSCOPE_API_KEY"),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        temperature=0.1,
    )

    results = {}

    # 策略 1: 递归字符分块    
    if not args.skip_build or args.force_rebuild:
        retriever_rec, chunks_rec = build_vectorstore(
            DATA_DIR, RECURSIVE_PERSIST, use_semantic=False
        )
    else:
        raw_docs = load_pdfs_from_dir(DATA_DIR)
        chunks_rec = split_documents(raw_docs)
        from langchain_chroma import Chroma
        vectordb_rec = Chroma(
            persist_directory=RECURSIVE_PERSIST,
            embedding_function=QwenEmbeddings(model=EMBEDDING_MODEL),
        )
        retriever_rec = HybridRetriever(
            vectordb_rec, raw_docs,
            recall_k=CONFIG.get("recall_k", 20),
            rrf_top_k=CONFIG.get("rrf_top_k", 20),
        )

    results["recursive"] = run_evaluation(retriever_rec, llm, "递归分块")

    # 策略 2: 语义分块
    if not args.skip_build or args.force_rebuild:
        retriever_sem, chunks_sem = build_vectorstore(
            DATA_DIR, SEMANTIC_PERSIST, use_semantic=True
        )
    else:
        raw_docs = load_pdfs_from_dir(DATA_DIR, clean_fn=clean_text_preserve_nl)
        embeddings = QwenEmbeddings(model=EMBEDDING_MODEL)
        chunks_sem = split_documents(
            raw_docs, embeddings=embeddings,
            similarity_threshold=0.80,
            overlap_ratio=0.25,
            strategy="semantic",
        )
        from langchain_chroma import Chroma
        vectordb_sem = Chroma(
            persist_directory=SEMANTIC_PERSIST,
            embedding_function=QwenEmbeddings(model=EMBEDDING_MODEL),
        )
        retriever_sem = HybridRetriever(
            vectordb_sem, raw_docs,
            recall_k=CONFIG.get("recall_k", 20),
            rrf_top_k=CONFIG.get("rrf_top_k", 20),
        )

    results["semantic"] = run_evaluation(retriever_sem, llm, "语义分块")

    # 输出结果到 JSON 文件（可选）
    if args.output:
        report = {
            "timestamp": datetime.now().isoformat(),
            "config": {
                "test_questions": len(TEST_QUESTIONS),
                "eval_llm": EVAL_LLM_MODEL,
                "embedding": EMBEDDING_MODEL,
                "search_top_k": SEARCH_TOP_K,
            },
            "results": results,
        }
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        logger.info(f"Report saved: {args.output}")

    # 打印对比报告
    sep = "=" * 70
    print("\n" + sep)
    print("  RAGAS Comparison Report")
    print(sep)
    print(f"  Questions: {len(TEST_QUESTIONS)}")
    print(f"  Eval LLM:  {EVAL_LLM_MODEL}")
    print(f"  Embedding: {EMBEDDING_MODEL}")
    print(f"  Top-K:     {SEARCH_TOP_K}")
    print("-" * 70)

    metric_names = [
        ("context_precision", "Context Precision"),
        ("context_recall", "Context Recall"),
        ("faithfulness", "Faithfulness"),
        ("answer_relevancy", "Answer Relevancy"),
    ]

    for metric_key, metric_en in metric_names:
        rec_val = results["recursive"].get(metric_key, 0)
        sem_val = results["semantic"].get(metric_key, 0)
        diff = sem_val - rec_val
        winner = "SEMANTIC" if diff > 0 else ("RECURSIVE" if diff < 0 else "TIE")
        direction = "+" if diff > 0 else ""
        print(f"  {metric_en:<22s} | recursive: {rec_val:.4f} | semantic: {sem_val:.4f} "
              f"| {direction}{diff:.4f}  [{winner}]")

    # 平均检索时间
    rec_time = results["recursive"].get("avg_retrieval_time_ms", 0)
    sem_time = results["semantic"].get("avg_retrieval_time_ms", 0)
    print(f"  {'Avg Retrieval Time':<22s} | recursive: {rec_time:.0f}ms | semantic: {sem_time:.0f}ms "
          f"| {'+' if sem_time > rec_time else ''}{sem_time - rec_time:.0f}ms")

    print(sep)


if __name__ == "__main__":
    main()
