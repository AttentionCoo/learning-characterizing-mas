"""
RAG 增强（决策驱动路由 + 物理隔离 + 医学评分）单元测试。

覆盖文档验证点：
- 血脂指南 chunk 物理上不能进 anatomy（入口约束）
- 证据类型路由正确
- 查询翻译（同义词扩展 / 剔除患者变量）
- 医学评分权重与淘汰惩罚
- Rerank 兜底（RRF 归一化 + 医学评分，不退化原始顺序）
- 临床决策规划（按临床优先级排序）
- chunk 结构化标签提取（subtopic/intervention/year/authority/time_window/evidence_level）

运行：在 model/ 目录下 `python -m pytest tests/test_medical_rag.py -q`
"""

import pytest
from langchain_core.documents import Document

from app.rag.labels import (
    AUTHORITY_GUIDELINE,
    AUTHORITY_TEXTBOOK,
    SUBTOPIC_COLLECTION,
    assign_decision_node,
    classify_subtopic,
    detect_evidence_level,
    detect_time_window,
    extract_authority,
    extract_interventions,
    extract_year,
    tag_chunk,
)
from app.rag.planner import plan_decision_nodes
from app.rag.router import (
    classify_evidence_type,
    route_collections,
    translate_query,
)
from app.rag.scoring import (
    MedicalEvidenceReranker,
    authority_score,
    medical_evidence_score,
    normalize_scores,
    recency_score,
)

# ═══════════════════════════════════════════════════════════════
# 1. 血脂指南不能进 anatomy（文档点名的核心断言）
# ═══════════════════════════════════════════════════════════════


def test_lipid_guideline_not_anatomy():
    """血脂/二级预防指南 chunk 分类必须落进 prevention，绝不能是 anatomy。"""
    lipid_chunk = (
        "二级预防：缺血性卒中患者应长期服用他汀类药物进行降脂治疗，"
        "控制低密度脂蛋白胆固醇水平，同时给予抗血小板治疗预防复发。"
    )
    subtopic = classify_subtopic(lipid_chunk, source="中国脑卒中防治指导规范（2021年版）.pdf")
    collection = SUBTOPIC_COLLECTION.get(subtopic)
    assert subtopic != "anatomy"
    assert collection != "anatomy"
    assert collection == "prevention", f"血脂指南 chunk 应进 prevention，实际: {subtopic} → {collection}"


def test_anatomy_chunk_goes_to_anatomy_collection():
    """解剖教材 chunk（MCA 供血区）应进 anatomy 库。"""
    anatomy_chunk = (
        "大脑中动脉（MCA）皮层支供血额叶、颞叶和顶叶外侧面，"
        "深穿支供血基底节和内囊，其解剖位置与侧支循环关系密切。"
    )
    subtopic = classify_subtopic(anatomy_chunk, source="Neuroanatomy through Clinical Cases, 3e.pdf")
    collection = SUBTOPIC_COLLECTION.get(subtopic)
    assert subtopic == "anatomy"
    assert collection == "anatomy"


def test_route_lipid_query_to_prevention():
    """"二级预防 / 降脂"查询应路由到 prevention 库，而非 anatomy。"""
    evidence_type = classify_evidence_type("缺血性卒中后二级预防应该如何降脂治疗？")
    assert evidence_type == "prevention"
    collections = route_collections(evidence_type)
    assert "anatomy" not in collections
    assert "prevention" in collections


# ═══════════════════════════════════════════════════════════════
# 2. 证据类型路由
# ═══════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "query,expected",
    [
        ("发病3小时急性缺血性卒中能否静脉溶栓？", "treatment"),
        ("左侧MCA闭塞的解剖供血区域是哪里？", "anatomy"),
        ("心房颤动导致心源性栓塞的病因机制", "etiology"),
        ("卒中后二级预防与康复护理要点", "prevention"),
        ("NIHSS评分如何评估卒中严重程度", "guideline"),
        ("卒中患者的CT和MRI影像诊断标准", "guideline"),
    ],
)
def test_route_evidence_types(query, expected):
    assert classify_evidence_type(query) == expected


def test_route_decision_node_prioritizes_etiology():
    """决策节点强先验：房颤病因问题即使含'治疗'也应路由到 etiology。"""
    evidence_type = classify_evidence_type(
        "房颤患者的卒中病因评估与抗凝治疗",
        decision_nodes=["etiology"],
    )
    assert evidence_type == "etiology"


