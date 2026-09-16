"""分歧门控单测：仅当专家意见存在实质分歧时才启动辩论+仲裁。

覆盖三层保证：
1. 白名单意图（profile）无条件辩论 —— 其争议无外部真理源，仲裁是证据纪律的唯一执行者；
2. 其余意图经分歧检测，无分歧则跳过 2(N-1)+1 次调用；
3. 任何异常/畸形输出一律 fail-open（照常辩论），绝不静默跳过审计。
"""
import asyncio
import json
from types import SimpleNamespace

import pytest

from app.agents.orchestrators.nodes.reason_node import ReasonNode

ROLES3 = ["需求分析智能体", "题目生成智能体", "学习激励智能体"]
OPINIONS3 = ["建议先讲解剖", "建议直接出题", "建议放慢节奏"]
TEMPLATE = "专家意见：\n{expert_opinions}\n请输出 JSON"


class _FakeExpertManager:
    def __init__(self, gate=True, intents=("profile",), template=TEMPLATE):
        self._gate = gate
        self._intents = list(intents)
        self._template = template

    def get_experts(self):
        return []

    def get_synthesis_config(self):
        return {}

    def get_debate_config(self):
        return {}

    def is_debate_enabled(self):
        return True

    def get_debate_max_rounds(self):
        return 1

    def get_arbitrator_role(self):
        return "仲裁智能体"

    def is_dynamic_orchestration_enabled(self):
        return False

    def is_dialogue_enabled(self):
        return True

    def is_conflict_gate_enabled(self):
        return self._gate

    def get_always_debate_intents(self):
        return list(self._intents)

    def get_conflict_prompt_template(self):
        return self._template


class _FakeJudge:
    """记录调用次数；可返回预设内容或抛异常。"""

    def __init__(self, content=None, raises=None):
        self.content = content
        self.raises = raises
        self.calls = 0
        self.last_prompt = ""

    async def ainvoke(self, messages):
        self.calls += 1
        self.last_prompt = messages[0].content
        if self.raises:
            raise self.raises
        return SimpleNamespace(content=self.content)


def _make_node(judge, gate=True, intents=("profile",), template=TEMPLATE):
    manager = _FakeExpertManager(gate=gate, intents=intents, template=template)
    return ReasonNode(llm=_FakeJudge(), expert_config=manager, llm_judge=judge)


def _decide(node, intent, roles=None, opinions=None):
    state = {"intent_type": intent}
    return asyncio.run(
        node._decide_debate(roles or ROLES3, opinions or OPINIONS3, state)
    )


# ── 1. 白名单意图无条件辩论 ────────────────────────────────────────────
def test_profile_always_debates_without_calling_judge():
    judge = _FakeJudge(content=json.dumps({"conflict": False, "reason": "看起来一致"}))
    node = _make_node(judge)
    run, note = _decide(node, "profile")
    assert run is True
    assert "强制辩论意图" in note
    assert judge.calls == 0, "白名单意图不应触发分歧检测调用"


def test_whitelist_is_read_from_config_not_hardcoded():
    """把白名单换成 resource 后，profile 应改走检测，resource 应无条件辩论。"""
    judge = _FakeJudge(content=json.dumps({"conflict": False, "reason": "一致"}))
    node = _make_node(judge, intents=("resource",))

    run_profile, _ = _decide(node, "profile")
    assert run_profile is False
    assert judge.calls == 1

    run_resource, note = _decide(node, "resource")
    assert run_resource is True
    assert "强制辩论意图" in note
    assert judge.calls == 1, "resource 直接放行，不应再调检测"


# ── 2. 分歧检测的正常判定 ──────────────────────────────────────────────
def test_no_conflict_skips_debate():
    judge = _FakeJudge(content=json.dumps({"conflict": False, "reason": "关注点互补"}))
    node = _make_node(judge)
    run, note = _decide(node, "tutor")
    assert run is False
    assert "无明显分歧" in note
    assert "关注点互补" in note
    assert judge.calls == 1


