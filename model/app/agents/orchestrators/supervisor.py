"""Tutor 意图的监督者（Supervisor）试点。

用 qwen-turbo 作为监督者 LLM，在工具白名单内自主调度：
- evidence_search(query)   — 检索脑卒中指南证据（Hybrid RAG + 共享记忆）
- consult_experts(question, reason, roles) — 召集多学科专家并行推理 + 辩论仲裁（复用 ReasonNode）
- get_student_profile()    — 获取学生画像信息

安全边界：
- 意图门控（非脑卒中拒绝）与医学规则校验保留在监督者外层，本组件不越权
- 工具白名单外无任何动作；迭代次数受 recursion_limit 限制
- 监督者提示词内重申教学辅导定位与红线

环境开关：SUPERVISOR_TUTOR_ENABLED=false 时 tutor 走 Planner 主链路。
"""
import json
import logging
import os
from typing import Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from app.agents.core.schema import LearningState
from app.agents.utils.text_utils import truncate_text

logger = logging.getLogger(__name__)

SUPERVISOR_TUTOR_ENABLED = os.getenv("SUPERVISOR_TUTOR_ENABLED", "true").lower() not in ("false", "0", "no")
SUPERVISOR_MAX_TOOL_ROUNDS = int(os.getenv("SUPERVISOR_MAX_TOOL_ROUNDS", "6"))
# 走监督者动态派发的意图白名单（默认全量多步任务走监督者主路由）
SUPERVISOR_INTENTS = tuple(
    i.strip() for i in os.getenv(
        "SUPERVISOR_INTENTS",
        "tutor,profile,resource,assessment,learning_path",
    ).split(",") if i.strip()
)

_COMMON_PRINCIPLES = """你可以调用以下工具（只能调用这些工具，不能虚构其他能力）：
1. evidence_search(query)：检索权威脑卒中指南证据，回答需要循证依据的问题前应调用
2. consult_experts(question, reason, roles)：召集指定专家并行讨论并仲裁，reason 为选人理由（必填），返回各专家发言与综合提案
3. dispatch_agent(name, task)：精确点将某一位专家单独处理子任务（name 从专家白名单选），返回该专家发言
4. finalize_report(proposal, evidence)：基于综合提案与证据生成最终结构化报告（资源/评估/路径等需要结构化产出的场景必须调用）
5. get_student_profile()：获取当前学生的学习画像，个性化建议前应调用

专家白名单（consult_experts/dispatch_agent 的 roles/name 只能从中选择）：
{expert_menu}

工作原则：
- 教学辅导定位：只做医学教育辅导，不替代临床诊疗决策；不确定时明确说明
- 召集专家时根据问题性质选择 2~5 位最相关的专家；consult_experts 的 reason 参数必填，
  用一句话说明选人理由（该理由会展示给学生作为可审计依据）
- 引用指南证据时标注来源；证据不足时先检索再回答
- 回答用中文、结构清晰；工具调用不超过 {max_rounds} 轮，信息足够后直接给出最终答案
- 你的最终消息是交给撰写环节的"要点草稿"：简要列出结论、关键要点与学生需注意处即可，
  **不要写成完整回答**——学生可见的完整回答由后续独立的流式撰写步骤产出，你只需保证材料充分
- 不要再输出工具调用指令"""

_INTENT_GUIDANCE = {
    "tutor": """- 最终回答请按以下结构组织（可依问题类型微调，但必须包含）：
  1. **解答**：循序渐进地解答学生问题
  2. **关键要点**：列出核心概念与知识点
  3. **易错提示**：指出常见误区和易错点
  4. **拓展思考**：引导学生深入思考的延伸问题
  5. **下一步建议**：建议接下来学习的内容或练习
  6. **学习激励**：最后用一小段积极正向的话鼓励学生坚持学习
  （若已召集专家会诊，请整合专家发言、会诊收敛结论与仲裁裁决后按上述结构输出）""",
    "profile": """- 当前为画像构建/更新场景：你的职责是"访谈式追问"，找出画像缺失的证据并提问，
  不要自己下画像结论；画像事实由画像抽取/校验专家产出，你只负责提出最有价值、最少必要的追问。
- 最终回答是"下一步该补充什么信息"的追问，而非画像总结。""",
    "resource": """- 当前为学习资源生成场景：先分析学习需求，必要时 consult_experts 召集需求/文档/题目
  专家，最终给出资源生成方案与要点。""",
    "assessment": """- 当前为学习评估场景：结合学生画像与学习表现给出评估，必要时 consult_experts 召集
  评估/题目专家，最终给出评估结论与改进建议。""",
}


