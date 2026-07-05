"""
RAGAS 对比评测：递归字符切分 vs 语义分块

评测维度:
  - Context Precision:   检索到的上下文中有多少是真正相关的（精准度）
  - Context Recall:      回答问题所需信息在检索上下文中的覆盖率（召回率）
  - Faithfulness:        生成的回答是否忠实于检索到的上下文（事实一致性）
  - Answer Relevancy:    生成的回答与问题的相关程度（回答相关性）

用法:
  python -m tests.compare_chunking          # 首次运行：构建两套向量库 + 评测
  python -m tests.compare_chunking --skip-build  # 仅评测（向量库已构建）
"""
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

# 确保项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.rag.data_loader import load_pdfs_from_dir, split_documents, clean_text_preserve_nl
from app.rag.retrievers import (
    DashScopeEmbeddings,
    BGEReranker,
    HybridRetriever,
    build_or_load_vectorstore,
    reciprocal_rank_fusion,
    CONFIG,
)

# RAGAS (0.4.x API: 旧版预实例化 metrics，兼容 evaluate())
from ragas import evaluate, EvaluationDataset
from ragas.metrics import (
    context_precision,
    context_recall,
    faithfulness,
    answer_relevancy,
)

load_dotenv()

# ── 日志 ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.WARNING,  # 评测时抑制 DEBUG 日志
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("compare_chunking")
logger.setLevel(logging.INFO)

# ── 配置 ──────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data", "documents")

RECURSIVE_PERSIST = os.path.join(BASE_DIR, "chroma_db_recursive")
SEMANTIC_PERSIST = os.path.join(BASE_DIR, "chroma_db_semantic")

# 评测用 LLM（用于生成回答 + RAGAS 评判）
EVAL_LLM_MODEL = "qwen-plus"
EMBEDDING_MODEL = "text-embedding-v2"

# 检索参数
SEARCH_TOP_K = 5  # 每次检索返回 5 篇上下文供 RAGAS 评估

# ── 测试问题集 ─────────────────────────────────────────────
# 每条包含：question, ground_truth（参考答案，用于 RAGAS 评估）
TEST_QUESTIONS = [
    {
        "question": "脑梗死后出血转化的主要危险因素有哪些？",
        "ground_truth": "出血转化的主要危险因素包括：大面积脑梗死、高血压、高血糖、心房颤动、高龄、基线NIHSS评分较高、使用抗凝药物等。心源性脑栓塞和基线CT低密度灶也是重要的预测因子。"
    },
    {
        "question": "急性缺血性脑卒中的静脉溶栓时间窗是多久？",
        "ground_truth": "急性缺血性脑卒中静脉溶栓治疗应在发病后4.5小时内开始。部分经影像学筛选的患者可延长至9小时。溶栓越早越好，每延迟一分钟约190万个神经元死亡。"
    },
    {
        "question": "阿替普酶（rt-PA）的标准用法用量是什么？",
        "ground_truth": "阿替普酶标准剂量为0.9mg/kg体重，最大剂量不超过90mg。其中10%在1分钟内静脉推注，剩余90%在60分钟内持续静脉滴注。"
    },
    {
        "question": "急性缺血性卒中血管内治疗的适应症是什么？",
        "ground_truth": "血管内治疗的适应症包括：大血管闭塞（如颈内动脉、大脑中动脉M1/M2段）、发病6-24小时内、ASPECTS评分≥6分、NIHSS评分≥6分、CTA/MRA证实存在可挽救的缺血半暗带。前循环闭塞时间窗可延长至24小时。"
    },
    {
        "question": "脑卒中一级预防的主要措施有哪些？",
        "ground_truth": "一级预防措施包括：控制血压（目标<140/90mmHg）、控制血糖、控制血脂、戒烟限酒、适度运动、合理膳食、控制体重。心房颤动患者需口服抗凝药物。无症状颈动脉狭窄需评估手术指征。"
    },
    {
        "question": "急性脑梗死溶栓后的血压管理目标是多少？",
        "ground_truth": "溶栓后24小时内血压应控制在180/105mmHg以下。溶栓前血压需降至185/110mmHg以下方可进行溶栓治疗。血压过高会增加出血转化风险。"
    },
    {
        "question": "NIHSS评分在脑卒中诊治中的作用是什么？",
        "ground_truth": "NIHSS（美国国立卫生研究院卒中量表）用于量化评估脑卒中患者的神经功能缺损程度。评分范围0-42分。评分<4分通常为轻型卒中，≥25分为极重型。用于指导溶栓决策、预后评估和治疗效果监测。基线NIHSS评分较高是出血转化的危险因素之一。"
    },
    {
        "question": "急性缺血性脑卒中早期康复的时机和内容是什么？",
        "ground_truth": "早期康复应在病情稳定后24-48小时内开始。内容包括：良肢位摆放、被动关节活动度训练、翻身训练、吞咽功能评估与训练、语言功能康复、心理支持。重度卒中患者应延迟至病情稳定后再开始。康复强度需根据患者耐受程度个体化。"
    },
    {
        "question": "脑卒中二级预防中抗血小板药物的选择原则是什么？",
        "ground_truth": "非心源性缺血性卒中推荐抗血小板治疗：阿司匹林（50-325mg/d）或氯吡格雷（75mg/d）单药治疗。轻型卒中（NIHSS≤3分）在发病24小时内可考虑阿司匹林+氯吡格雷双联抗血小板治疗21天。心源性栓塞需改用口服抗凝药（如华法林或新型口服抗凝药）。"
    },
    {
        "question": "急性脑梗死后出血转化的分型和处理原则是什么？",
        "ground_truth": "出血转化分型：HI-1型（梗死灶边缘小点状出血）、HI-2型（梗死灶内融合点状出血）、PH-1型（血肿≤梗死面积30%伴轻微占位效应）、PH-2型（血肿>梗死面积30%伴明显占位效应）。HI型和PH-1型通常无症状无需特殊处理；PH-2型需停用抗血小板/抗凝药物，必要时给予逆转剂或手术。"
    },
]


