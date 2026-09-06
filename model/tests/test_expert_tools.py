"""专家工具集与专家 Agent 化测试。"""
from types import SimpleNamespace

import pytest

from app.agents.tools import build_expert_tools
from app.agents.orchestrators.nodes.reason_node import ReasonNode


def test_lookup_evidence_filters_by_keyword():
    tools = build_expert_tools({
        "evidence": "脑卒中指南：静脉溶栓时间窗4.5小时\n脑血管解剖：MCA供应额顶叶",
        "profile_summary": "临床医学 大三",
    })

    result = tools["lookup_evidence"].invoke({"query": "溶栓 时间窗"})

    assert "4.5小时" in result


def test_get_student_profile_returns_profile():
    tools = build_expert_tools({"profile_summary": "临床医学 大三"})

    assert "临床医学" in tools["get_student_profile"].invoke({})


def test_retrieve_shared_memory_unavailable_without_system():
    tools = build_expert_tools({})

    assert tools["retrieve_shared_memory"].invoke({"query": "x"}) == "共享记忆不可用"


def test_lookup_evidence_empty_when_no_evidence():
    tools = build_expert_tools({})

    assert tools["lookup_evidence"].invoke({"query": "x"}) == "当前无已检索证据"


@pytest.mark.asyncio
async def test_ask_expert_with_tools_uses_react_agent(monkeypatch):
    captured = {}

    def fake_create_react_agent(model, tools, prompt):
        captured["tools"] = tools
        captured["prompt"] = prompt

        async def fake_ainvoke(inputs, config=None):
            return {"messages": [
                SimpleNamespace(content=""),
                SimpleNamespace(content="工具调用后的最终发言"),
            ]}

        return SimpleNamespace(ainvoke=fake_ainvoke)

    monkeypatch.setattr("langgraph.prebuilt.create_react_agent", fake_create_react_agent)

    node = SimpleNamespace(llm="fake", shared_memory_system=None)

    async def fake_single(role, sp, prompt):
        return "single"

    node._ask_expert_single = fake_single

    result = await ReasonNode._ask_expert_with_tools(
        node, "需求分析智能体", "系统提示", "提示词", ["lookup_evidence"], {}, None,
    )

    assert result == "工具调用后的最终发言"
    assert len(captured["tools"]) == 1


@pytest.mark.asyncio
async def test_ask_expert_with_tools_falls_back_when_no_tool_available(monkeypatch):
    node = SimpleNamespace(llm="fake", shared_memory_system=None)
    calls = []

    async def fake_single(role, sp, prompt):
        calls.append(role)
        return "single"

    node._ask_expert_single = fake_single

    # 声明的工具不存在 → 回退单次调用
    result = await ReasonNode._ask_expert_with_tools(
        node, "需求分析智能体", "sp", "p", ["nonexistent_tool"], {}, None,
    )

    assert result == "single"
    assert calls == ["需求分析智能体"]
