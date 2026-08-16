"""ExecutorNode — 按计划逐步执行。

把 PlannerNode 生成的 ExecutionPlan 逐步派发给既有能力节点：
- analyze       → AnalysisNode（拆解需求/子问题）
- retrieve      → RetrieveNode（Hybrid RAG + 共享记忆；自动并入影像证据）
- expert_reason → ReasonNode（多专家并行 + 辩论仲裁 + 统筹汇总）
- finalize      → 结束标记，最终报告由 generate_report 节点生成

执行过程通过 LangGraph stream_writer 逐步骤推送 thinking 事件，
前端可在推理轨迹中实时看到「执行步骤 i/n」。
"""
import logging
from typing import Dict, List

from langgraph.config import get_stream_writer

from app.agents.core.schema import LearningState
from app.agents.orchestrators.nodes.base import BaseNode

logger = logging.getLogger(__name__)


class ExecutorNode(BaseNode):

    def __init__(self, retrieve_node, analysis_node, reason_node):
        self.retrieve_node = retrieve_node
        self.analysis_node = analysis_node
        self.reason_node = reason_node

    async def run(self, state: LearningState) -> Dict:
        plan = state.get("plan") or {}
        steps: List[dict] = plan.get("steps", []) if isinstance(plan, dict) else []
        if not steps:
            logger.warning("[executor] 状态中无执行计划，跳过执行")
            return {"plan_results": []}

        try:
            writer = get_stream_writer()
        except Exception:
            writer = None

        # working_state 在节点内部逐步合并子节点输出（节点内循环需要手工合并）
        working: dict = dict(state)
        merged: dict = {}
        plan_results: List[dict] = []

        for i, step in enumerate(steps):
            step_type = step.get("step_type", "")
            title = step.get("title") or step_type
            progress = f"执行步骤 {i + 1}/{len(steps)}：{title}"
            logger.info(f"[executor] {progress} (type={step_type})")

            if writer is not None:
                try:
                    writer({
                        "type": "thinking",
                        "thinking": {"step": "execute_plan", "title": progress},
                    })
                except Exception as e:
                    logger.debug(f"[executor] 推送步骤进度失败: {e}")

            if step_type == "finalize":
                plan_results.append(self._result(i, step, "finalize", "交给报告节点汇总生成"))
                break

            try:
                updates = await self._dispatch(step_type, working)
            except Exception as e:
                logger.error(f"[executor] 步骤 {i + 1} ({step_type}) 执行失败: {type(e).__name__}: {e}")
                plan_results.append(self._result(i, step, step_type, f"执行失败：{e}", failed=True))
                continue

            for key, value in (updates or {}).items():
                working[key] = value
                merged[key] = value

            plan_results.append(self._result(i, step, step_type, self._summarize(step_type, updates)))
            logger.info(f"[executor] 步骤 {i + 1}/{len(steps)} 完成: {step_type}")

        merged["plan_results"] = plan_results
        return merged

    async def _dispatch(self, step_type: str, working: dict) -> Dict:
        if step_type == "analyze":
            return await self.analysis_node.run(working) or {}
        if step_type == "retrieve":
            updates = await self.retrieve_node.run(working) or {}
            # 影像路径的影像证据并入循证材料
            vision_evidence = working.get("vision_evidence", "")
            if vision_evidence:
                evidence = updates.get("evidence", "") or ""
                if evidence:
                    updates["evidence"] = f"{evidence}\n\n--- 影像证据 ---\n{vision_evidence}"
                else:
                    updates["evidence"] = vision_evidence
            return updates
        if step_type == "expert_reason":
            return await self.reason_node.run(working) or {}
        return {}

    def _summarize(self, step_type: str, updates: Dict) -> str:
        if step_type == "analyze":
            return f"拆解出 {len(updates.get('learning_questions', []) or [])} 个学习子问题"
        if step_type == "retrieve":
            evidence = updates.get("evidence", "") or ""
            sources = updates.get("retrieval_sources", []) or []
            return f"检索到 {len(sources)} 条证据（{len(evidence)} 字符）"
        if step_type == "expert_reason":
            experts = updates.get("active_experts", []) or []
            debate = updates.get("debate_history", []) or []
            parts = [f"{len(experts)} 位专家完成推理"]
            if debate:
                parts.append(f"辩论 {len(debate)} 轮")
            return "，".join(parts)
        return "完成"

    @staticmethod
    def _result(index: int, step: dict, step_type: str, summary: str, failed: bool = False) -> dict:
        return {
            "index": index,
            "step_type": step_type,
            "title": step.get("title") or step_type,
            "summary": summary,
            "failed": failed,
        }
