import logging
import asyncio
from typing import AsyncGenerator, Dict
from langchain_core.messages import SystemMessage, HumanMessage
from app.agents.core.schema import LearningState
from app.agents.orchestrators.clinical_graph import LearningGraphBuilder
from app.agents.orchestrators.nodes.intent_node import IntentNode, REPORT_MODE_TO_INTENT
from app.agents.orchestrators.nodes.analysis_node import AnalysisNode
from app.agents.orchestrators.nodes.retrieve_node import RetrieveNode
from app.agents.orchestrators.nodes.reason_node import ReasonNode
from app.agents.orchestrators.nodes.validate_node import ValidateNode
from app.agents.orchestrators.nodes.report_node import ReportNode
from app.agents.orchestrators.nodes.planner_node import PlannerNode
from app.agents.orchestrators.nodes.executor_node import ExecutorNode
from app.agents.orchestrators.supervisor import TutorSupervisor, SUPERVISOR_TUTOR_ENABLED
from app.agents.utils.reasoning_trace import build_node_trace
from app.agents.utils.json_parser import JsonParser
from app.utils.error_codes import build_error_event, format_error_log

logger = logging.getLogger(__name__)

_NODE_LABELS: Dict[str, str] = {
    "intent": "正在判断问题类型...",
    "reject": "正在处理回复...",
    "analysis": "正在分析学习需求...",
    "vision": "正在分析医学影像...",
    "retrieve": "正在检索教育参考资料...",
    "reason": "正在进行多智能体推理...",
    "planner": "正在规划任务步骤...",
    "execute_plan": "正在按计划执行...",
    "supervisor": "监督者正在调度工具...",
    "validate": "正在进行质量校验...",
    "generate_report": "正在生成学习分析报告...",
    "knowledge_answer": "正在回答学习问题...",
}

_NODE_PROGRESS_LABELS: Dict[str, str] = {
    "analysis": "正在分析学习需求",
    "vision": "正在分析医学影像",
    "retrieve": "正在检索教育参考资料",
    "reason": "正在进行多智能体推理",
    "planner": "正在规划任务步骤",
    "supervisor": "监督者调度中",
    "validate": "正在进行质量校验",
    "generate_report": "正在生成报告",
}

_REPORT_MODE_TO_INTENT: Dict[str, str] = REPORT_MODE_TO_INTENT


