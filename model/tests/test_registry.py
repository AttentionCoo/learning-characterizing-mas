"""专家注册表（Specialist Agent Registry）测试。"""
from types import SimpleNamespace

import pytest

from app.agents.registry import AgentRegistry, SpecialistAgent


def _fake_react_agent(model, tools, prompt):
    async def fake_ainvoke(inputs, config=None):
        return {"messages": [
            SimpleNamespace(content=""),
            SimpleNamespace(content="专家最终发言"),
        ]}

    return SimpleNamespace(ainvoke=fake_ainvoke)


def _tool_factory():
    from app.agents.tools import build_expert_tools
    return build_expert_tools({"evidence": "证据片段", "profile_summary": "大三"})


def test_registry_builds_addressable_agents(monkeypatch):
    monkeypatch.setattr("app.agents.registry.create_react_agent", _fake_react_agent)
    configs = [
        {"role": "需求分析智能体", "system_prompt": "sp1", "tools": ["lookup_evidence"]},
        {"role": "仲裁智能体", "system_prompt": "sp2", "tools": []},
    ]
    registry = AgentRegistry("fake-llm", configs, _tool_factory)

    assert set(registry.roles()) == {"需求分析智能体", "仲裁智能体"}
    assert registry.get("需求分析智能体") is not None
    assert registry.get("不存在的专家") is None


@pytest.mark.asyncio
async def test_specialist_agent_run_returns_final_answer(monkeypatch):
    monkeypatch.setattr("app.agents.registry.create_react_agent", _fake_react_agent)
    agent = SpecialistAgent("需求分析智能体", "sp", "fake-llm", [], max_rounds=4)

    result = await agent.run("分析这个需求")

    assert result == "专家最终发言"
    assert len(agent.history) == 1  # 请求内会话记忆保留


@pytest.mark.asyncio
async def test_specialist_agent_run_failure_returns_fallback(monkeypatch):
    def failing_agent(model, tools, prompt):
        async def fake_ainvoke(inputs, config=None):
            raise RuntimeError("llm down")

        return SimpleNamespace(ainvoke=fake_ainvoke)

    monkeypatch.setattr("app.agents.registry.create_react_agent", failing_agent)
    agent = SpecialistAgent("仲裁智能体", "sp", "fake-llm", [])

    result = await agent.run("x")

    assert result == "未能获取仲裁智能体建议。"
