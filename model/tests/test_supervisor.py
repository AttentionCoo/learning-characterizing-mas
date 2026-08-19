"""Tutor 监督者单测：最终答案提取、轨迹构建、工具注册、失败降级。"""
import asyncio
from types import SimpleNamespace

import pytest

from app.agents.core.schema import LearningState
from app.agents.orchestrators.supervisor import TutorSupervisor


def _make_state(**overrides) -> LearningState:
    state = {
        "case_text": "什么是脑卒中的 FAST 原则？",
        "all_info": "",
        "report_mode": "tutor",
        "intent_type": "tutor",
        "input_rejection_message": "",
        "context": {},
        "learning_questions": [],
        "key_risks": [],
        "complexity": "high",
        "difficulty_score": 0.5,
        "evidence": "",
        "retrieval_sources": [],
        "proposal": "",
        "critique": "",
        "user_questions": [],
        "report": "",
        "expert_advices": {},
        "validation_passed": True,
        "validation_feedback": "",
        "reflection_count": 0,
        "agent_weights": {},
        "rejection_categories": [],
        "debate_history": [],
        "arbitration_result": "",
        "active_experts": [],
        "motivational_feedback": "",
        "profile_summary": "临床医学大三学生",
        "shared_memory_hits": [],
        "memory_entropy_scores": {},
        "consensus_result": {},
        "images": [],
        "vision_findings": None,
        "vision_evidence": "",
        "has_medical_images": False,
        "plan": {},
        "plan_rationale": "",
        "plan_results": [],
        "supervisor_trace": [],
    }
    state.update(overrides)
    return state


def _supervisor(llm=None):
    return TutorSupervisor(llm=llm or object(), retrieve_node=None, reason_node=None)


def test_extract_answer_returns_last_content_message():
    from langchain_core.messages import AIMessage, HumanMessage
    messages = [
        HumanMessage(content="问题"),
        AIMessage(content="", tool_calls=[{"name": "evidence_search", "args": {}, "id": "1"}]),
        AIMessage(content="最终答案：FAST 代表 Face/Arms/Speech/Time。"),
    ]
    assert "FAST" in TutorSupervisor._extract_answer(messages)


def test_extract_answer_falls_back_when_no_content():
    from langchain_core.messages import AIMessage, HumanMessage
    messages = [HumanMessage(content="问题"), AIMessage(content="", tool_calls=[{"name": "evidence_search", "args": {}, "id": "1"}])]
    answer = TutorSupervisor._extract_answer(messages)
    assert "无法给出有效回答" in answer


def test_build_trace_lists_tool_calls():
    from langchain_core.messages import AIMessage
    trace = TutorSupervisor._build_trace([
        AIMessage(content="", tool_calls=[{"name": "evidence_search", "args": {}, "id": "1"}]),
        AIMessage(content="回答内容"),
    ])
    assert trace[0]["tools"] == ["evidence_search"]
    assert trace[1]["role"] == "assistant"


def test_build_trace_captures_selection_reason():
    from langchain_core.messages import AIMessage
    trace = TutorSupervisor._build_trace([
        AIMessage(
            content="该问题需要内容生成与题目设计，故选文档撰写与题目生成两位专家。",
            tool_calls=[{"name": "consult_experts", "args": {}, "id": "1"}],
        ),
    ])
    assert trace[0]["tools"] == ["consult_experts"]
    assert "题目生成" in trace[0]["reason"]


def test_run_returns_fallback_when_agent_raises(monkeypatch):
    supervisor = _supervisor()

    class _BoomAgent:
        async def ainvoke(self, *args, **kwargs):
            raise RuntimeError("react agent boom")

    monkeypatch.setattr(supervisor, "_build_agent", lambda state: (_BoomAgent(), {"last_roles": [], "expert_advices": []}))
    result = asyncio.run(supervisor.run(_make_state()))
    assert "暂时不可用" in result["report"]
    assert result["supervisor_trace"] == []


def test_run_extracts_answer_from_messages(monkeypatch):
    from langchain_core.messages import AIMessage, HumanMessage
    supervisor = _supervisor()

    class _FakeAgent:
        async def ainvoke(self, *args, **kwargs):
            return {"messages": [
                HumanMessage(content="问题"),
                AIMessage(content="这是一个完整的辅导回答。"),
            ]}

    monkeypatch.setattr(supervisor, "_build_agent", lambda state: (_FakeAgent(), {"last_roles": [], "expert_advices": []}))
    result = asyncio.run(supervisor.run(_make_state()))
    assert result["report"] == "这是一个完整的辅导回答。"
    assert result["proposal"] == result["report"]


