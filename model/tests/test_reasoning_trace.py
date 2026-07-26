from app.agents.utils.reasoning_trace import build_node_trace, parse_retrieval_evidence


def test_parse_retrieval_evidence_includes_guide_page_query_and_excerpt():
    evidence = """### 检索维度1: 静脉溶栓时间窗
【文献1】[来源:中国急性缺血性脑卒中诊治指南2023.pdf p.12](相关度:0.91)
发病 4.5 小时内可评估静脉溶栓治疗。

【文献2】[来源:中国脑血管病临床管理指南（第2版）.PDF p.38](相关度:0.82)
治疗前应完成必要的影像学评估。

---

### 检索维度2: 二级预防
【文献1】[来源:中国脑卒中防治指导规范.pdf p.7](相关度:N/A)
根据卒中机制制定个体化二级预防策略。"""

    sources = parse_retrieval_evidence(evidence)

    assert len(sources) == 3
    assert sources[0] == {
        "guide": "中国急性缺血性脑卒中诊治指南2023",
        "page": "12",
        "query": "静脉溶栓时间窗",
        "score": "0.91",
        "excerpt": "发病 4.5 小时内可评估静脉溶栓治疗。",
    }
    assert sources[1]["guide"] == "中国脑血管病临床管理指南（第2版）"
    assert sources[2]["query"] == "二级预防"


def test_build_retrieve_trace_exposes_rag_sources_without_raw_prompt():
    output = {
        "evidence": """### 检索维度1: TOAST 分型
【文献1】[来源:中国脑血管病防治指南.pdf p.20](相关度:0.88)
TOAST 分型用于缺血性卒中病因分类。"""
    }

    trace = build_node_trace("retrieve", output)

    assert trace["title"] == "RAG 检索完成"
    assert "1 条指南证据" in trace["content"]
    assert trace["sources"][0]["guide"] == "中国脑血管病防治指南"


def test_build_reason_trace_is_an_auditable_summary_not_raw_chain_of_thought():
    output = {
        "active_experts": ["神经病学专家", "循证医学专家"],
        "debate_history": [{"round": 1}],
        "proposal": "这段内部综合提案不应该原样输出",
        "critique": "这段内部批判也不应该原样输出",
    }

    trace = build_node_trace("reason", output)

    assert trace["title"] == "多智能体推理完成"
    assert "神经病学专家、循证医学专家" in trace["content"]
    assert "1 轮交叉校验" in trace["content"]
    assert "内部综合提案" not in trace["content"]