class LearningAgent:

    _STREAMING_NODES = {"knowledge_answer", "generate_report", "supervisor"}

    def __init__(
        self,
        llm_proposer,
        llm_critic,
        learning_assistant,
        prompt_manager,
        report_manager,
        llm_turbo=None,
        shared_memory_system=None,
        vision_node=None,
    ):
        self.llm_proposer = llm_proposer
        self.llm_critic = llm_critic
        self.llm_turbo = llm_turbo or llm_critic
        self.learning_assistant = learning_assistant
        self.prompts = prompt_manager
        self.reports = report_manager
        self.shared_memory_system = shared_memory_system
        self.vision_node = vision_node

        self.intent_node = IntentNode(self.llm_turbo)
        self.analysis_node = AnalysisNode(self.llm_critic)
        self.retrieve_node = RetrieveNode(learning_assistant, shared_memory_system=shared_memory_system)
        self.reason_node = ReasonNode(self.llm_critic, llm_synthesis=self.llm_proposer, shared_memory_system=shared_memory_system)
        self.validate_node = ValidateNode(self.llm_critic, shared_memory_system=shared_memory_system)
        self.report_node = ReportNode(self.llm_proposer, report_manager)

        # Planner/Supervisor 架构
        self.planner_node = PlannerNode(self.llm_turbo)
        self.executor_node = ExecutorNode(self.retrieve_node, self.analysis_node, self.reason_node)
        self.supervisor_node = None
        if SUPERVISOR_TUTOR_ENABLED:
            try:
                self.supervisor_node = TutorSupervisor(
                    llm=self.llm_turbo,
                    retrieve_node=self.retrieve_node,
                    reason_node=self.reason_node,
                )
                logger.info("[agent] Tutor 监督者已启用 (SUPERVISOR_TUTOR_ENABLED=true)")
            except Exception as e:
                logger.warning(f"[agent] 监督者初始化失败，tutor 回退 planner 链路: {e}")

        self._event_log_counts = {}

        self.graph = LearningGraphBuilder(
            intent_node=self.intent_node,
            analysis_node=self.analysis_node,
            retrieve_node=self.retrieve_node,
            reason_node=self.reason_node,
            validate_node=self.validate_node,
            report_node=self.report_node,
            vision_node=self.vision_node,
            planner_node=self.planner_node,
            executor_node=self.executor_node,
            supervisor_node=self.supervisor_node,
            llm_critic=self.llm_critic,
            report_manager=self.reports,
            shared_memory_system=shared_memory_system,
        ).build()

    async def run_learning_reasoning(
        self,
        case_text: str,
        all_info: str = "",
        report_mode: str = "emergency",
        show_thinking: bool = True,
        profile_summary: str = "",
        images: list = None,
    ) -> AsyncGenerator[Dict, None]:
        if report_mode not in _REPORT_MODE_TO_INTENT:
            yield {
                "type": "token",
                "content": f"不支持的功能类型「{report_mode}」，请求已被拦截。",
            }
            return

        if not profile_summary and all_info:
            profile_summary = all_info

        preset_intent = _REPORT_MODE_TO_INTENT.get(report_mode, "")

        initial_state: LearningState = {
            "case_text": case_text,
            "all_info": all_info,
            "report_mode": report_mode,
            "intent_type": preset_intent,
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
            "profile_summary": profile_summary,
            "shared_memory_hits": [],
            "memory_entropy_scores": {},
            "consensus_result": {},
            "images": images or [],
            "vision_findings": None,
            "vision_evidence": "",
            "has_medical_images": bool(images) if images else False,
            "plan": {},
            "plan_rationale": "",
            "plan_results": [],
            "supervisor_trace": [],
            "supervisor_roles": [],
            "expert_advices": [],
        }
        streamed_nodes: set = set()

        try:
            import uuid
            config = {
                "configurable": {
                    "thread_id": uuid.uuid4().hex
                }
            }

            # 三通道流式：custom=节点中途事件 / updates=节点完成输出 / messages=LLM token 流
            async for mode, chunk in self.graph.astream(
                initial_state,
                config=config,
                stream_mode=["custom", "updates", "messages"],
            ):
                # ── custom：推理链中途事件（逐步骤/逐专家/辩论/提案/校验反馈实时打印）──
                if mode == "custom":
                    data = chunk
                    if not isinstance(data, dict) or not data.get("type"):
                        continue
                    evt_type = data["type"]

                    if evt_type == "node_start":
                        node = data.get("node", "")
                        label = _NODE_LABELS.get(node, "")
                        if label and show_thinking:
                            yield {"type": "node_start", "node": node, "label": label}
                        continue

                    if evt_type == "thinking":
                        if show_thinking:
                            yield data
                        continue

                    if evt_type == "experts_selected":
                        # 专家名单先行到达（发言随后逐条到达）；selection_reason 为点将/编排依据
                        yield {
                            "type": "experts",
                            "node": data.get("node", "reason"),
                            "active_experts": data.get("active_experts", []),
                            "advices": [],
                            "debate_rounds": 0,
                            "arbitration": "",
                            "selection_reason": data.get("reason", ""),
                        }
                        continue

                    if evt_type == "expert_done":
                        # 每位专家完成即流式推送其完整发言
                        yield {
                            "type": "thinking",
                            "thinking": {
                                "step": data.get("node", "reason"),
                                "title": "专家发言 {}/{}：{}".format(
                                    data.get("index"), data.get("total"), data.get("role")
                                ),
                                "content": data.get("content", ""),
                            },
                        }
                        continue

                    if evt_type == "debate":
                        yield {
                            "type": "debate",
                            "node": data.get("node", "reason"),
                            "rounds": data.get("rounds", 0),
                            "history": data.get("history", []),
                            "arbitration": data.get("arbitration", ""),
                        }
                        continue

                    if evt_type == "proposal":
                        # 综合提案与风险批判全文
                        yield {
                            "type": "thinking",
                            "thinking": {
                                "step": data.get("node", "reason"),
                                "title": "综合提案与风险批判",
                                "content": "【提案】\n{}\n\n【批判】\n{}".format(
                                    data.get("proposal", ""), data.get("critique", "")
                                ),
                            },
                        }
                        continue

                    logger.debug("[stream] 未识别的 custom 事件类型: %s", evt_type)
                    continue

                # ── updates：节点完成输出 ──
                if mode == "updates":
                    for node_name, output in chunk.items():
                        if not isinstance(output, dict):
                            continue
                        if node_name == "reject":
                            report_text = output.get("report", "")
                            if report_text:
                                yield {"type": "token", "content": report_text}
                            continue
                        # supervisor 是流式节点，需在其报告输出之外补发点将 events 事件，
                        # 因此必须在 _STREAMING_NODES 分支之前处理
                        if node_name == "supervisor":
                            # 监督者点将名单 + 专家发言 + 选人理由（experts 事件）
                            roles = output.get("supervisor_roles") or []
                            advices = output.get("expert_advices") or []
                            trace_items = output.get("supervisor_trace") or []
                            reasons = [
                                t.get("reason", "") for t in trace_items
                                if isinstance(t, dict) and t.get("reason")
                            ]
                            if roles:
                                logger.info(
                                    "[event] ✅ 推送 supervisor 点将结果到前端 (roles=%s, advices=%s, reasons=%s)",
                                    roles, len(advices), len(reasons),
                                )
                                yield {
                                    "type": "experts",
                                    "node": "supervisor",
                                    "active_experts": roles,
                                    "advices": advices,
                                    "debate_rounds": 0,
                                    "arbitration": "",
                                    "selection_reason": "；".join(reasons),
                                }
                            report_text = output.get("report", "")
                            if report_text:
                                if node_name not in streamed_nodes:
                                    streamed_nodes.add(node_name)
                                    yield {"type": "token", "content": report_text}
                                else:
                                    yield {"type": "replace", "content": report_text}
                            if show_thinking:
                                yield self._build_node_done_event(node_name, output)
                            continue
                        if node_name in self._STREAMING_NODES:
                            report_text = output.get("report", "")
                            if report_text:
                                if node_name not in streamed_nodes:
                                    streamed_nodes.add(node_name)
                                    yield {"type": "token", "content": report_text}
                                else:
                                    yield {"type": "replace", "content": report_text}
                            if show_thinking:
                                yield self._build_node_done_event(node_name, output)
                            continue
                        if show_thinking:
                            yield self._build_node_done_event(node_name, output)
                    continue

                # ── messages：流式 token（仅最终报告类节点；supervisor 内部推理文本不外泄，其答案由 updates 端到端替换）──
                if mode == "messages":
                    message_chunk, metadata = chunk
                    langgraph_node = (metadata or {}).get("langgraph_node", "")
                    if langgraph_node not in {"generate_report", "knowledge_answer"}:
                        continue
                    content = getattr(message_chunk, "content", None)
                    if content is None:
                        continue
                    if not isinstance(content, str):
                        content = str(content)
                    if not content:
                        continue
                    streamed_nodes.add(langgraph_node)
                    yield {"type": "token", "content": content}
                    continue

        except Exception as e:
            logger.error(f"学习推理管线异常 | {format_error_log(e)}")
            yield build_error_event(e, talk_id=None)

    def _build_node_done_event(self, name: str, output: dict) -> Dict:
        summary = self._node_summary(name, output)
        trace = build_node_trace(name, output)
        for source in trace.get("sources", []):
            logger.debug(
                "[RAG依据] 指南=%s | 页码=%s",
                source.get("guide", "未知指南"),
                source.get("page", "?"),
            )
        return {
            "type": "node_done",
            "node": name,
            "summary": summary,
            **trace,
        }

    def _build_debate_event(self, output: dict):
        """把 reason 节点的辩论记录 + 仲裁裁决封装成前端流事件。"""
        if not isinstance(output, dict):
            return None
        debate_history = output.get("debate_history", []) or []
        arbitration = output.get("arbitration_result", "") or ""
        if not debate_history and not arbitration:
            return None
        return {
            "type": "debate",
            "node": "reason",
            "rounds": len(debate_history),
            "history": debate_history,
            "arbitration": arbitration,
        }

    @staticmethod
    def _build_experts_event(output: dict):
        """把 reason 节点的参与专家名单与各专家发言封装成前端可审计事件。

        专家发言存放在 `{role}_advice` 键中（ReasonNode 的返回结构）。
        """
        if not isinstance(output, dict):
            return None
        active = output.get("active_experts", []) or []
        advices = []
        for role in active:
            advice = output.get(f"{role}_advice", "") or ""
            if advice and not advice.startswith("未能获取"):
                advices.append({"role": role, "content": advice})
        if not active and not advices:
            return None
        return {
            "type": "experts",
            "node": "reason",
            "active_experts": active,
            "advices": advices,
            "debate_rounds": len(output.get("debate_history", []) or []),
            "arbitration": output.get("arbitration_result", "") or "",
        }

    def _node_summary(self, node: str, output: dict) -> str:
        if not isinstance(output, dict):
            return ""
        if node == "vision":
            findings = output.get("vision_findings")
            has_findings = findings and isinstance(findings, dict) and len(findings) > 0
            if has_findings:
                img_type = findings.get("image_type", "未知")
                key_count = len(findings.get("key_findings", []))
                return f"医学影像分析完成（{img_type}，{key_count} 项关键发现）"
            return "医学影像分析完成"
        if node == "analysis":
            q = output.get("learning_questions", [])
            return f"提取到 {len(q)} 个学习子问题"
        if node == "retrieve":
            ev = output.get("evidence", "")
            count = ev.count("---") + 1 if ev.strip() else 0
            return f"检索到 {count} 个参考片段"
        if node == "reason":
            active = output.get("active_experts", [])
            debate_history = output.get("debate_history", [])
            parts = [f"多智能体推理完成 ({len(active)} 位专家)"]
            if debate_history:
                parts.append(f"辩论 {len(debate_history)} 轮")
            return "，".join(parts)
        if node == "validate":
            return "质量校验完成"
        if node == "planner":
            plan = output.get("plan", {}) or {}
            steps = plan.get("steps", []) if isinstance(plan, dict) else []
            titles = "、".join(s.get("title", s.get("step_type", "")) for s in steps if isinstance(s, dict))
            rationale = output.get("plan_rationale", "") or ""
            summary = f"规划完成（{len(steps)} 步：{titles}）"
            if rationale and "回退" in rationale:
                summary += f"（{rationale[:40]}）"
            return summary
        if node == "execute_plan":
            results = output.get("plan_results", []) or []
            done = [r for r in results if not r.get("failed")]
            titles = "、".join(r.get("title", "") for r in results if r.get("title"))
            return f"按计划执行完成（{len(done)}/{len(results)} 步：{titles}）"
        if node == "supervisor":
            trace = output.get("supervisor_trace", []) or []
            tool_calls = sum(1 for m in trace if m.get("tools"))
            return f"监督者调度完成（{tool_calls} 次工具调用）"
        if node == "generate_report":
            report = output.get("report", "")
            return f"生成报告，长度: {len(report)} 字符"
        return ""

    async def analyze_learning_risk_fast(self, student_data: str) -> Dict[str, str]:
        prompt = f"""你是资深学习风险评估专家。请基于以下学生信息，快速给出学习风险结论。

学生信息：{student_data}

请直接输出 JSON，不要任何解释、不要 markdown 代码块：

{{
    "riskLevel": "低风险/中风险/高风险",
    "suggestion": "一句到两句实用学习建议",
    "analysisDetails": "简要说明主要风险依据（控制在80字以内）"
}}

要求：
- riskLevel 必须是：低风险、中风险、高风险之一
- suggestion 简洁、可执行
- analysisDetails 聚焦关键学习问题"""

        try:
            response = await self.llm_critic.ainvoke([HumanMessage(content=prompt)])
            result = JsonParser.parse(getattr(response, "content", ""), {}) or {}
            payload = {
                "riskLevel": result.get("riskLevel", "中风险"),
                "suggestion": result.get("suggestion", "建议结合学习情况进一步评估。"),
                "analysisDetails": result.get("analysisDetails", "基于学生提供的信息完成初步风险评估。"),
            }
            normalize = {"高": "高风险", "中": "中风险", "低": "低风险"}
            if payload["riskLevel"] in normalize:
                payload["riskLevel"] = normalize[payload["riskLevel"]]
            logger.info(f"[AILearningAnalyzeFast] riskLevel={payload['riskLevel']}")
            return payload
        except Exception as e:
            logger.error(f"[AILearningAnalyzeFast] failed: {e}")
            return {
                "riskLevel": "中风险",
                "suggestion": "建议结合学习情况进一步评估。",
                "analysisDetails": "系统已完成基础风险评估，但详细分析生成失败。",
            }