def test_conflict_triggers_debate():
    judge = _FakeJudge(content=json.dumps({"conflict": True, "reason": "对难度判断相反"}))
    node = _make_node(judge)
    run, note = _decide(node, "assessment")
    assert run is True
    assert "存在实质分歧" in note
    assert "对难度判断相反" in note


def test_judge_prompt_receives_all_opinions():
    judge = _FakeJudge(content=json.dumps({"conflict": False, "reason": "一致"}))
    node = _make_node(judge)
    _decide(node, "tutor")
    for role in ROLES3:
        assert role in judge.last_prompt
    assert "建议先讲解剖" in judge.last_prompt


def test_judge_output_in_markdown_fence_still_parsed():
    fenced = "```json\n" + json.dumps({"conflict": True, "reason": "相反"}) + "\n```"
    node = _make_node(_FakeJudge(content=fenced))
    run, _ = _decide(node, "tutor")
    assert run is True


# ── 3. fail-open：绝不静默跳过审计 ─────────────────────────────────────
def test_judge_exception_fails_open():
    node = _make_node(_FakeJudge(raises=RuntimeError("模型超时")))
    run, note = _decide(node, "tutor")
    assert run is True
    assert "保守放行" in note


def test_malformed_judge_output_fails_open():
    node = _make_node(_FakeJudge(content="我觉得他们差不多（非 JSON）"))
    run, note = _decide(node, "tutor")
    assert run is True
    assert "保守放行" in note


def test_missing_template_fails_open_without_calling_judge():
    judge = _FakeJudge(content=json.dumps({"conflict": False}))
    node = _make_node(judge, template="")
    run, note = _decide(node, "tutor")
    assert run is True
    assert "提示词缺失" in note
    assert judge.calls == 0


def test_gate_disabled_keeps_original_always_debate_behavior():
    judge = _FakeJudge(content=json.dumps({"conflict": False}))
    node = _make_node(judge, gate=False)
    run, note = _decide(node, "tutor")
    assert run is True
    assert "门控未启用" in note
    assert judge.calls == 0


# ── 4. 边界：无辩论对象 / 无有效意见 ───────────────────────────────────
def test_single_expert_skips_debate_without_calling_judge():
    judge = _FakeJudge(content=json.dumps({"conflict": True}))
    node = _make_node(judge)
    run, note = _decide(node, "tutor", roles=["需求分析智能体"], opinions=["建议"])
    assert run is False
    assert "仅 1 位专家" in note
    assert judge.calls == 0


def test_all_experts_failed_skips_debate():
    judge = _FakeJudge(content=json.dumps({"conflict": True}))
    node = _make_node(judge)
    run, note = _decide(node, "tutor", opinions=["未能获取有效建议"] * 3)
    assert run is False
    assert "无有效专家意见" in note
    assert judge.calls == 0


# ── 5. 与真实配置联动 ──────────────────────────────────────────────────
def test_real_config_declares_profile_as_always_debate():
    """真实 expert_config.yaml 必须把 profile 列入强制辩论白名单。

    profile 的争议'原则上不可消解'（关于学生的事实没有外部真理源），
    仲裁是 Claim/Evidence 纪律的唯一执行者——一旦被分歧门控跳过，
    证据三段式校验与画像写边界会整体失效。
    """
    from app.config.config_loader import get_expert_manager

    manager = get_expert_manager()
    assert manager.is_conflict_gate_enabled() is True
    assert "profile" in manager.get_always_debate_intents()
    assert "{expert_opinions}" in manager.get_conflict_prompt_template()


def test_real_config_gate_off_by_default_when_key_absent():
    """配置缺省时门控必须为关（保守）：宁可每次都辩论，不可静默跳过仲裁。"""
    from app.config.config_loader import ExpertConfigManager

    manager = ExpertConfigManager.__new__(ExpertConfigManager)
    manager._data = {"debate": {"enabled": True}}
    assert manager.is_conflict_gate_enabled() is False
    assert manager.get_always_debate_intents() == []
    assert manager.get_conflict_prompt_template() == ""