def test_build_agent_registers_three_tools(monkeypatch):
    captured = {}

    def _fake_create_react_agent(model, tools, prompt=None, **kwargs):
        captured["tools"] = tools
        captured["model"] = model
        captured["prompt"] = prompt
        return object()

    monkeypatch.setattr(
        "app.agents.orchestrators.supervisor.create_react_agent",
        _fake_create_react_agent,
    )
    supervisor = _supervisor(llm="fake-model")
    agent, workspace = supervisor._build_agent(_make_state())
    assert agent is not None
    assert "last_roles" in workspace
    assert len(captured["tools"]) == 3
    names = sorted(t.name for t in captured["tools"])
    assert names == ["consult_experts", "evidence_search", "get_student_profile"]
    assert "监督者" in captured["prompt"]
    assert "教学辅导" in captured["prompt"]
    assert "专家白名单" in captured["prompt"]
    assert "画像对话智能体" in captured["prompt"]
    # supervisor 最终回答要求结构化章节 + 学习激励段落
    assert "下一步建议" in captured["prompt"]
    assert "学习激励" in captured["prompt"]


class _FakeReasonNode:
    """记录点将名单并返回模拟专家发言与提案。"""

    def __init__(self):
        self.last_state = None

    async def run(self, state):
        self.last_state = dict(state)
        roles = self.last_state.get("active_experts_override", [])
        updates = {
            "active_experts": roles,
            "proposal": "综合提案内容。",
            "agent_messages": [
                {"from": "需求分析智能体", "to": "题目生成智能体", "round": 1,
                 "kind": "question", "content": "难度怎么定？"},
            ],
            "blackboard": [
                {"role": "需求分析智能体", "round": 1, "kind": "finding", "content": "先拆解需求。"},
            ],
            "convergence": "共识已达成。",
        }
        for role in roles:
            updates[f"{role}_advice"] = f"{role} 的发言。"
        return updates


def _capture_tools(monkeypatch):
    captured = {}

    def _fake_create_react_agent(model, tools, prompt=None, **kwargs):
        captured["tools"] = tools
        return object()

    monkeypatch.setattr(
        "app.agents.orchestrators.supervisor.create_react_agent",
        _fake_create_react_agent,
    )
    return captured


def test_consult_experts_filters_roles_to_whitelist_and_returns_speeches(monkeypatch):
    captured = _capture_tools(monkeypatch)
    fake_reason = _FakeReasonNode()
    supervisor = _supervisor(llm="fake-model")
    supervisor.reason_node = fake_reason
    _, workspace = supervisor._build_agent(_make_state())

    tool_map = {t.name: t for t in captured["tools"]}
    consult = tool_map["consult_experts"]

    result = asyncio.run(consult.ainvoke({
        "question": "怎么学好脑血管解剖？",
        "reason": "该问题需要解剖图谱与认知负荷管理，故选需求分析智能体。",
        "roles": ["需求分析智能体", "不存在的专家"],
    }))

    assert fake_reason.last_state["active_experts_override"] == ["需求分析智能体"]
    assert "【需求分析智能体】" in result
    assert "综合提案" in result
    assert "不存在的专家" not in result
    # reason 必须被记录，供学习链路以 supervisor_reason 流式送达前端审计
    assert workspace["last_reason"] == "该问题需要解剖图谱与认知负荷管理，故选需求分析智能体。"
    assert workspace["last_roles"] == ["需求分析智能体"]
    # M2+M3 对话-黑板结果经 workspace 透传（learning_agent 补发事件用）
    assert workspace["agent_messages"][0]["kind"] == "question"
    assert workspace["blackboard"][0]["role"] == "需求分析智能体"
    assert workspace["convergence"] == "共识已达成。"


def test_consult_experts_empty_roles_falls_back_to_rule_selection(monkeypatch):
    captured = _capture_tools(monkeypatch)
    fake_reason = _FakeReasonNode()
    supervisor = _supervisor(llm="fake-model")
    supervisor.reason_node = fake_reason
    supervisor._build_agent(_make_state())

    consult = {t.name: t for t in captured["tools"]}["consult_experts"]
    result = asyncio.run(consult.ainvoke({"question": "问题", "reason": "未指定名单，走规则兜底。", "roles": []}))

    assert "active_experts_override" not in fake_reason.last_state
    assert "综合提案" in result
