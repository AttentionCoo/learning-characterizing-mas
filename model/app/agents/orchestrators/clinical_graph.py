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
from app.agents.orchestrators.nodes.vision_node import VisionAnalysisNode
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
        vision_node: VisionAnalysisNode = None,
        planner_node=None,
        executor_node=None,
        supervisor_node=None,
        llm_critic=None,
        report_manager=None,
        shared_memory_system=None,
    ):
        self.intent_node = intent_node
        self.analysis_node = analysis_node
        self.retrieve_node = retrieve_node
        self.reason_node = reason_node
        self.report_node = report_node
        self.validate_node = validate_node
        self.vision_node = vision_node
        self.planner_node = planner_node
        self.executor_node = executor_node
        self.supervisor_node = supervisor_node
        self.llm_critic = llm_critic
        self.report_manager = report_manager
        self.shared_memory_system = shared_memory_system

        self.validation_manager = get_validation_manager()
        self.max_reflection_count = self.validation_manager.get_max_reflection_count()

        self.checkpointer = MemorySaver()

    @staticmethod
    def _with_node_events(name: str, fn):
        """给图节点包一层：进入节点时经 stream_writer 发 node_start 自定义事件。

        外层运行器以 stream_mode=["custom", ...] 消费，保证 astream_events 迁移后
        前端仍然能收到节点开始标签（由 LearningAgent 的 _NODE_LABELS 翻译）。
        """

        async def wrapper(state, **kwargs):
            try:
                from langgraph.config import get_stream_writer
                writer = get_stream_writer()
                writer({"type": "node_start", "node": name})
            except Exception:
                pass
            return await fn(state, **kwargs)

        wrapper.__name__ = f"{name}_with_events"
        return wrapper

    def build(self):
        graph = StateGraph(LearningState)

        graph.add_node("intent", self._with_node_events("intent", self.intent_node.run))
        graph.add_node("reject", self._with_node_events("reject", self._reject_node))
        graph.add_node("knowledge_answer", self._with_node_events("knowledge_answer", self._knowledge_node))
        graph.add_node("analysis", self._with_node_events("analysis", self.analysis_node.run))

        # 医学多模态：当存在影像时添加 vision 节点
        if self.vision_node:
            graph.add_node("vision", self._with_node_events("vision", self.vision_node.run))
            logger.info("[graph] 已添加 vision 影像分析节点")

        graph.add_node("retrieve", self._with_node_events("retrieve", self.retrieve_node.run))
        graph.add_node("reason", self._with_node_events("reason", self.reason_node.run))

        if self.planner_node:
            graph.add_node("planner", self._with_node_events("planner", self.planner_node.run))
            logger.info("[graph] 已添加 planner 规划节点")
        if self.executor_node:
            graph.add_node("execute_plan", self._with_node_events("execute_plan", self.executor_node.run))
            logger.info("[graph] 已添加 execute_plan 执行节点")
        if self.supervisor_node:
            graph.add_node("supervisor", self._with_node_events("supervisor", self.supervisor_node.run))
            logger.info("[graph] 已添加 supervisor 监督者节点（tutor 试点）")

        if self.validate_node:
            graph.add_node("validate", self._with_node_events("validate", self.validate_node.run))

        graph.add_node("generate_report", self._with_node_events("generate_report", self.report_node.run))

        graph.set_entry_point("intent")

        graph.add_conditional_edges(
            "intent",
            self._route_intent,
            {
                "non_stroke": "reject",
                "irrelevant": "reject",
                "knowledge": "knowledge_answer",
                "planner": "planner",
                "supervisor": "supervisor",
                "generate_report": "generate_report",
                "analysis": "analysis",
            }
        )

        graph.add_edge("reject", END)
        graph.add_edge("knowledge_answer", END)
        if self.supervisor_node:
            graph.add_edge("supervisor", END)
            logger.info("[graph] supervisor 输出报告后直接结束")

        # 影像不相关时的拒绝节点
        if self.vision_node:
            graph.add_node("reject_image", self._reject_image_node)

        # 条件路由：有影像 → intent → analysis → vision → (planner | reject_image)；无影像 → intent 直接 planner
        if self.vision_node:
            graph.add_conditional_edges(
                "analysis",
                self._route_after_analysis,
                {
                    "vision": "vision",
                    "planner": "planner",
                }
            )
            # 影像分析后：检查是否与脑卒中相关
            graph.add_conditional_edges(
                "vision",
                self._route_after_vision,
                {
                    "planner": "planner",
                    "reject": "reject_image",
                }
            )
            graph.add_edge("reject_image", END)
            logger.info("[graph] 已添加影像分支路由: intent → (analysis → vision → planner | reject_image)")

        if self.planner_node and self.executor_node:
            graph.add_edge("planner", "execute_plan")

        if self.validate_node and self.planner_node and self.executor_node:
            graph.add_edge("execute_plan", "validate")
            graph.add_conditional_edges(
                "validate",
                self._route_validation,
                {
                    "pass": "generate_report",
                    "retry": "planner",
                    "fail": "generate_report"
                }
            )
            logger.info("[graph] 已添加校验节点：失败反馈回到 planner 重新规划（RePlan 循环）")
        elif self.executor_node:
            graph.add_edge("execute_plan", "generate_report")

        graph.add_edge("generate_report", END)

        return graph.compile(
            checkpointer=self.checkpointer
        )

    def _route_intent(self, state: LearningState) -> str:
        t = state['intent_type']
        if t == "non_stroke":
            return "non_stroke"
        # code_assist 跳过临床分析链，直接进入报告生成
        if t == "code_assist":
            return "generate_report"
        if t == "knowledge":
            return "knowledge"
        # tutor 试点：监督者优先，未启用时走 planner 主链路
        if t == "tutor" and self.supervisor_node:
            return "supervisor"
        valid_types = {"profile", "resource", "tutor", "assessment", "learning_path", "consultation"}
        if t in valid_types:
            # 有医学影像时先走 analysis → vision 影像门控，再进入规划
            if self.vision_node and state.get("images"):
                return "analysis"
            return "planner"
        return "irrelevant"

    def _route_after_analysis(self, state: LearningState) -> str:
        """analysis 节点之后的条件路由：有医学影像走 vision，否则进入规划器"""
        images = state.get("images", [])
        has_images = bool(images)
        if has_images:
            logger.info(f"[graph] 检测到 {len(images)} 张医学影像 → 路由到 vision 节点")
            return "vision"
        logger.info("[graph] 无医学影像 → 路由到 planner 规划节点")
        return "planner"

    def _route_after_vision(self, state: LearningState) -> str:
        """vision 节点之后的条件路由：检查影像是否与脑卒中相关"""
        is_stroke_related = state.get("is_image_stroke_related", True)
        findings = state.get("vision_findings")

        if not is_stroke_related:
            # 获取影像类型用于提示（仅在日志中使用，不做 state 副作用）
            image_type = findings.get("image_type", "unknown") if findings else "unknown"
            logger.info(f"[graph] 影像与脑卒中无关 (类型: {image_type}) → 路由到 reject_image")
            return "reject"

        logger.info(f"[graph] 影像与脑卒中相关 → 路由到 planner")
        return "planner"

    async def _reject_node(self, state: LearningState) -> dict:
        message = state.get("input_rejection_message")
        if message:
            return {"report": message}
        return {"report": "您的问题与脑卒中学习不相关，本系统仅支持脑卒中（中风）相关的学习问答，包括脑卒中的病因、症状、诊断、治疗、康复、预防、护理、并发症等方面。请提出与脑卒中学习相关的问题。"}

    async def _reject_image_node(self, state: LearningState) -> dict:
        """当上传的影像与脑卒中无关时的拒绝消息"""
        gate_result = state.get("_gate_result", "")
        findings = state.get("vision_findings") or {}
        image_type = findings.get("image_type", "") if isinstance(findings, dict) else ""

        if gate_result == "rejected_by_precheck":
            # Tier 0 预校验直接拒绝（格式/大小/数量问题）
            reason = state.get("_precheck_reason", "图片不符合要求")
            return {"report": (
                "⚠️ **图片预检未通过**\n\n"
                f"原因：{reason}\n\n"
                "**图片要求：**\n"
                "- 支持的格式：JPEG、PNG、BMP、TIFF、DICOM\n"
                "- 单张图片不超过 14MB\n"
                "- 单次最多上传 5 张图片\n"
                "- 请勿上传非图片文件（PDF、文本、视频等）\n\n"
                "请按要求重新上传脑卒中相关的医学影像。"
            )}

        if gate_result == "rejected_by_adversarial_detection":
            # 对抗性提示检测
            return {"report": (
                "🚫 **请求已被安全系统拦截**\n\n"
                "系统检测到您的请求中包含异常指令，该行为已被记录。\n\n"
                "本系统仅支持脑卒中（中风）相关的医学影像分析学习。"
                "如果您确实有脑卒中相关学习需求，请正常描述您的问题并上传相关医学影像。"
            )}

        if gate_result == "rejected_by_gate":
            # Tier 1 门控直接拒绝
            return {"report": (
                "⚠️ **图片已被拦截**\n\n"
                "经 AI 医学影像门控系统检测，您上传的图片**与脑卒中（中风）医学内容无关**。\n\n"
                "本系统仅支持脑卒中相关的医学影像分析，包括但不限于：\n"
                "- 🧠 **头部CT / MRI** — 脑梗死、脑出血的影像判读\n"
                "- 🔬 **脑血管造影**（CTA/MRA/DSA）— 血管狭窄、闭塞、动脉瘤\n"
                "- 🩻 **病理切片** — 脑卒中相关组织学\n"
                "- 📊 **心电图** — 房颤等心源性卒中风险评估\n"
                "- 📋 **检验报告 / 影像报告** — 脑卒中相关实验室检查\n\n"
                "请上传与脑卒中相关的医学影像。如需其他帮助，请用文字描述您的学习需求。"
            )}

        if gate_result == "rejected_by_content_check":
            # Tier 2/3 内容检测拒绝
            findings_summary = ""
            if findings:
                ftype = findings.get("image_type", "")
                fkeys = findings.get("key_findings", [])
                if fkeys:
                    findings_summary = f"\n\n图片分析摘要：类型={ftype}，发现={'；'.join(fkeys[:2])}"

            return {"report": (
                "⚠️ **图片内容与脑卒中无关**\n\n"
                "经 AI 影像分析，您上传的图片内容**不属于脑卒中（中风）相关的医学影像**。"
                f"{findings_summary}\n\n"
                "请上传脑卒中相关的医学影像，例如：\n"
                "- 头部CT/MRI（脑梗、脑出血等）\n"
                "- 脑血管造影片\n"
                "- 脑卒中相关的病理切片、心电图、检验报告\n\n"
                "如需其他学习帮助，请直接输入文字问题。"
            )}

        # 默认拒绝消息
        if image_type:
            return {"report": (
                f"⚠️ **不支持的图片类型**\n\n"
                f"检测到您上传的图片类型为「{image_type}」，该类型图片经分析后与脑卒中学习无关。\n\n"
                "本系统仅支持脑卒中相关的医学影像分析。请上传头部CT、MRI、血管造影等脑卒中相关的医学影像。"
            )}

        return {"report": (
            "⚠️ **图片与脑卒中学习无关**\n\n"
            "您上传的图片不属于脑卒中相关的医学影像。本系统仅支持脑卒中（中风）相关的医学影像分析与学习。\n\n"
            "请上传：头部CT/MRI、脑血管造影、病理切片、心电图、检验报告等与脑卒中相关的医学影像。"
        )}

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
            logger.info(f"[route_validation] 决策: retry → 反馈回到 planner 重新规划（退火权重已更新）")
        else:
            route_decision = "fail"
            logger.info(f"[route_validation] 决策: fail → 强制输出")

        if not isinstance(route_decision, str):
            logger.error(f"[route_validation] 路由决策不是字符串: {route_decision}，强制返回'fail'")
            route_decision = "fail"

        return route_decision
