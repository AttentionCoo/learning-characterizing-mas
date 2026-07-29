import asyncio

from app.agents.orchestrators.nodes.retrieve_node import RetrieveNode
from app.agents.orchestrators.xf_xinghuo_agent import LearningAgent
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


def test_parse_retrieval_evidence_keeps_all_sources_and_full_excerpt():
    long_excerpt = "指南命中内容" * 80
    documents = "\n\n".join(
        f"【文献{i}】[来源:指南{i}.pdf p.{i}](相关度:0.{i})\n{long_excerpt}"
        for i in range(1, 11)
    )
    evidence = f"### 检索维度1: 完整检索证据\n{documents}"

    sources = parse_retrieval_evidence(evidence)

    assert len(sources) == 10
    assert sources[0]["excerpt"] == long_excerpt
    assert sources[-1]["guide"] == "指南10"


def test_retrieve_node_keeps_full_sources_while_truncating_reasoning_context():
    class FakeAssistant:
        async def afast_parallel_retrieve(self, _questions):
            excerpt = "完整证据" * 180
            return "\n\n".join(
                f"【文献{i}】[来源:指南{i}.pdf p.{i}](相关度:0.9)\n{excerpt}"
                for i in range(1, 4)
            )

    node = RetrieveNode(FakeAssistant())
    result = asyncio.run(node.run({"learning_questions": ["检索问题"]}))

    assert len(result["evidence"]) < len("完整证据" * 180 * 3)
    assert len(result["retrieval_sources"]) == 3
    assert result["retrieval_sources"][-1]["guide"] == "指南3"


def test_streaming_report_emits_token_and_completion_audit_event():
    class FakeGraph:
        async def astream_events(self, _state, config, version):
            yield {
                "event": "on_chain_end",
                "name": "generate_report",
                "metadata": {"langgraph_node": "generate_report"},
                "data": {"output": {"report": "最终回答"}},
            }

    agent = LearningAgent.__new__(LearningAgent)
    agent.graph = FakeGraph()
    agent._event_log_counts = {}

    async def collect_events():
        return [event async for event in agent.run_learning_reasoning("问题")]

    events = asyncio.run(collect_events())

    assert [event["type"] for event in events] == ["token", "node_done"]
    assert events[1]["title"] == "回答生成完成"


def test_streaming_report_replaces_tokens_with_complete_report_at_chain_end():
    class Chunk:
        content = "一、总体评估\n"

    class FakeGraph:
        async def astream_events(self, _state, config, version):
            yield {
                "event": "on_chat_model_stream",
                "name": "ChatModel",
                "metadata": {"langgraph_node": "generate_report"},
                "data": {"chunk": Chunk()},
            }
            yield {
                "event": "on_chain_end",
                "name": "generate_report",
                "metadata": {"langgraph_node": "generate_report"},
                "data": {"output": {"report": "一、总体评估\n二、改进建议"}},
            }

    agent = LearningAgent.__new__(LearningAgent)
    agent.graph = FakeGraph()
    agent._event_log_counts = {}

    async def collect_events():
        return [event async for event in agent.run_learning_reasoning("问题")]

    events = asyncio.run(collect_events())

    assert [event["type"] for event in events] == ["token", "replace", "node_done"]
    assert events[1]["content"] == "一、总体评估\n二、改进建议"