# 最终回答撰写阶段的系统提示：与监督者的内部调度推理彻底分离——
# 内部调度文本不外泄，学生可见的回答由这一步单独流式生成（逐 token 打印）。
_ANSWER_SYSTEM = (
    "你是脑卒中医学教育的学习辅导老师。请把收集到的材料整合成给学生的最终回答，"
    "直接输出回答正文（Markdown）。不要复述调度过程，不要提及智能体、工具、提示词或内部流程，"
    "不确定的内容不要编造。"
)


_TOOL_LABELS = {
    "evidence_search": "检索循证指南",
    "consult_experts": "召集专家会诊",
    "dispatch_agent": "点将专家",
    "finalize_report": "生成结构化报告",
    "get_student_profile": "读取学习画像",
}


def _summarize_tool_usage(trace: List[Dict]) -> tuple:
    """把监督者的工具使用情况转成一句自解释的轨迹说明。

    没有它，"0 次工具调用"在推理轨迹上只剩一句「处理完成」，
    用户看不出监督者做了什么、也看不出为什么没有专家内容。
    """
    tool_names = [name for item in trace for name in (item.get("tools") or [])]
    if tool_names:
        labels = "、".join(_TOOL_LABELS.get(n, n) for n in tool_names)
        return "调度完成", f"本轮调用：{labels}"
    return "本轮直接作答", "未检索证据、未召集专家——该问题无需额外材料即可回答"


def emit_supervisor_progress(title: str, detail: str = "") -> None:
    """推送监督者的**动作**进度（不是推理文本）。

    监督者的内部思考按设计不外泄，但"正在做什么"属于元信息，可以安全展示。
    没有它，调度阶段（实测可达 70s+）在推理轨迹上是一片空白——用户只看得到
    「监督者正在调度工具...」然后直接跳到「处理完成」。
    """
    try:
        from app.agents.event_sink import get_event_sink

        sink = get_event_sink()
        if sink is None:
            return
        sink({
            "type": "thinking",
            "thinking": {"step": "supervisor", "title": title, "content": detail or ""},
        })
    except Exception as e:  # noqa: BLE001 - 进度推送失败不应影响调度
        logger.debug(f"[supervisor] 进度事件推送失败: {e}")


def _build_answer_prompt(intent_type: str, question: str, material: str) -> str:
    guidance = _INTENT_GUIDANCE.get(intent_type, "")
    return (
        f"【学生问题】\n{question}\n\n"
        f"【回答要求】\n{guidance or '- 直接、结构清晰地回答学生的问题。'}\n\n"
        f"【可用材料】\n{material or '（无额外材料，请依据你的医学教育知识作答）'}\n\n"
        "请输出最终回答："
    )


def _build_system_prompt(intent_type: str, max_rounds: int, expert_menu_text: str) -> str:
    common = _COMMON_PRINCIPLES.format(max_rounds=max_rounds, expert_menu=expert_menu_text)
    guidance = _INTENT_GUIDANCE.get(intent_type, _INTENT_GUIDANCE["tutor"])
    return f"你是脑卒中医学教育{intent_type}场景的监督者（supervisor）智能体。你负责动态调度专家完成任务。\n\n{common}\n{guidance}"


