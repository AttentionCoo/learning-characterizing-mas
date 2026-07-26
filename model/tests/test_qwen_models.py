from types import SimpleNamespace

import pytest
from langchain_core.documents import Document

from app.config.qwen import (
    get_qwen_chat_model_name,
    get_qwen_embedding_dimension,
    get_qwen_embedding_model,
    get_qwen_rerank_model,
    get_qwen_vision_model,
)
from app.rag import retrievers
from app.rag.retrievers import HybridRetriever, QwenEmbeddings
from app.services.vision_service import VisionAnalysisService


def test_qwen_model_defaults(monkeypatch):
    for name in (
        "QWEN_MODEL_MAX",
        "QWEN_MODEL_PLUS",
        "QWEN_MODEL_TURBO",
        "QWEN_EMBEDDING_MODEL",
        "QWEN_EMBEDDING_DIMENSION",
        "QWEN_RERANK_MODEL",
        "QWEN_VISION_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)

    assert get_qwen_chat_model_name("max") == "qwen-max"
    assert get_qwen_chat_model_name("plus") == "qwen-plus"
    assert get_qwen_chat_model_name("turbo") == "qwen-turbo"
    assert get_qwen_embedding_model() == "qwen3.7-text-embedding"
    assert get_qwen_embedding_dimension() == 1024
    assert get_qwen_rerank_model() == "qwen3-rerank"
    assert get_qwen_vision_model() == "qwen-vl-max"


def test_qwen_embeddings_use_same_model_and_dimension(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    calls = []

    def fake_call(**kwargs):
        calls.append(kwargs)
        items = [
            {"text_index": index, "embedding": [float(index), 0.0, 1.0]}
            for index, _ in enumerate(kwargs["input"])
        ]
        return SimpleNamespace(status_code=200, output={"embeddings": items})

    monkeypatch.setattr(retrievers.dashscope.TextEmbedding, "call", fake_call)
    embeddings = QwenEmbeddings(
        model="qwen3.7-text-embedding",
        dimension=3,
        batch_size=2,
        max_retries=1,
    )

    document_vectors = embeddings.embed_documents(["指南甲", "指南乙", "指南丙"])
    query_vector = embeddings.embed_query("脑卒中")

    assert len(document_vectors) == 3
    assert query_vector == [0.0, 0.0, 1.0]
    assert [call["text_type"] for call in calls] == [
        "document",
        "document",
        "query",
    ]
    assert all(call["model"] == "qwen3.7-text-embedding" for call in calls)
    assert all(call["dimension"] == 3 for call in calls)


def test_qwen_embeddings_reject_wrong_dimension(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")

    def fake_call(**_kwargs):
        return SimpleNamespace(
            status_code=200,
            output={"embeddings": [{"text_index": 0, "embedding": [1.0, 2.0]}]},
        )

    monkeypatch.setattr(retrievers.dashscope.TextEmbedding, "call", fake_call)
    embeddings = QwenEmbeddings(dimension=3, max_retries=1)

    with pytest.raises(RuntimeError, match="维度异常"):
        embeddings.embed_query("测试")


def test_hybrid_retriever_keeps_bm25_when_vector_search_fails():
    expected = [Document(page_content="脑卒中指南", metadata={"source": "指南.pdf"})]

    class FailingVectorRetriever:
        def invoke(self, _query):
            raise RuntimeError("向量服务不可用")

    class WorkingBM25:
        def invoke(self, _query):
            return expected

    class PassthroughReranker:
        def rerank(self, _query, docs, top_k=None):
            return docs[:top_k]

    hybrid = HybridRetriever.__new__(HybridRetriever)
    hybrid.vector_retriever = FailingVectorRetriever()
    hybrid.bm25 = WorkingBM25()
    hybrid.reranker = PassthroughReranker()
    hybrid.rrf_top_k = 20
    hybrid._cache = {}
    hybrid._cache_ttl = 300

    result = hybrid.search("什么是脑卒中", top_k_final=1)

    assert result == expected


def test_vision_service_builds_qwen_multimodal_messages(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setenv("QWEN_VISION_MODEL", "qwen-vl-max")
    prompt_manager = SimpleNamespace(get=lambda _name: None)
    service = VisionAnalysisService(prompt_manager)

    messages = service._build_messages(
        ["aGVsbG8="],
        "请分析图片",
        "你是图片分析助手",
    )

    assert service._model == "qwen-vl-max"
    assert messages[0]["role"] == "system"
    assert messages[1]["content"][0]["image"].startswith("data:image/jpeg;base64,")
    assert messages[1]["content"][-1] == {"text": "请分析图片"}
