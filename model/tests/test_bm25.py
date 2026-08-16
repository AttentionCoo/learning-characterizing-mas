"""自实现 BM25 检索器单测：CJK 二元组分词、召回、空结果、top-k 限制。"""
from langchain_core.documents import Document

from app.rag.bm25 import BM25Retriever, tokenize


def test_tokenize_mixed_cjk_and_ascii():
    tokens = tokenize("急性缺血性脑卒中 tPA 静脉溶栓")
    assert "tpa" in tokens
    assert "急性" in tokens      # CJK 二元组
    assert "卒中" in tokens
    assert "。" not in tokens    # 标点不产生词项


def test_cjk_bigram_recall_ranks_relevant_doc_first():
    docs = [
        Document(page_content="急性缺血性脑卒中静脉溶栓时间窗为4.5小时"),
        Document(page_content="高血压是脑卒中的主要危险因素"),
    ]
    retriever = BM25Retriever.from_documents(docs, k=2)
    hits = retriever.invoke("脑卒中溶栓")
    assert hits, "应召回与查询重叠的文档"
    assert hits[0].page_content.startswith("急性缺血性")


def test_no_term_overlap_returns_empty():
    docs = [Document(page_content="糖尿病饮食管理指南")]
    retriever = BM25Retriever.from_documents(docs, k=4)
    assert retriever.invoke("脑卒中溶栓时间窗") == []


def test_k_limits_result_count():
    docs = [Document(page_content=f"脑卒中诊疗指南第{i}条") for i in range(5)]
    retriever = BM25Retriever.from_documents(docs, k=3)
    assert len(retriever.invoke("脑卒中诊疗指南")) == 3


def test_empty_documents_returns_empty():
    retriever = BM25Retriever.from_documents([], k=4)
    assert retriever.invoke("任意查询") == []