class TutorSupervisor:

    def __init__(
        self,
        llm,
        retrieve_node=None,
        reason_node=None,
        analysis_node=None,
        report_node=None,
        max_tool_rounds: int = SUPERVISOR_MAX_TOOL_ROUNDS,
    ):
        self.llm = llm
        self.retrieve_node = retrieve_node
        self.reason_node = reason_node
        self.report_node = report_node
        self.max_tool_rounds = max_tool_rounds
        self._agent = None
        # 专家白名单：从 expert_config.yaml 加载，供监督者点将与提示词菜单使用
        try:
            from app.config.config_loader import get_expert_manager
            self.expert_menu = [
                {
                    "role": e.get("role"),
                    "brief": (e.get("instruction") or "").replace("\n", " ")[:60],
                }
                for e in get_expert_manager().get_experts()
            ]
        except Exception as e:
            logger.warning(f"[supervisor] 加载专家白名单失败: {e}")
            self.expert_menu = []

    def _expert_menu_text(self) -> str:
        if not self.expert_menu:
            return "（专家白名单不可用，roles 留空时由系统按规则自动编排）"
        lines = [f"- {e['role']}：{e['brief']}" for e in self.expert_menu]
        return "\n".join(lines)

    # ── 工具定义（闭包捕获当前 state 与共享工作区） ──────────────────────────
    def _build_agent(self, state: LearningState):
        workspace: Dict[str, str] = {
            "evidence": state.get("evidence", "") or "",
            "proposal": "",
            "last_roles": [],
            "last_reason": "",
            "expert_advices": [],
            "agent_messages": [],
            "blackboard": [],
            "convergence": "",
            "arbitration_result": "",
        }
        profile_text = self._format_profile(state)

        @tool
        async def evidence_search(query: str) -> str:
            """检索脑卒中指南证据。参数 query 为检索查询语句。返回命中的循证材料片段。"""
            emit_supervisor_progress("正在检索循证指南", f"检索词：{query}")
            try:
                if not self.retrieve_node:
                    return "证据检索不可用"
                mini_state = dict(state)
                mini_state["learning_questions"] = [query]
                updates = await self.retrieve_node.run(mini_state) or {}
                evidence = updates.get("evidence", "") or ""
                if evidence:
                    existing = workspace["evidence"]
                    workspace["evidence"] = f"{existing}\n\n--- 补充检索 ---\n{evidence}" if existing else evidence
                    return truncate_text(evidence, 3000)
                return "未检索到相关证据"
            except Exception as e:
                logger.warning(f"[supervisor] evidence_search 失败: {e}")
                return f"检索失败：{e}"

        @tool
        async def consult_experts(question: str, reason: str, roles: List[str] = None) -> str:
            """召集指定专家并行讨论并仲裁。

            参数 question 为要讨论的问题；reason 为本轮选人理由（必填，用一句话说明
            为什么选择这些专家，将随推理轨迹展示给学生）；roles 为本轮召集的专家角色列表，
            只能从系统提示中的专家白名单选择 1~5 位（留空则按系统规则自动编排）。
            返回各专家发言与综合提案。"""
            try:
                if not self.reason_node:
                    return "专家咨询不可用"
                valid_roles = {e["role"] for e in self.expert_menu}
                chosen = [r for r in (roles or []) if r in valid_roles]
                workspace["last_roles"] = list(chosen)
                workspace["last_reason"] = (reason or "").strip()
                emit_supervisor_progress(
                    "正在召集专家会诊",
                    "、".join(chosen) if chosen else "按系统规则自动编排",
                )
                if roles and len(chosen) != len(roles):
                    logger.info(
                        "[supervisor] 点将名单过滤: 请求=%s, 白名单内=%s", roles, chosen
                    )

                mini_state = dict(state)
                mini_state["case_text"] = question
                mini_state["evidence"] = workspace["evidence"]
                mini_state["validation_feedback"] = ""
                mini_state["reflection_count"] = 0
                if chosen:
                    mini_state["active_experts_override"] = chosen

                updates = await self.reason_node.run(mini_state) or {}

                logger.info(
                    "[supervisor] reason_node 返回: conv=%s arb=%s msgs=%d board=%d",
                    (updates.get("convergence") or "")[:30],
                    (updates.get("arbitration_result") or "")[:30],
                    len(updates.get("agent_messages") or []),
                    len(updates.get("blackboard") or []),
                )

                # 收集各专家完整发言（回流前端可审计展示）
                resolved_roles = updates.get("active_experts", []) or chosen
                speeches = []
                for role in resolved_roles:
                    advice = updates.get(f"{role}_advice", "") or ""
                    if advice and not advice.startswith("未能获取"):
                        speeches.append({"role": role, "content": advice})
                workspace["expert_advices"] = speeches

                # M2+M3 对话-黑板结果（reason_node 嵌套运行时 custom 事件不冒泡，
                # 需经 supervisor 返回后由 learning_agent 补发 agent_msg/blackboard 事件）
                workspace["agent_messages"] = updates.get("agent_messages", []) or []
                workspace["blackboard"] = updates.get("blackboard", []) or []
                workspace["convergence"] = updates.get("convergence", "") or ""
                workspace["arbitration_result"] = updates.get("arbitration_result", "") or ""

                proposal = updates.get("proposal", "") or ""
                if proposal:
                    workspace["proposal"] = proposal
                    body = "\n\n".join(
                        f"【{s['role']}】\n{s['content']}" for s in speeches
                    )
                    result = f"{body}\n\n【综合提案】\n{proposal}" if body else proposal
                    return truncate_text(result, 5000)
                return "专家未产出有效提案"
            except Exception as e:
                logger.warning(f"[supervisor] consult_experts 失败: {e}")
                return f"专家咨询失败：{e}"

        @tool
        async def get_student_profile() -> str:
            """获取当前学生的学习画像（专业、年级、知识水平、目标等）。"""
            emit_supervisor_progress("正在读取学习画像")
            return profile_text or "暂无学习画像信息"

        # ── 专家注册表：可寻址的 specialist agents ──
        from app.agents.registry import AgentRegistry
        from app.agents.tools import build_expert_tools

        def _tool_factory():
            return build_expert_tools(state, None, None)

        try:
            expert_configs = [
                e for e in (self.expert_menu or [])
                if isinstance(e, dict)
            ]
            # 重新构造含 tools/priority 等完整字段的专家配置（menu 只有 role/brief）
            from app.config.config_loader import get_expert_manager
            full_configs = get_expert_manager().get_experts()
            registry = AgentRegistry(self.llm, full_configs, _tool_factory)
        except Exception as e:
            logger.warning(f"[supervisor] 专家注册表构建失败: {e}")
            registry = None

        @tool
        async def dispatch_agent(name: str, task: str) -> str:
            """精确点将某一位专家单独处理子任务。name 从专家白名单选择；task 为要处理的任务。返回该专家发言。"""
            emit_supervisor_progress(f"正在点将：{name}", task)
            if not registry:
                return "专家注册表不可用"
            agent = registry.get(name)
            if not agent:
                return f"专家「{name}」不在白名单内"
            return await agent.run(task)

        @tool
        async def finalize_report(proposal: str, evidence: str) -> str:
            """基于综合提案与证据生成最终结构化报告（资源/评估/路径等需要结构化产出时必须调用）。"""
            emit_supervisor_progress("正在生成结构化报告", (proposal or "")[:120])
            if not self.report_node:
                return "报告生成不可用"
            try:
                mini_state = dict(state)
                mini_state["proposal"] = proposal
                mini_state["evidence"] = evidence
                updates = await self.report_node.run(mini_state) or {}
                report = updates.get("report", "") or ""
                if report:
                    workspace["proposal"] = proposal
                    return report[:6000]
                return "报告生成结果为空"
            except Exception as e:
                logger.warning(f"[supervisor] finalize_report 失败: {e}")
                return f"报告生成失败：{e}"

        system_prompt = _build_system_prompt(
            state.get("intent_type", "tutor"),
            self.max_tool_rounds,
            self._expert_menu_text(),
        )
        # langgraph-prebuilt 1.x 用 prompt 参数注入系统提示（0.x 时代叫 state_modifier）
        return create_react_agent(
            model=self.llm,
            tools=[evidence_search, consult_experts, dispatch_agent, finalize_report, get_student_profile],
            prompt=system_prompt,
        ), workspace

    @staticmethod
    def _format_profile(state: LearningState) -> str:
        profile_summary = state.get("profile_summary", "") or ""
        if profile_summary:
            return profile_summary
        context = state.get("context", {}) or {}
        if context:
            try:
                return json.dumps(context, ensure_ascii=False)[:2000]
            except Exception:
                pass
        return ""

    def _answer_material(self, state: LearningState, workspace: Dict, draft: str) -> str:
        """汇总撰写最终回答所需的材料（画像 / 证据 / 专家意见 / 收敛 / 仲裁 / 草稿）。"""
        parts: List[str] = []
        profile = self._format_profile(state)
        if profile:
            parts.append(f"【学习画像】\n{profile[:1200]}")
        evidence = (workspace.get("evidence") or state.get("evidence") or "").strip()
        if evidence:
            parts.append(f"【循证材料】\n{evidence[:3000]}")
        advices = workspace.get("expert_advices") or []
        if advices:
            joined = "\n\n".join(
                f"【{a.get('role', '')}】{(a.get('content') or '')[:1500]}" for a in advices
            )
            parts.append(f"【专家意见】\n{joined}")
        if workspace.get("convergence"):
            parts.append(f"【会诊收敛结论】\n{str(workspace['convergence'])[:1200]}")
        if workspace.get("arbitration_result"):
            parts.append(f"【仲裁裁决】\n{str(workspace['arbitration_result'])[:1500]}")
        if workspace.get("proposal"):
            parts.append(f"【综合提案】\n{str(workspace['proposal'])[:2500]}")
        if draft:
            parts.append(f"【监督者调度后的要点草稿】\n{draft[:4000]}")
        return "\n\n".join(parts)

    async def _compose_answer(self, state: LearningState, user_input: str,
                              draft: str, workspace: Dict) -> str:
        """独立流式撰写最终回答。

        与监督者的内部调度推理分离：中间思考（工具调度、选人理由、提示词）不外泄，
        学生可见的回答由这一步单独生成，并逐 token 推送给前端。
        撰写失败时回退监督者草稿，功能不退化。
        """
        from app.agents.event_sink import get_event_sink
        from app.agents.text_stream import stream_llm_text

        # profile_build 的最终结果由 agent_runner 从抽取到的维度**确定性渲染**，
        # 并以下发 replace 事件覆盖回答。这里若再流式撰写一次，用户会看到回答
        # 打到一半被整体替换，且白白多花一次调用——直接回退草稿跳过撰写。
        if state.get("report_mode") == "profile_build":
            logger.info("[supervisor] profile_build 由确定性渲染产出结果，跳过流式撰写")
            return draft

        prompt = _build_answer_prompt(
            state.get("intent_type", "tutor"),
            user_input,
            self._answer_material(state, workspace, draft),
        )
        emit_supervisor_progress("正在整合最终回答")
        try:
            answer = await stream_llm_text(
                self.llm,
                [SystemMessage(content=_ANSWER_SYSTEM), HumanMessage(content=prompt)],
                emit=get_event_sink(), channel="answer", label="最终回答", node="supervisor",
            )
            answer = (answer or "").strip()
            if answer:
                return answer
            logger.warning("[supervisor] 流式撰写结果为空，回退监督者草稿")
            return draft
        except Exception as e:
            logger.warning(
                f"[supervisor] 流式撰写最终回答失败，回退监督者草稿: {type(e).__name__}: {e}"
            )
            return draft

    # ── 主入口 ────────────────────────────────────────────────────────────
    async def run(self, state: LearningState) -> Dict:
        user_input = state["case_text"]
        all_info = state.get("all_info", "") or ""
        if all_info:
            user_input = f"{all_info}\n\n【本轮问题】{user_input}"

        agent, workspace = self._build_agent(state)

        try:
            # react 图每轮工具调用约占 2 层递归，预留富余
            recursion_limit = 2 * self.max_tool_rounds + 8
            result = await agent.ainvoke(
                {"messages": [HumanMessage(content=user_input)]},
                config={"recursion_limit": recursion_limit},
            )
        except Exception as e:
            logger.error(f"[supervisor] 监督者执行失败: {type(e).__name__}: {e}")
            return {
                "report": "抱歉，辅导服务暂时不可用，请稍后重试。",
                "proposal": "",
                "supervisor_trace": [],
                "supervisor_roles": [],
                "expert_advices": [],
                "agent_messages": [],
                "blackboard": [],
                "convergence": "",
                "arbitration_result": "",
            }

        messages = result.get("messages", []) or []
        draft = self._extract_answer(messages)
        trace = self._build_trace(messages)
        # 让调度结果自我解释：否则"0 次工具调用"在轨迹上只剩一句「处理完成」，
        # 用户看不出监督者到底做了什么、以及为什么没有专家内容。
        emit_supervisor_progress(*_summarize_tool_usage(trace))
        # 最终回答与内部调度推理分离：由独立的流式撰写步骤产出，前端逐 token 打印
        answer = await self._compose_answer(state, user_input, draft, workspace)

        logger.info(
            "[supervisor] 完成: 消息数=%d, 工具调用=%d, 点将=%s, 答案长度=%d",
            len(messages),
            sum(1 for m in trace if m.get("tools")),
            workspace.get("last_roles"),
            len(answer),
        )
        return {
            "report": answer,
            "proposal": answer,
            "supervisor_trace": trace,
            "supervisor_roles": workspace.get("last_roles", []),
            "supervisor_reason": workspace.get("last_reason", ""),
            "expert_advices": workspace.get("expert_advices", []),
            "agent_messages": workspace.get("agent_messages", []),
            "blackboard": workspace.get("blackboard", []),
            "convergence": workspace.get("convergence", ""),
            "arbitration_result": workspace.get("arbitration_result", ""),
        }

    @staticmethod
    def _extract_answer(messages: List) -> str:
        # 从后往前找最后一条有实质内容的 AI 消息
        for message in reversed(messages):
            if isinstance(message, AIMessage):
                content = getattr(message, "content", "") or ""
                # 排除"仅含工具调用"的空内容消息
                if isinstance(content, str) and content.strip():
                    return content.strip()
        return "抱歉，我暂时无法给出有效回答，请换个方式提问。"

    @staticmethod
    def _build_trace(messages: List) -> List[Dict]:
        from langchain_core.messages import ToolMessage
        trace = []
        pending = None
        for message in messages:
            if isinstance(message, ToolMessage):
                result_content = getattr(message, "content", "") or ""
                if isinstance(result_content, str) and result_content.strip():
                    if pending is not None:
                        existing = pending.get("results", "")
                        merged = f"{existing}\n\n{result_content}" if existing else result_content
                        pending["results"] = truncate_text(merged, 600)
                continue
            if isinstance(message, AIMessage):
                tool_calls = getattr(message, "tool_calls", None) or []
                tools = [tc.get("name", "unknown") for tc in tool_calls]
                content = getattr(message, "content", "") or ""
                if tools:
                    entry = {"role": "assistant", "tools": tools, "results": ""}
                    # 选人/调度理由：工具调用前的文字说明（监督者自主点将的依据）
                    if isinstance(content, str) and content.strip():
                        entry["reason"] = truncate_text(content, 300)
                    trace.append(entry)
                    pending = entry
                elif isinstance(content, str) and content.strip():
                    trace.append({"role": "assistant", "content": truncate_text(content, 200)})
                    pending = None
        return trace