# ═══════════════════════════════════════════════════════════════
# 3. 查询翻译（Query Translator）
# ═══════════════════════════════════════════════════════════════


def test_translate_query_synonym_expansion():
    """rt-pa 应扩展出 阿替普酶/重组组织型纤溶酶原激活剂。"""
    translated = translate_query("rt-pa静脉溶栓的适应证")
    assert "阿替普酶" in translated
    assert "重组组织型纤溶酶原激活剂" in translated


def test_translate_query_keeps_original():
    """翻译应保留原词（OR-AND 范式），而不是替换掉。"""
    translated = translate_query("房颤患者抗凝治疗")
    assert "房颤" in translated
    assert "心房颤动" in translated
    assert "华法林" in translated


def test_translate_removes_patient_variables():
    """NIHSS 分数、年龄等患者变量应被剔除，不能污染检索关键词。"""
    translated = translate_query("NIHSS 12 分的患者，年龄 75 岁，能否溶栓")
    assert "nihss 12" not in translated.lower()
    assert "12" not in translated
    assert "75 岁" not in translated
    assert "溶栓" in translated


# ═══════════════════════════════════════════════════════════════
# 4. 临床决策规划
# ═══════════════════════════════════════════════════════════════


def test_plan_decision_nodes_reperfusion():
    """溶栓时间窗问题应命中 reperfusion 决策节点。"""
    nodes = plan_decision_nodes("发病4.5小时内能否静脉溶栓？")
    assert "reperfusion" in nodes
    # 按临床优先级，再灌注应排在二级预防之前（若同时命中）
    if "secondary_prevention" in nodes:
        assert nodes.index("reperfusion") < nodes.index("secondary_prevention")


def test_plan_decision_nodes_priority_order():
    """决策节点按临床优先级排序：再灌注 → LVO → 血压 → 病因 → 二级预防。"""
    question = "大血管闭塞取栓后血压管理及二级预防抗血小板方案"
    nodes = plan_decision_nodes(question)
    priority = ["reperfusion", "lvo", "blood_pressure", "etiology", "secondary_prevention"]
    positions = [priority.index(n) for n in nodes if n in priority]
    assert positions == sorted(positions), f"决策节点未按临床优先级排序: {nodes}"


def test_plan_decision_nodes_empty():
    assert plan_decision_nodes("今天天气怎么样") == []


# ═══════════════════════════════════════════════════════════════
# 5. chunk 结构化标签
# ═══════════════════════════════════════════════════════════════


def test_extract_year_and_authority():
    assert extract_year("中国急性缺血性卒中诊治指南2023.pdf") == 2023
    assert extract_year("2019 Update to the 2018 Guidelines.pdf") == 2019
    assert extract_authority("中国急性缺血性卒中诊治指南2023.pdf") == AUTHORITY_GUIDELINE
    assert extract_authority("Neuroanatomy through Clinical Cases, 3e.pdf") == AUTHORITY_TEXTBOOK


def test_extract_interventions_alias():
    """rt-pa 应归一为 iv_thrombolysis（静脉溶栓）。"""
    interventions = extract_interventions("给予rt-pa静脉溶栓治疗，随后阿司匹林抗血小板")
    assert "iv_thrombolysis" in interventions
    assert "antiplatelet" in interventions


def test_detect_time_window_and_evidence_level():
    assert detect_time_window("发病4.5小时内静脉溶栓") == "4.5小时"
    assert detect_time_window("6h内取栓") == "6小时"
    assert detect_evidence_level("推荐级别：I级，证据级别：A") is not None


def test_tag_chunk_writes_metadata():
    meta = tag_chunk(
        "机械取栓治疗大血管闭塞，推荐时间窗6小时",
        {"source": "急性缺血性卒中血管内治疗中国指南2023.pdf", "page": 5},
    )
    assert meta["collection"] == "treatment"
    assert meta["subtopic"] == "reperfusion"
    assert "mechanical_thrombectomy" in meta["interventions"]
    assert meta["year"] == 2023
    assert meta["authority"] == AUTHORITY_GUIDELINE
    assert "reperfusion" in meta["decision_node"]


