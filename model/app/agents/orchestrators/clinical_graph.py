import logging
from langgraph.graph import StateGraph, END
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from app.agents.core.schema import LearningState
from app.agents.orchestrators.nodes.intent_node import IntentNode
from app.agents.orchestrators.nodes.analysis_node import AnalysisNode
from app.agents.orchestrators.nodes.retrieve_node import RetrieveNode
from app.agents.orchestrators.nodes.reason_node import ReasonNode
from app.agents.orchestrators.nodes.report_node import ReportNode
from app.agents.orchestrators.nodes.validate_node import ValidateNode
from app.config.config_loader import get_validation_manager

logger = logging.getLogger(__name__)


class LearningGraphBuilder:

    def __init__(
        self,
        intent_node: IntentNode,
        analysis_node: AnalysisNode,
        retrieve_node: RetrieveNode,
        reason_node: ReasonNode,
        report_node: ReportNode,
        validate_node: ValidateNode = None,
        llm_critic=None,
        report_manager=None,
    ):
        self.intent_node = intent_node
        self.analysis_node = analysis_node
        self.retrieve_node = retrieve_node
        self.reason_node = reason_node
        self.report_node = report_node
        self.validate_node = validate_node
        self.llm_critic = llm_critic
        self.report_manager = report_manager

        self.validation_manager = get_validation_manager()
        self.max_reflection_count = self.validation_manager.get_max_reflection_count()

        self.checkpointer = MemorySaver()

    def build(self):
        graph = StateGraph(LearningState)

        graph.add_node("intent", self.intent_node.run)
        graph.add_node("reject", self._reject_node)
        graph.add_node("knowledge_answer", self._knowledge_node)
        graph.add_node("analysis", self.analysis_node.run)
        graph.add_node("retrieve", self.retrieve_node.run)
        graph.add_node("reason", self.reason_node.run)

        if self.validate_node:
            graph.add_node("validate", self.validate_node.run)

        graph.add_node("generate_report", self.report_node.run)

        graph.set_entry_point("intent")

        graph.add_conditional_edges(
            "intent",
            self._route_intent,
            {
                "non_stroke": "reject",
                "irrelevant": "reject",
                "knowledge": "knowledge_answer",
                "profile": "analysis",
                "resource": "analysis",
                "tutor": "analysis",
                "assessment": "analysis",
                "learning_path": "analysis",
                "consultation": "analysis",
            }
        )

        graph.add_edge("reject", END)
        graph.add_edge("knowledge_answer", END)
        graph.add_edge("analysis", "retrieve")
        graph.add_edge("retrieve", "reason")

        if self.validate_node:
            graph.add_edge("reason", "validate")
            graph.add_conditional_edges(
                "validate",
                self._route_validation,
                {
                    "pass": "generate_report",
                    "retry": "reason",
                    "fail": "generate_report"
                }
            )
            logger.info("[graph] 已添加校验节点和反思循环路由")
        else:
            graph.add_edge("reason", "generate_report")
            logger.info("[graph] 无校验节点，推理直接连接到报告生成")

        graph.add_edge("generate_report", END)

        return graph.compile(
            checkpointer=self.checkpointer
        )

    def _route_intent(self, state: LearningState) -> str:
        t = state['intent_type']
        if t == "non_stroke":
            return "non_stroke"
        valid_types = {"profile", "resource", "tutor", "assessment", "learning_path", "consultation", "knowledge"}
        if t in valid_types:
            return t
        return "irrelevant"

    async def _reject_node(self, state: LearningState) -> dict:
        return {"report": "您的问题与脑卒中学习不相关，本系统仅支持脑卒中（中风）相关的学习问答，包括脑卒中的病因、症状、诊断、治疗、康复、预防、护理、并发症等方面。请提出与脑卒中学习相关的问题。"}

    async def _knowledge_node(self, state: LearningState) -> dict:
        if not self.llm_critic:
            return {"report": "知识回答服务未就绪"}

        knowledge_prompt = f"""你是脑卒中（中风）领域的专业学习顾问。请基于脑卒中医学知识和临床指南，直接回答以下脑卒中相关的通用问题。

问题：{state['case_text']}

回答要求：
- 用中文，简洁专业
- 内容必须围绕脑卒中（中风）相关
- 禁止绝对性结论
- 如果需要，引用权威脑卒中指南或研究"""

        messages = [
            SystemMessage(content=self.report_manager.system_role if self.report_manager else "你是一位专业的教育顾问。"),
            HumanMessage(content=knowledge_prompt),
        ]

        content = ""
        async for chunk in self.llm_critic.astream(messages):
            c = chunk.content if hasattr(chunk, "content") else str(chunk)
            content += c

        return {"report": content}

    def _route_validation(self, state: LearningState) -> str:
        logger.info(f"[route_validation] 校验路由决策")
        logger.info(f"[route_validation] 校验状态: {state['validation_passed']}")
        logger.info(f"[route_validation] 反思次数: {state['reflection_count']}")
        logger.info(f"[route_validation] 智能体权重: {state.get('agent_weights', {})}")
        logger.info(f"[route_validation] 驳回分类: {state.get('rejection_categories', [])}")

        route_decision = None
        if state['validation_passed']:
            route_decision = "pass"
            logger.info(f"[route_validation] 决策: pass → 生成报告")
        elif state['reflection_count'] < self.max_reflection_count:
            route_decision = "retry"
            logger.info(f"[route_validation] 决策: retry → 重新推理（退火权重已更新）")
        else:
            route_decision = "fail"
            logger.info(f"[route_validation] 决策: fail → 强制输出")

        if not isinstance(route_decision, str):
            logger.error(f"[route_validation] 路由决策不是字符串: {route_decision}，强制返回'fail'")
            route_decision = "fail"

        return route_decision