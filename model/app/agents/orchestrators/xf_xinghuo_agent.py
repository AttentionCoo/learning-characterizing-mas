import logging
import asyncio
import json
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
from app.agents.utils.reasoning_trace import build_node_trace
from app.utils.error_codes import build_error_event, format_error_log

logger = logging.getLogger(__name__)

_NODE_LABELS: Dict[str, str] = {
    "intent": "正在判断问题类型...",
    "reject": "正在处理回复...",
    "analysis": "正在分析学习需求...",
    "vision": "正在分析医学影像...",
    "retrieve": "正在检索教育参考资料...",
    "reason": "正在进行多智能体推理...",
    "validate": "正在进行质量校验...",
    "generate_report": "正在生成学习分析报告...",
    "knowledge_answer": "正在回答学习问题...",
}

_NODE_PROGRESS_LABELS: Dict[str, str] = {
    "analysis": "正在分析学习需求",
    "vision": "正在分析医学影像",
    "retrieve": "正在检索教育参考资料",
    "reason": "正在进行多智能体推理",
    "validate": "正在进行质量校验",
    "generate_report": "正在生成报告",
}

_REPORT_MODE_TO_INTENT: Dict[str, str] = REPORT_MODE_TO_INTENT


class LearningAgent:

    _STREAMING_NODES = {"knowledge_answer", "generate_report"}

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

        self._event_log_counts = {}

        self.graph = LearningGraphBuilder(
            intent_node=self.intent_node,
            analysis_node=self.analysis_node,
            retrieve_node=self.retrieve_node,
            reason_node=self.reason_node,
            validate_node=self.validate_node,
            report_node=self.report_node,
            vision_node=self.vision_node,
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
        }
        streamed_nodes: set = set()
        llm_call_counts: Dict[str, int] = {}

        try:
            import uuid
            config = {
                "configurable": {
                    "thread_id": uuid.uuid4().hex
                }
            }

            async for event in self.graph.astream_events(initial_state, config=config, version="v2"):
                translated = self._translate_event(event, show_thinking, streamed_nodes, llm_call_counts)
                if translated:
                    if translated.get("type") == "token":
                        node = event.get("metadata", {}).get("langgraph_node", "")
                        if node in self._STREAMING_NODES:
                            streamed_nodes.add(node)
                    yield translated
                    if (
                        show_thinking
                        and event.get("event") == "on_chain_end"
                        and event.get("name") in self._STREAMING_NODES
                        and translated.get("type") in {"token", "replace"}
                    ):
                        output = event.get("data", {}).get("output", {})
                        yield self._build_node_done_event(event.get("name", ""), output)

        except Exception as e:
            logger.error(f"学习推理管线异常 | {format_error_log(e)}")
            yield build_error_event(e, talk_id=None)

    def _translate_event(
        self,
        event: dict,
        show_thinking: bool,
        streamed_nodes: set,
        llm_call_counts: Dict[str, int],
    ) -> Dict:
        evt = event.get("event", "")
        name = event.get("name", "")
        meta = event.get("metadata", {})
        langgraph_node = meta.get("langgraph_node", "")

        log_key = f"{evt}:{name}:{langgraph_node}"
        log_count = self._event_log_counts.get(log_key, 0)
        if log_count < 10:
            self._event_log_counts[log_key] = log_count + 1
            logger.info(f"[event] 事件类型: {evt}, 节点名称: {name}, langgraph_node: {langgraph_node}")

        if evt == "on_chain_start" and name in _NODE_LABELS and show_thinking:
            llm_call_counts.pop(name, None)
            return {"type": "node_start", "node": name, "label": _NODE_LABELS[name]}

        if evt == "on_chain_end" and name in _NODE_LABELS:
            output = event.get("data", {}).get("output", {})
            report_text = output.get("report", "") if isinstance(output, dict) else ""

            logger.info(f"[event] 节点 {name} 完成，输出类型: {type(output)}")
            if isinstance(output, dict):
                logger.info(f"[event] 节点 {name} 输出键: {list(output.keys())}")
                if "report" in output:
                    logger.info(f"[event] 节点 {name} 报告长度: {len(output['report'])}")

            if name == "reject":
                return {"type": "token", "content": report_text} if report_text else None

            if name in self._STREAMING_NODES:
                if report_text:
                    if name not in streamed_nodes:
                        logger.info(f"[event] 节点 {name} 输出报告内容（首次），长度: {len(report_text)}")
                        streamed_nodes.add(name)
                        return {"type": "token", "content": report_text}

                    # 流式内容已经发送过，节点结束时用完整报告覆盖它。
                    # 既避免正常场景重复，也保留强化重试产生的最终版本。
                    logger.info(f"[event] 节点 {name} 使用完整报告替换流式内容，长度: {len(report_text)}")
                    return {"type": "replace", "content": report_text}

            if show_thinking:
                return self._build_node_done_event(name, output)

        if evt == "on_chat_model_stream" and langgraph_node in self._STREAMING_NODES:
            chunk = event.get("data", {}).get("chunk")
            if chunk is None:
                return None
            content = getattr(chunk, "content", None)
            # 兼容 content 为 None / 空字符串 / 非字符串类型
            if content is None:
                return None
            if not isinstance(content, str):
                content = str(content)
            if not content:
                return None
            return {"type": "token", "content": content}

        if evt == "on_chain_stream" and langgraph_node in self._STREAMING_NODES:
            chunk_data = event.get("data", {}).get("chunk")
            if chunk_data is None:
                return None
            if hasattr(chunk_data, "content"):
                content = chunk_data.content
                if content is None:
                    return None
                if not isinstance(content, str):
                    content = str(content)
                if not content:
                    return None
                return {"type": "token", "content": content}
            if isinstance(chunk_data, str):
                if not chunk_data:
                    return None
                return {"type": "token", "content": chunk_data}
            return None

        if evt == "on_chat_model_start" and langgraph_node and langgraph_node not in self._STREAMING_NODES:
            if show_thinking and langgraph_node in _NODE_PROGRESS_LABELS:
                llm_call_counts[langgraph_node] = llm_call_counts.get(langgraph_node, 0) + 1
                count = llm_call_counts[langgraph_node]
                base_label = _NODE_PROGRESS_LABELS[langgraph_node]
                progress_label = f"{base_label}...（思考中 #{count}）"
                logger.info(f"[event] 节点 {langgraph_node} LLM调用 #{count}")
                return {
                    "type": "thinking",
                    "thinking": {"step": langgraph_node, "title": progress_label},
                }

        if evt == "on_retriever_start" and langgraph_node == "retrieve" and show_thinking:
            return {
                "type": "thinking",
                "thinking": {
                    "step": "retrieve",
                    "title": "正在检索教育参考资料...（向量检索中）",
                },
            }

        return None

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
            result = self._parse_json(getattr(response, "content", ""), {}) or {}
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

    def _parse_json(self, text: str, default=None):
        content = (text or "").strip()
        try:
            return json.loads(content)
        except Exception:
            pass
        for marker in ["```json", "```"]:
            if marker in content:
                try:
                    s = content.split(marker)[1].split("```")[0].strip()
                    return json.loads(s)
                except Exception:
                    pass
        for sc, ec in [("{", "}"), ("[", "]")]:
            si, ei = content.find(sc), content.rfind(ec)
            if si != -1 and ei > si:
                try:
                    return json.loads(content[si:ei + 1])
                except Exception:
                    pass
        return default