def test_partition_chunks_by_collection_isolates_lipid_from_anatomy():
    """
    分库回归测试：标签必须写回 chunk.metadata（tag_chunk 返回副本），
    血脂 chunk 进 prevention、解剖 chunk 进 anatomy，绝不能全部落进 guideline。
    """
    from app.rag.labels import partition_chunks_by_collection

    chunks = [
        Document(
            page_content="二级预防他汀降脂抗血小板预防复发",
            metadata={"source": "中国脑卒中防治指导规范（2021年版）.pdf"},
        ),
        Document(
            page_content="大脑中动脉供血区解剖与侧支循环关系",
            metadata={"source": "Neuroanatomy through Clinical Cases, 3e.pdf"},
        ),
    ]
    partitioned = partition_chunks_by_collection(chunks)

    # 标签已写回 chunk.metadata（防止"返回值被丢弃"回归）
    assert all(c.metadata.get("collection") for c in chunks)

    # 血脂 chunk → prevention 库
    assert partitioned["prevention"], "血脂指南 chunk 必须进 prevention 库"
    assert all("降脂" in c.page_content for c in partitioned["prevention"])

    # 解剖 chunk → anatomy 库
    assert partitioned["anatomy"], "解剖 chunk 必须进 anatomy 库"
    assert all("解剖" in c.page_content or "供血" in c.page_content for c in partitioned["anatomy"])

    # 血脂 chunk 绝不混入 anatomy 候选集
    assert all("降脂" not in c.page_content for c in partitioned["anatomy"])


# ═══════════════════════════════════════════════════════════════
# 6. 医学评分（权重 + 惩罚 + 兜底）
# ═══════════════════════════════════════════════════════════════


def _doc(text, **meta):
    return Document(page_content=text, metadata=meta)


def test_normalize_scores():
    assert normalize_scores([1, 3, 5]) == [0.0, 0.5, 1.0]
    assert normalize_scores([2, 2, 2]) == [1.0, 1.0, 1.0]
    assert normalize_scores([]) == []


def test_authority_recency_score():
    assert authority_score(AUTHORITY_GUIDELINE) == 1.0
    assert authority_score(AUTHORITY_TEXTBOOK) == 0.8
    assert recency_score(2024) == 1.0
    assert recency_score(2023) > recency_score(2019)


def test_medical_score_weights():
    """权重正确融合：指南(权威1.0)+治疗库(类型1.0)+语义1.0 → 加权分 ≈ 0.35+0.25+0.2+时效+0.1。"""
    doc = _doc(
        "静脉溶栓治疗缺血性卒中",
        collection="treatment",
        subtopic="reperfusion",
        authority=AUTHORITY_GUIDELINE,
        year=2023,
        interventions=["iv_thrombolysis"],
    )
    result = medical_evidence_score(
        "静脉溶栓的适应证", doc, evidence_type="treatment", semantic_score=1.0
    )
    breakdown = result["breakdown"]
    assert breakdown["semantic"] == 1.0
    assert breakdown["evidence_type"] == 1.0
    assert breakdown["authority"] == 1.0
    assert breakdown["topic"] == 1.0
    # 干预命中加分
    assert result["bonus"] > 0
    # 0.35+0.25+0.20+0.10+0.10+bonus
    assert result["score"] > 0.9


def test_mismatch_penalty():
    """治疗查询中混入的血脂预防 chunk 应被淘汰惩罚（负分区间）。"""
    lipid_doc = _doc(
        "二级预防降脂治疗他汀类药物",
        collection="prevention",
        subtopic="prevention",
        authority=AUTHORITY_GUIDELINE,
        year=2023,
        interventions=["lipid_lowering"],
    )
    result = medical_evidence_score(
        "急性期静脉溶栓治疗", lipid_doc, evidence_type="treatment", semantic_score=0.9
    )
    assert result["penalty"] < 0
    assert result["score"] < 0.3  # 语义再高也因主题不匹配被压垮


