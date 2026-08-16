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


def test_run_returns_fallback_when_agent_raises(monkeypatch):
    supervisor = _supervisor()

    class _BoomAgent:
        async def ainvoke(self, *args, **kwargs):
            raise RuntimeError("react agent boom")

    monkeypatch.setattr(supervisor, "_build_agent", lambda state: _BoomAgent())
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

    monkeypatch.setattr(supervisor, "_build_agent", lambda state: _FakeAgent())
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
    supervisor._build_agent(_make_state())
    assert len(captured["tools"]) == 3
    names = sorted(t.name for t in captured["tools"])
    assert names == ["consult_experts", "evidence_search", "get_student_profile"]
    assert "监督者" in captured["prompt"]
    assert "教学辅导" in captured["prompt"]
