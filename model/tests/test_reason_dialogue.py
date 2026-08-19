"""对话-黑板编排器（M2+M3）单测：结构化消息解析、黑板修订、收敛、仲裁。"""
import asyncio
import json
from types import SimpleNamespace

import pytest

from app.agents.orchestrators.nodes.reason_dialogue import DialogueOrchestrator

ARBITRATOR = "仲裁智能体"
ROLES = ["需求分析智能体", "题目生成智能体", "学习激励智能体"]


class _FakeExpertManager:
    def get_expert_by_role(self, role):
        return {"role": role, "system_prompt": f"你是{role}"}


class _FakeLLM:
    """按顺序返回预设回复；用于模拟对话轮/收敛/仲裁。"""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    async def ainvoke(self, messages):
        self.calls += 1
        idx = min(self.calls, len(self.replies)) - 1
        return SimpleNamespace(content=self.replies[idx])


def _make_orchestrator(llm_replies, synthesis_replies):
    config = {
        "enabled": True,
        "max_rounds": 1,
        "arbitrator_role": ARBITRATOR,
        "dialogue_max_rounds": 2,
    }
    return DialogueOrchestrator(
        debate_config=config,
        arbitrator_role=ARBITRATOR,
        expert_manager=_FakeExpertManager(),
        llm=_FakeLLM(llm_replies),
        llm_synthesis=_FakeLLM(synthesis_replies),
        debate_max_rounds=1,
    )


def test_parse_messages_validates_kind_and_structure():
    orch = _make_orchestrator([], [])
    raw = json.dumps([
        {"kind": "question", "to": "题目生成智能体", "content": "题型如何匹配难度？"},
        {"kind": "badkind", "to": "x", "content": "非法类型应被过滤"},
        {"kind": "revise", "to": "__all__", "content": "修订我的意见"},
    ], ensure_ascii=False)
    messages = orch._parse_messages("需求分析智能体", raw, 1)

    assert len(messages) == 2
    assert messages[0]["from"] == "需求分析智能体"
    assert messages[0]["to"] == "题目生成智能体"
    assert messages[0]["kind"] == "question"
    assert messages[0]["round"] == 1
    assert messages[1]["kind"] == "revise"
    assert all(m["kind"] in ("question", "reply", "revise", "agree", "object", "finding") for m in messages)


def test_parse_messages_handles_empty_and_garbage():
    orch = _make_orchestrator([], [])
    assert orch._parse_messages("A", "", 1) == []
    assert orch._parse_messages("A", "不是JSON", 1) == []
    assert orch._parse_messages("A", "[]", 1) == []
    assert orch._parse_messages("A", '{"kind":"agree","to":"B","content":"认同"}', 1)[0]["kind"] == "agree"


def test_parse_messages_strips_markdown_fence():
    orch = _make_orchestrator([], [])
    raw = '```json\n[{"kind":"finding","to":"__all__","content":"新发现"}]\n```'
    messages = orch._parse_messages("A", raw, 1)
    assert len(messages) == 1
    assert messages[0]["kind"] == "finding"


def test_parse_messages_cleans_round_suffix_in_to():
    orch = _make_orchestrator([], [])
    raw = json.dumps([
        {"kind": "agree", "to": "画像对话智能体（第0轮）", "content": "认同画像思路"},
    ], ensure_ascii=False)
    messages = orch._parse_messages("需求分析智能体", raw, 1)
    assert messages[0]["to"] == "画像对话智能体"


def test_update_blackboard_replaces_latest_finding():
    orch = _make_orchestrator([], [])
    blackboard = [
        {"role": "需求分析智能体", "round": 0, "kind": "finding", "content": "旧版"},
    ]
    orch._update_blackboard(blackboard, "需求分析智能体", "修订版", 2)
    assert blackboard[0]["content"] == "修订版"
    assert blackboard[0]["round"] == 2
    assert len(blackboard) == 1