# ═══════════════════════════════════════════════════════════
# 评测基础设施
# ═══════════════════════════════════════════════════════════

_dashscope_client = None


def _get_dashscope_client():
    """懒加载 OpenAI-compatible client，指向阿里云百炼 DashScope 端点"""
    global _dashscope_client
    if _dashscope_client is None:
        _dashscope_client = OpenAI(
            api_key=os.getenv("DASHSCOPE_API_KEY"),
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
    return _dashscope_client

def build_vectorstore(docs_dir: str, persist_dir: str, use_semantic: bool):
    """
    构建向量库。use_semantic=True 使用语义分块，否则使用递归字符切分。
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"Building vectorstore: {persist_dir}")
    logger.info(f"   Strategy: {'Semantic (0.80 + overlap)' if use_semantic else 'Recursive'}")
    logger.info(f"{'='*60}")

    # 加载文档（语义分块保留换行作为段落边界信号）
    if use_semantic:
        raw_docs = load_pdfs_from_dir(docs_dir, clean_fn=clean_text_preserve_nl)
    else:
        raw_docs = load_pdfs_from_dir(docs_dir)
    logger.info(f"Loaded {len(raw_docs)} pages")

    # 切分
    if use_semantic:
        embeddings = DashScopeEmbeddings(model=EMBEDDING_MODEL)
        chunks = split_documents(
            raw_docs,
            embeddings=embeddings,
            similarity_threshold=0.80,   # 升高阈值减少医学文本假断点
            min_chunk_size=100,
            max_chunk_size=800,
            overlap_ratio=0.25,           # 句子级重叠
            strategy="semantic",          # 显式指定语义分块
        )
    else:
        chunks = split_documents(raw_docs)  # 默认 hybrid

    logger.info(f"✂️ 切分得到 {len(chunks)} 个块")

    # 构建/加载向量库（关闭 QA 衍生，公平对比）
    vectordb = build_or_load_vectorstore(
        chunks, persist_dir, enable_qa=False
    )

    # 构建检索引擎
    retriever = HybridRetriever(
        vectordb, raw_docs,
        recall_k=CONFIG.get("recall_k", 20),
        rrf_top_k=CONFIG.get("rrf_top_k", 20),
    )

    return retriever, chunks


def generate_answer(query: str, contexts: List[Document], llm) -> str:
    """基于检索到的上下文生成回答"""
    if not contexts:
        return "（无法回答：未检索到相关上下文）"

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
    跑一轮完整的 RAGAS 评测，返回指标字典。
    """
    eval_data = []
    retrieval_times = []

    logger.info(f"\n🔍 [{strategy_name}] 开始检索+生成...")

    for i, item in enumerate(TEST_QUESTIONS):
        question = item["question"]
        ground_truth = item["ground_truth"]

        # 检索
        t0 = time.time()
        contexts = retriever.search(question, top_k_final=SEARCH_TOP_K)
        retrieval_times.append(time.time() - t0)

        # 生成回答
        answer = generate_answer(question, contexts, llm)

        context_texts = [d.page_content for d in contexts]

        eval_data.append({
            "user_input": question,
            "response": answer,
            "retrieved_contexts": context_texts,
            "reference": ground_truth,
        })

        logger.info(f"  Q{i+1}: {question[:40]}... → {len(contexts)} contexts, {len(answer)} chars")

    # 构建 RAGAS Dataset
    hf_dataset = Dataset.from_list(eval_data)
    eval_dataset = EvaluationDataset.from_hf_dataset(hf_dataset)

    # RAGAS 评估
    # 注意：使用 LangchainEmbeddingsWrapper 包装项目自己的 DashScopeEmbeddings，
    # 而不是 ragas.embeddings.OpenAIEmbeddings（后者缺少 embed_query 方法）。
    logger.info(f"📊 [{strategy_name}] 运行 RAGAS 评估...")
    from ragas.embeddings import LangchainEmbeddingsWrapper

    ragas_emb = LangchainEmbeddingsWrapper(
        DashScopeEmbeddings(model=EMBEDDING_MODEL)
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

    # 提取均值
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


# ═══════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="RAGAS 对比评测：递归切分 vs 语义分块")
    parser.add_argument("--skip-build", action="store_true",
                        help="跳过向量库构建（适用于已构建好的场景）")
    parser.add_argument("--force-rebuild", action="store_true",
                        help="强制重建向量库（删除旧数据）")
    parser.add_argument("--output", type=str, default=None,
                        help="将结果输出为 JSON 文件路径")
    args = parser.parse_args()

    import shutil

    # 强制重建
    if args.force_rebuild:
        for d in [RECURSIVE_PERSIST, SEMANTIC_PERSIST]:
            if os.path.exists(d):
                shutil.rmtree(d)
                logger.info(f"🗑️ 删除旧向量库: {d}")

    # 构建 LLM（用于生成回答 + RAGAS 评判）
    llm = ChatOpenAI(
        model=EVAL_LLM_MODEL,
        api_key=os.getenv("DASHSCOPE_API_KEY"),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        temperature=0.1,
    )

    results = {}

    # ═══ 评测 1: 递归字符切分 ═══
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
            embedding_function=DashScopeEmbeddings(model=EMBEDDING_MODEL),
        )
        retriever_rec = HybridRetriever(
            vectordb_rec, raw_docs,
            recall_k=CONFIG.get("recall_k", 20),
            rrf_top_k=CONFIG.get("rrf_top_k", 20),
        )

    results["recursive"] = run_evaluation(retriever_rec, llm, "递归字符切分")

    # ═══ 评测 2: 语义分块 ═══
    if not args.skip_build or args.force_rebuild:
        retriever_sem, chunks_sem = build_vectorstore(
            DATA_DIR, SEMANTIC_PERSIST, use_semantic=True
        )
    else:
        raw_docs = load_pdfs_from_dir(DATA_DIR, clean_fn=clean_text_preserve_nl)
        embeddings = DashScopeEmbeddings(model=EMBEDDING_MODEL)
        chunks_sem = split_documents(
            raw_docs, embeddings=embeddings,
            similarity_threshold=0.80,
            overlap_ratio=0.25,
            strategy="semantic",
        )
        from langchain_chroma import Chroma
        vectordb_sem = Chroma(
            persist_directory=SEMANTIC_PERSIST,
            embedding_function=DashScopeEmbeddings(model=EMBEDDING_MODEL),
        )
        retriever_sem = HybridRetriever(
            vectordb_sem, raw_docs,
            recall_k=CONFIG.get("recall_k", 20),
            rrf_top_k=CONFIG.get("rrf_top_k", 20),
        )

    results["semantic"] = run_evaluation(retriever_sem, llm, "语义分块")

    # ═══ 先保存 JSON（避免打印崩溃导致数据丢失）═══
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

    # ═══ 输出对比报告 ═══
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

    # 检索耗时
    rec_time = results["recursive"].get("avg_retrieval_time_ms", 0)
    sem_time = results["semantic"].get("avg_retrieval_time_ms", 0)
    print(f"  {'Avg Retrieval Time':<22s} | recursive: {rec_time:.0f}ms | semantic: {sem_time:.0f}ms "
          f"| {'+' if sem_time > rec_time else ''}{sem_time - rec_time:.0f}ms")

    print(sep)


if __name__ == "__main__":
    main()