def test_fallback_rerank_uses_medical_score_not_original_order():
    """
    Rerank 兜底核心断言：无 API 时按 RRF 归一化 + 医学评分排序，
    而不是退化为原始 embedding 顺序。
    """
    docs = [
        # 原始顺序第 1：血脂预防 chunk（语义分最高，但主题不匹配 treatment）
        _doc(
            "二级预防他汀降脂预防复发",
            collection="prevention", subtopic="prevention",
            authority=AUTHORITY_GUIDELINE, year=2023,
            interventions=["lipid_lowering"], rrf_score=0.9,
        ),
        # 原始顺序第 2：治疗库 chunk（主题匹配，权威指南）
        _doc(
            "静脉溶栓治疗急性缺血性卒中推荐意见",
            collection="treatment", subtopic="reperfusion",
            authority=AUTHORITY_GUIDELINE, year=2023,
            interventions=["iv_thrombolysis"], rrf_score=0.5,
        ),
    ]
    reranker = MedicalEvidenceReranker(top_k=2, api_key=None)  # 无 API → 兜底
    ranked = reranker.fallback_rerank(
        "静脉溶栓的适应证", docs, evidence_type="treatment", top_k=2
    )
    # 医学评分应把匹配治疗主题的文档排到前面
    assert ranked[0].metadata["collection"] == "treatment"
    assert ranked[0].metadata["medical_score"] > ranked[1].metadata["medical_score"]
    # 不再依赖原始顺序（血脂 chunk 虽然原始 rrf 更高，但排到了后面）
    assert ranked[1].metadata["collection"] == "prevention"


def test_rerank_accepts_external_semantic_scores():
    """外部注入语义分时，评分重排仍按医学评分执行。"""
    docs = [
        _doc("治疗A", collection="treatment", subtopic="reperfusion",
             authority=AUTHORITY_GUIDELINE, year=2024,
             interventions=["iv_thrombolysis"], rrf_score=0.1),
        _doc("治疗B", collection="treatment", subtopic="reperfusion",
             authority=AUTHORITY_TEXTBOOK, year=2019,
             interventions=["iv_thrombolysis"], rrf_score=0.9),
    ]
    reranker = MedicalEvidenceReranker(top_k=2, api_key=None)
    ranked = reranker.rerank(
        "溶栓", docs, evidence_type="treatment", top_k=2,
        semantic_scores=[1.0, 0.0],  # 语义分相同，靠权威/时效区分
    )
    # 权威指南 + 新年份 的 doc0 应胜出
    assert ranked[0].page_content == "治疗A"


# ═══════════════════════════════════════════════════════════════
# 7. 跨库路由与隔离（入口约束）
# ═══════════════════════════════════════════════════════════════


def test_route_collections_strict_anatomy_only():
    """strict 模式下 anatomy 查询只进 anatomy 库——隔离入口约束。"""
    collections = route_collections("anatomy", strict=True)
    assert collections == ["anatomy"]


def test_route_collections_treatment_with_related():
    """非 strict 模式：treatment 主库 + guideline 相关库（跨库 RRF 融合）。"""
    collections = route_collections("treatment", strict=False)
    assert collections == ["treatment", "guideline"]


# ═══════════════════════════════════════════════════════════════
# 8. 检索证据格式与解析（防止标签破坏 parse_retrieval_evidence 回归）
# ═══════════════════════════════════════════════════════════════


def test_retrieve_single_format_parseable():
    """retrieve_single 输出(带主题/干预/年份/权威标签)必须能被 parse_retrieval_evidence 解析。"""
    from app.agents.services.retrieval_service import EvidenceRetrievalService
    from app.agents.utils.reasoning_trace import parse_retrieval_evidence

    class FakeRetriever:
        def search(self, query, top_k=None, evidence_type=None, decision_nodes=None):
            return [Document(
                page_content="静脉溶栓治疗急性缺血性卒中的推荐意见",
                metadata={
                    "source": "中国急性缺血性卒中诊治指南2023.pdf",
                    "page": 5,
                    "medical_score": 0.85,
                    "subtopic_name": "再灌注治疗",
                    "interventions": ["iv_thrombolysis"],
                    "year": 2023,
                    "authority": "guideline",
                },
            )]

    service = EvidenceRetrievalService(FakeRetriever(), top_k=3)
    evidence = service.retrieve_single("静脉溶栓的适应证")

    # 关键：第一行 "(相关度:0.85)" 后必须紧跟换行，标签独立成行
    assert "(相关度:0.85)\n" in evidence

    sources = parse_retrieval_evidence(evidence)
    assert sources, f"检索证据应能被解析出 sources，实际 evidence={evidence!r}"
    assert sources[0]["guide"] == "中国急性缺血性卒中诊治指南2023"
    assert sources[0]["page"] == "5"
