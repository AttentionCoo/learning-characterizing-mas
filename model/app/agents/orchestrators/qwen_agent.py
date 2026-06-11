import logging
import asyncio
import json
from typing import AsyncGenerator, Dict
from langchain_core.messages import SystemMessage, HumanMessage
from app.agents.core.schema import LearningState
from app.agents.orchestrators.clinical_graph import LearningGraphBuilder
from app.agents.orchestrators.nodes.intent_node import IntentNode
from app.agents.orchestrators.nodes.analysis_node import AnalysisNode
from app.agents.orchestrators.nodes.retrieve_node import RetrieveNode
from app.agents.orchestrators.nodes.reason_node import ReasonNode
from app.agents.orchestrators.nodes.validate_node import ValidateNode
from app.agents.orchestrators.nodes.report_node import ReportNode
from app.utils.error_codes import build_error_event, format_error_log

logger = logging.getLogger(__name__)

_NODE_LABELS: Dict[str, str] = {
    "intent": "正在判断问题类型...",
    "reject": "正在处理回复...",
    "analysis": "正在分析学习需求...",
    "retrieve": "正在检索教育参考资料...",
    "reason": "正在进行多智能体推理...",
    "validate": "正在进行质量校验...",
    "generate_report": "正在生成学习分析报告...",
    "knowledge_answer": "正在回答学习问题...",
}


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
    ):
        self.llm_proposer = llm_proposer
        self.llm_critic = llm_critic
        self.llm_turbo = llm_turbo or llm_critic
        self.learning_assistant = learning_assistant
        self.prompts = prompt_manager
        self.reports = report_manager

        self.intent_node = IntentNode(self.llm_turbo)
        self.analysis_node = AnalysisNode(self.llm_critic)
        self.retrieve_node = RetrieveNode(learning_assistant)
        self.reason_node = ReasonNode(self.llm_proposer)
        self.validate_node = ValidateNode(self.llm_critic)
        self.report_node = ReportNode(self.llm_proposer, report_manager)

        self.graph = LearningGraphBuilder(
            intent_node=self.intent_node,
            analysis_node=self.analysis_node,
            retrieve_node=self.retrieve_node,
            reason_node=self.reason_node,
            validate_node=self.validate_node,
            report_node=self.report_node,
            llm_critic=self.llm_critic,
            report_manager=self.reports,
        ).build()

    async def run_learning_reasoning(
        self,
        case_text: str,
        all_info: str = "",
        report_mode: str = "emergency",
        show_thinking: bool = True,
    ) -> AsyncGenerator[Dict, None]:
        initial_state: LearningState = {
            "case_text": case_text,
            "all_info": all_info,
            "report_mode": report_mode,
            "intent_type": "",
            "context": {},
            "learning_questions": [],
            "key_risks": [],
            "complexity": "high",
            "evidence": "",
            "proposal": "",
            "critique": "",
            "user_questions": [],
            "report": "",
            "expert_advices": {},
            "validation_passed": True,
            "validation_feedback": "",
            "reflection_count": 0
        }
        streamed_nodes: set = set()

        try:
            import uuid
            config = {
                "configurable": {
                    "thread_id": uuid.uuid4().hex
                }
            }

            async for event in self.graph.astream_events(initial_state, config=config, version="v2"):
                if (event.get("event") == "on_chat_model_stream"
                        and event.get("metadata", {}).get("langgraph_node", "")
                        in self._STREAMING_NODES):
                    streamed_nodes.add(
                        event["metadata"]["langgraph_node"]
                    )

                translated = self._translate_event(event, show_thinking, streamed_nodes)
                if translated:
                    yield translated

        except Exception as e:
            logger.error(f"学习推理管线异常 | {format_error_log(e)}")
            yield build_error_event(e, talk_id=None)

    def _translate_event(
        self,
        event: dict,
        show_thinking: bool,
        streamed_nodes: set,
    ) -> Dict:
        evt = event.get("event", "")
        name = event.get("name", "")
        meta = event.get("metadata", {})
        langgraph_node = meta.get("langgraph_node", "")

        logger.info(f"[event] 事件类型: {evt}, 节点名称: {name}, langgraph_node: {langgraph_node}")

        if evt == "on_chain_start" and name in _NODE_LABELS and show_thinking:
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

            if name in self._STREAMING_NODES and name not in streamed_nodes:
                if report_text:
                    logger.info(f"[event] 节点 {name} 输出报告内容，长度: {len(report_text)}")
                    streamed_nodes.add(name)
                    return {"type": "token", "content": report_text}

            if show_thinking:
                summary = self._node_summary(name, output)
                return {"type": "node_done", "node": name, "summary": summary}

        if evt == "on_chat_model_stream" and langgraph_node in self._STREAMING_NODES:
            chunk = event.get("data", {}).get("chunk")
            content = getattr(chunk, "content", "") if chunk else ""
            if content:
                return {"type": "token", "content": content}

        return None

    def _node_summary(self, node: str, output: dict) -> str:
        if not isinstance(output, dict):
            return ""
        if node == "analysis":
            q = output.get("learning_questions", [])
            return f"提取到 {len(q)} 个学习子问题"
        if node == "retrieve":
            ev = output.get("evidence", "")
            count = ev.count("---") + 1 if ev.strip() else 0
            return f"检索到 {count} 个参考片段"
        if node == "reason":
            return "多智能体推理完成"
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