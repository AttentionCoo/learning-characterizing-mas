"""Planner/Supervisor 架构单测：计划 schema 归一化、规划器降级、执行器派发、意图路由。"""
import asyncio
from types import SimpleNamespace

import pytest

from app.agents.core.schema import LearningState
from app.agents.orchestrators.clinical_graph import LearningGraphBuilder
from app.agents.schemas.plan import (
    ExecutionPlan,
    PlanStep,
    build_default_plan,
    normalize_plan,
)
from app.agents.orchestrators.nodes.planner_node import PlannerNode
from app.agents.orchestrators.nodes.executor_node import ExecutorNode


def _make_state(**overrides) -> LearningState:
    state = {
        "case_text": "测试问题",
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
        "profile_summary": "",
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


# ── 计划 schema ──────────────────────────────────────────────────────────────

def test_default_plan_ends_with_finalize():
    plan = build_default_plan("tutor")
    assert len(plan.steps) == 4
    assert plan.steps[-1].step_type == "finalize"
    assert plan.steps[0].step_type == "analyze"


def test_normalize_plan_appends_finalize_when_missing():
    plan = ExecutionPlan(
        steps=[PlanStep(step_type="expert_reason", title="专家推理")],
        rationale="简单问题",
    )
    normalized = normalize_plan(plan, "tutor")
    assert normalized.steps[-1].step_type == "finalize"
    assert len(normalized.steps) == 2


def test_normalize_plan_drops_out_of_range_dependencies():
    plan = ExecutionPlan(
        steps=[
            PlanStep(step_type="retrieve", title="检索", depends_on=[9, -1]),
            PlanStep(step_type="finalize", title="汇总"),
        ],
    )
    normalized = normalize_plan(plan, "tutor")
    assert normalized.steps[0].depends_on == []


def test_normalize_plan_truncates_after_finalize():
    plan = ExecutionPlan(
        steps=[
            PlanStep(step_type="expert_reason", title="推理"),
            PlanStep(step_type="finalize", title="汇总"),
            PlanStep(step_type="retrieve", title="多余步骤"),
        ],
    )
    normalized = normalize_plan(plan, "tutor")
    assert [s.step_type for s in normalized.steps] == ["expert_reason", "finalize"]


def test_normalize_plan_injects_expert_reason_when_missing():
    # 报告节点消费 expert_reason 的 proposal，缺少该步骤必须自动补齐
    plan = ExecutionPlan(
        steps=[
            PlanStep(step_type="analyze", title="需求分析"),
            PlanStep(step_type="finalize", title="汇总"),
        ],
        rationale="简单问题",
    )
    normalized = normalize_plan(plan, "profile")
    types = [s.step_type for s in normalized.steps]
    assert types == ["analyze", "expert_reason", "finalize"]


def test_normalize_plan_returns_default_when_none():
    plan = normalize_plan(None, "tutor")
    assert plan.steps[-1].step_type == "finalize"


# ── PlannerNode ─────────────────────────────────────────────────────────────

class _BrokenStructuredLLM:
    def with_structured_output(self, schema):
        class _Raiser:
            async def ainvoke(self, messages):
                raise RuntimeError("structured output failed")
        return _Raiser()

    async def ainvoke(self, messages):
        return SimpleNamespace(content="这不是 JSON")


def test_planner_falls_back_to_default_plan_on_failure():
    planner = PlannerNode(_BrokenStructuredLLM())
    result = asyncio.run(planner.run(_make_state()))
    plan = result["plan"]
    assert plan["steps"][-1]["step_type"] == "finalize"
    assert "回退" in result["plan_rationale"] or "失败" in result["plan_rationale"]


class _GoodStructuredLLM:
    def with_structured_output(self, schema):
        class _Plan:
            async def ainvoke(self, messages):
                return ExecutionPlan(
                    steps=[
                        PlanStep(step_type="retrieve", title="检索证据"),
                        PlanStep(step_type="expert_reason", title="专家推理"),
                    ],
                    rationale="先循证再推理",
                )
        return _Plan()

    async def ainvoke(self, messages):
        return SimpleNamespace(content="unused")


def test_planner_accepts_structured_plan():
    planner = PlannerNode(_GoodStructuredLLM())
    result = asyncio.run(planner.run(_make_state()))
    types = [s["step_type"] for s in result["plan"]["steps"]]
    assert types == ["retrieve", "expert_reason", "finalize"]
    assert "先循证再推理" in result["plan_rationale"]


def test_planner_disabled_returns_default():
    planner = PlannerNode(None, enabled=False)
    result = asyncio.run(planner.run(_make_state()))
    assert len(result["plan"]["steps"]) == 4


# ── ExecutorNode ────────────────────────────────────────────────────────────

class _FakeNode:
    def __init__(self, name, updates):
        self.name = name
        self.updates = updates
        self.calls = []

    async def run(self, state):
        self.calls.append(self.name)
        return dict(self.updates)


def test_executor_dispatch_order_and_merge():
    analyze = _FakeNode("analyze", {"learning_questions": ["子问题1"]})
    retrieve = _FakeNode("retrieve", {"evidence": "证据", "retrieval_sources": [{"source": "x"}]})
    reason = _FakeNode("expert_reason", {"proposal": "提案", "active_experts": ["专家A"]})
    executor = ExecutorNode(retrieve, analyze, reason)

    state = _make_state(plan={
        "steps": [
            {"step_type": "analyze", "title": "分析"},
            {"step_type": "retrieve", "title": "检索"},
            {"step_type": "expert_reason", "title": "推理"},
            {"step_type": "finalize", "title": "汇总"},
        ]
    })
    result = asyncio.run(executor.run(state))

    assert analyze.calls == ["analyze"]
    assert retrieve.calls == ["retrieve"]
    assert reason.calls == ["expert_reason"]
    assert result["evidence"] == "证据"
    assert result["proposal"] == "提案"
    assert len(result["plan_results"]) == 4
    assert result["plan_results"][0]["summary"] == "拆解出 1 个学习子问题"


class _FailingNode:
    async def run(self, state):
        raise RuntimeError("检索失败")


def test_executor_records_step_failure_and_continues():
    executor = ExecutorNode(_FailingNode(), _FakeNode("analyze", {}), _FakeNode("expert_reason", {}))
    state = _make_state(plan={
        "steps": [
            {"step_type": "retrieve", "title": "检索"},
            {"step_type": "finalize", "title": "汇总"},
        ]
    })
    result = asyncio.run(executor.run(state))
    assert result["plan_results"][0]["failed"] is True
    assert len(result["plan_results"]) == 2


# ── 意图路由 ────────────────────────────────────────────────────────────────

def _builder(supervisor=None, vision=None):
    return LearningGraphBuilder(
        intent_node=None,
        analysis_node=None,
        retrieve_node=None,
        reason_node=None,
        report_node=None,
        validate_node=None,
        vision_node=vision,
        planner_node=object(),
        executor_node=object(),
        supervisor_node=supervisor,
    )


def test_route_tutor_to_supervisor_when_enabled():
    builder = _builder(supervisor=object())
    assert builder._route_intent(_make_state(intent_type="tutor")) == "supervisor"


def test_route_tutor_to_planner_when_supervisor_disabled():
    builder = _builder(supervisor=None)
    assert builder._route_intent(_make_state(intent_type="tutor")) == "planner"


def test_route_profile_to_planner():
    builder = _builder()
    assert builder._route_intent(_make_state(intent_type="profile")) == "planner"


def test_route_code_assist_skips_planner():
    builder = _builder()
    assert builder._route_intent(_make_state(intent_type="code_assist")) == "generate_report"
