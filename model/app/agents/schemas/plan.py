"""结构化执行计划 schema — Planner/Supervisor 架构的数据契约。

PlannerNode 用 LLM 生成 ExecutionPlan；步骤类型被严格限制在 PLAN_STEP_TYPES 白名单内，
LLM 只能在白名单内编排步骤，无法幻觉出越界动作。
"""
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

# 步骤类型白名单：每种类型对应 ExecutorNode 中的一个既有能力
# - analyze:        拆解学习需求/子问题（AnalysisNode）
# - retrieve:       脑卒中指南证据检索（RetrieveNode，Hybrid RAG + 共享记忆）
# - expert_reason:  多专家并行提案 + 辩论仲裁 + 统筹汇总（ReasonNode）
# - finalize:       结束标记，最终报告由 generate_report 节点生成
PLAN_STEP_TYPES = ("analyze", "retrieve", "expert_reason", "finalize")

STEP_TYPE_LITERAL = Literal["analyze", "retrieve", "expert_reason", "finalize"]

MAX_PLAN_STEPS = 6


class PlanStep(BaseModel):
    step_type: STEP_TYPE_LITERAL
    title: str = Field(..., description="步骤标题（用于前端 SSE 展示）")
    goal: str = Field("", description="该步骤要达成的目标")
    depends_on: List[int] = Field(
        default_factory=list, description="依赖的前置步骤序号（0-based）"
    )


class ExecutionPlan(BaseModel):
    steps: List[PlanStep] = Field(..., min_length=1, max_length=MAX_PLAN_STEPS)
    rationale: str = Field("", description="规划理由（审计与前端展示）")


def normalize_plan(plan: Optional[ExecutionPlan], intent_type: str = "") -> ExecutionPlan:
    """归一化 LLM 生成的计划：
    - 去掉超出白名单的步骤类型（防御性，pydantic 已限制，双保险）
    - 依赖序号越界/自依赖一律清除
    - 保证以 finalize 结尾（缺失则补，重复则只保留最后一个）
    """
    if plan is None or not getattr(plan, "steps", None):
        return build_default_plan(intent_type)

    steps: List[PlanStep] = []
    for step in plan.steps:
        if step.step_type not in PLAN_STEP_TYPES:
            continue
        deps = [
            d for d in step.depends_on
            if isinstance(d, int) and 0 <= d < MAX_PLAN_STEPS
        ]
        step.depends_on = deps
        steps.append(step)

    # 只保留最后一个 finalize 之前的内容（finalize 之后的内容无意义）
    finalize_idx = max((i for i, s in enumerate(steps) if s.step_type == "finalize"), default=-1)
    if finalize_idx >= 0 and finalize_idx < len(steps) - 1:
        steps = steps[: finalize_idx + 1]

    if not steps or steps[-1].step_type != "finalize":
        steps.append(PlanStep(
            step_type="finalize",
            title="汇总生成最终报告",
            goal="基于以上步骤的结果生成最终回答",
        ))

    return ExecutionPlan(steps=steps[:MAX_PLAN_STEPS], rationale=plan.rationale)


def build_default_plan(intent_type: str = "") -> ExecutionPlan:
    """规划失败或规划器禁用时的默认计划：等价于升级前的固定管线顺序。

    analysis → retrieve → expert_reason → finalize
    （RetrieveNode 内部对 profile_build/assessment/learning_path 自动跳过检索）
    """
    return ExecutionPlan(
        steps=[
            PlanStep(step_type="analyze", title="分析学习需求", goal="拆解问题、提取学习子问题与难度"),
            PlanStep(step_type="retrieve", title="检索循证资料", goal="检索脑卒中指南证据与共享记忆"),
            PlanStep(step_type="expert_reason", title="多专家推理与辩论", goal="专家并行提案、辩论仲裁、统筹汇总"),
            PlanStep(step_type="finalize", title="汇总生成最终报告", goal="生成最终回答"),
        ],
        rationale="默认计划（规划器不可用时的兜底，与升级前固定管线一致）",
    )


def plan_to_dict(plan: ExecutionPlan) -> Dict:
    return plan.model_dump()