def test_update_blackboard_appends_when_missing():
    orch = _make_orchestrator([], [])
    blackboard = []
    orch._update_blackboard(blackboard, "需求分析智能体", "首次发现", 1)
    assert len(blackboard) == 1
    assert blackboard[0]["kind"] == "finding"


def test_run_returns_messages_blackboard_arbitration():
    # 第1轮：两位专家输出 question/revise；第2轮：无消息 → 提前收敛
    round1 = json.dumps([
        {"kind": "question", "to": "题目生成智能体", "content": "难度怎么定？"},
    ], ensure_ascii=False)
    orch = _make_orchestrator(
        [round1, round1, "[]", "[]", "[]", "[]"],
        ["收敛结论：共识已达成。", "仲裁裁决：以证据为准。"],
    )
    result = asyncio.run(orch.run(
        ROLES,
        ["需求分析：先拆解。", "题目生成：出题。", "激励：鼓励。"],
        "学习资料",
        "证据链",
        [],
        [],
        [],
    ))

    assert result["agent_messages"], "应至少产生一条结构化消息"
    first = result["agent_messages"][0]
    assert first["from"] == "需求分析智能体"
    assert first["kind"] == "question"
    assert first["to"] == "题目生成智能体"
    # 黑板包含全部专家的初始发现（仲裁角色除外）
    findings = [e for e in result["blackboard"] if e.get("kind") == "finding"]
    assert len(findings) == 3
    assert "收敛结论" in result["convergence"]
    assert "仲裁裁决" in result["arbitration_result"]


def test_run_handles_exception_in_dialogue_round():
    class _BoomLLM:
        async def ainvoke(self, messages):
            raise RuntimeError("llm down")

    orch = DialogueOrchestrator(
        debate_config={"enabled": True, "max_rounds": 1, "arbitrator_role": ARBITRATOR,
                       "dialogue_max_rounds": 1},
        arbitrator_role=ARBITRATOR,
        expert_manager=_FakeExpertManager(),
        llm=_BoomLLM(),
        llm_synthesis=_FakeLLM(["仲裁兜底。"]),
        debate_max_rounds=1,
    )
    result = asyncio.run(orch.run(
        ["需求分析智能体", "题目生成智能体"],
        ["A意见", "B意见"],
        "资料",
        "证据",
        [],
        [],
        [],
    ))
    # 异常被吞掉，黑板仍保留初稿，仲裁仍执行
    assert len(result["blackboard"]) == 2
    assert "仲裁" in result["arbitration_result"]


def test_run_convergence_skipped_when_single_expert():
    orch = _make_orchestrator([], [])
    convergence = asyncio.run(orch._run_convergence(
        [{"role": "需求分析智能体", "kind": "finding", "content": "唯一发现"}],
        [],
        "资料",
        "证据",
    ))
    assert convergence == ""


def test_arbitration_prompt_includes_dialogue_and_findings():
    """仲裁 prompt 必须包含专家对话记录与黑板发现，而非只有辩论记录/证据。

    回归：YAML 模板曾只含 {debate_history}/{evidence} 占位符，
    format() 多余参数被静默忽略，导致仲裁只看到空记录而无法评估。
    """
    from app.config.config_loader import get_expert_manager
    mgr = get_expert_manager()
    yaml_template = mgr.get_debate_config().get("arbitration_prompt_template", "")

    assert "{agent_messages}" in yaml_template
    assert "{findings}" in yaml_template
    assert "{debate_history}" in yaml_template
    assert "{evidence}" in yaml_template

    # 用 YAML 模板实际渲染，确认对话与黑板内容进入 prompt
    orch = _make_orchestrator([], [])
    orch.debate_config = mgr.get_debate_config()
    rendered = yaml_template.format(
        agent_messages="第1轮 需求分析智能体 → 题目生成智能体 [question]: 难度怎么定？",
        findings="需求分析智能体: 先拆解需求。",
        debate_history="（无）",
        evidence="无",
    )
    assert "需求分析智能体 → 题目生成智能体" in rendered
    assert "先拆解需求" in rendered
