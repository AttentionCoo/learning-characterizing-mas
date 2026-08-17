"""Tutor 意图的监督者（Supervisor）试点。

用 qwen-turbo 作为监督者 LLM，在工具白名单内自主调度：
- evidence_search(query)   — 检索脑卒中指南证据（Hybrid RAG + 共享记忆）
- consult_experts(question) — 召集多学科专家并行推理 + 辩论仲裁（复用 ReasonNode）
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

_SUPERVISOR_SYSTEM_PROMPT = """你是脑卒中医学教育辅导的监督者（supervisor）智能体。你负责回答脑卒中（中风）相关的学习问题。

你可以调用以下工具（只能调用这些工具，不能虚构其他能力）：
1. evidence_search(query)：检索权威脑卒中指南证据，回答需要循证依据的问题前应调用
2. consult_experts(question, roles)：召集指定专家并行讨论并仲裁，返回各专家发言与综合提案
3. get_student_profile()：获取当前学生的学习画像，个性化建议前应调用

专家白名单（consult_experts 的 roles 只能从中选择）：
{expert_menu}

工作原则：
- 教学辅导定位：只做医学教育辅导，不替代临床诊疗决策；不确定时明确说明
- 召集专家时根据问题性质选择 2~5 位最相关的专家，并在工具调用前用一句话说明选人理由；
  例如需要循证依据时先 evidence_search，需要多角度教学建议时 consult_experts
- 引用指南证据时标注来源；证据不足时先检索再回答
- 回答用中文、结构清晰；工具调用不超过 {max_rounds} 轮，信息足够后直接给出最终答案
- 最终输出是给学生的完整回答，不要再输出工具调用指令"""


class TutorSupervisor:

    def __init__(
        self,
        llm,
        retrieve_node=None,
        reason_node=None,
        analysis_node=None,
        max_tool_rounds: int = SUPERVISOR_MAX_TOOL_ROUNDS,
    ):
        self.llm = llm
        self.retrieve_node = retrieve_node
        self.reason_node = reason_node
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
            "expert_advices": [],
        }
        profile_text = self._format_profile(state)

        @tool
        async def evidence_search(query: str) -> str:
            """检索脑卒中指南证据。参数 query 为检索查询语句。返回命中的循证材料片段。"""
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
        async def consult_experts(question: str, roles: List[str] = None) -> str:
            """召集指定专家并行讨论并仲裁。

            参数 question 为要讨论的问题；roles 为本轮召集的专家角色列表，
            只能从系统提示中的专家白名单选择 1~5 位（留空则按系统规则自动编排）。
            返回各专家发言与综合提案。"""
            try:
                if not self.reason_node:
                    return "专家咨询不可用"
                valid_roles = {e["role"] for e in self.expert_menu}
                chosen = [r for r in (roles or []) if r in valid_roles]
                workspace["last_roles"] = list(chosen)
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

                # 收集各专家完整发言（回流前端可审计展示）
                resolved_roles = updates.get("active_experts", []) or chosen
                speeches = []
                for role in resolved_roles:
                    advice = updates.get(f"{role}_advice", "") or ""
                    if advice and not advice.startswith("未能获取"):
                        speeches.append({"role": role, "content": advice})
                workspace["expert_advices"] = speeches

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
            return profile_text or "暂无学习画像信息"

        system_prompt = _SUPERVISOR_SYSTEM_PROMPT.format(
            max_rounds=self.max_tool_rounds,
            expert_menu=self._expert_menu_text(),
        )
        # langgraph-prebuilt 1.x 用 prompt 参数注入系统提示（0.x 时代叫 state_modifier）
        return create_react_agent(
            model=self.llm,
            tools=[evidence_search, consult_experts, get_student_profile],
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
            }

        messages = result.get("messages", []) or []
        answer = self._extract_answer(messages)
        trace = self._build_trace(messages)

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
            "expert_advices": workspace.get("expert_advices", []),
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
                    trace.append(entry)
                    pending = entry
                elif isinstance(content, str) and content.strip():
                    trace.append({"role": "assistant", "content": truncate_text(content, 200)})
                    pending = None
        return trace
