"""对话-黑板编排器（M2+M3）：专家间结构化消息交流 + 黑板共享工作区。

M2 结构化消息：专家在初稿后互见彼此观点，可定向提问（A→B）、回复、修订、
同意、反对，形成可审计的 agent_messages 通道（from/to/round/kind/content）。
M3 黑板共享工作区：专家在 blackboard 通道写「发现/认领子问题」，读他人发现，
教学总监从黑板+消息收敛最终意见。
仲裁智能体在对话结束后依据对话记录与证据链裁决。

由 ReasonNode 持有并调用，替代原广播式 DebateOrchestrator 的单一职责。
"""
import asyncio
import logging
import re
from typing import Dict, List

from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

# 消息类型白名单（与前端 agent_msg 事件 kind 对齐）
MSG_KINDS = ("question", "reply", "revise", "object", "finding")


class DialogueOrchestrator:

    def __init__(
        self,
        debate_config: Dict,
        arbitrator_role: str,
        expert_manager,
        llm,
        llm_synthesis,
        debate_max_rounds: int,
    ):
        self.debate_config = debate_config
        self.arbitrator_role = arbitrator_role
        self.expert_manager = expert_manager
        self.llm = llm
        self.llm_synthesis = llm_synthesis
        self.debate_max_rounds = debate_max_rounds
        # M2 对话轮数（可与辩论轮数不同，默认与 debate_max_rounds 一致）
        self.dialogue_max_rounds = debate_config.get("dialogue_max_rounds", debate_max_rounds)

    async def run(
        self,
        expert_roles: List[str],
        initial_results: List[str],
        case_info: str,
        evidence: str,
        existing_history: List[Dict],
        existing_messages: List[Dict],
        existing_blackboard: List[Dict],
    ) -> Dict:
        """执行 初稿互见 → 多轮结构化对话（M2）→ 黑板收敛（M3）→ 仲裁。"""
        debate_history = list(existing_history)
        agent_messages = list(existing_messages)
        blackboard = list(existing_blackboard)

        # 黑板初始化：每位专家的初稿作为首条「发现」
        if not blackboard:
            for role, opinion in zip(expert_roles, initial_results):
                if role == self.arbitrator_role:
                    continue
                blackboard.append({
                    "role": role,
                    "round": 0,
                    "kind": "finding",
                    "content": opinion,
                })

        dialogue_roles = [r for r in expert_roles if r != self.arbitrator_role]
        results_map = dict(zip(expert_roles, initial_results))

        logger.info("[dialogue] ══════════ 专家间对话开始（M2 结构化消息 + M3 黑板） ══════════")

        for round_num in range(1, self.dialogue_max_rounds + 1):
            logger.info(f"[dialogue] 对话第 {round_num}/{self.dialogue_max_rounds} 轮")

            # 每位专家基于「黑板 + 消息历史 + 他人观点」产生结构化消息
            round_tasks = [
                self._ask_dialogue(role, results_map, agent_messages, blackboard, case_info, round_num)
                for role in dialogue_roles
            ]
            round_outputs = await asyncio.gather(*round_tasks, return_exceptions=True)

            round_messages: List[Dict] = []
            for role, output in zip(dialogue_roles, round_outputs):
                if isinstance(output, Exception):
                    logger.warning(f"[dialogue] {role} 对话发言异常: {type(output).__name__}")
                    continue
                parsed = self._parse_messages(role, output, round_num)
                for msg in parsed:
                    agent_messages.append(msg)
                    round_messages.append(msg)
                    logger.info(
                        f"[dialogue] 消息 round={round_num} {msg['from']} → {msg['to']} "
                        f"[{msg['kind']}]: {msg['content'][:80]}"
                    )
                    if msg["kind"] == "revise":
                        # 修订黑板中该专家上一轮的发现
                        self._update_blackboard(blackboard, role, msg["content"], round_num)
                    elif msg["kind"] == "finding":
                        blackboard.append({
                            "role": role,
                            "round": round_num,
                            "kind": "finding",
                            "content": msg["content"],
                        })

            if not round_messages:
                logger.info("[dialogue] 本轮无有效消息（观点一致），提前收敛")
                break

            # 异议驱动停止：本轮只有 agree/无 object/question 且无人修订 → 提前结束
            has_disagreement = any(
                m["kind"] in ("object", "question", "revise") for m in round_messages
            )
            if not has_disagreement and round_num >= 2:
                logger.info("[dialogue] 观点已收敛（无异议/提问），停止后续轮次")
                break

        # M3 收敛：教学总监从黑板最终发现 + 消息历史生成收敛摘要（写入黑板 summary）
        convergence = await self._run_convergence(blackboard, agent_messages, case_info, evidence)

        arbitration_result = await self._run_arbitration(
            agent_messages, blackboard, debate_history, evidence
        )

        return {
            "debate_history": debate_history,
            "arbitration_result": arbitration_result,
            "agent_messages": agent_messages,
            "blackboard": blackboard,
            "convergence": convergence,
        }

    # ── M2 结构化消息 ──────────────────────────────────────────────────────

    async def _ask_dialogue(
        self,
        role: str,
        results_map: Dict[str, str],
        agent_messages: List[Dict],
        blackboard: List[Dict],
        case_info: str,
        round_num: int,
    ) -> str:
        expert_config = self.expert_manager.get_expert_by_role(role)
        system_prompt = (
            expert_config.get("system_prompt", f"你是专业的{role}")
            if expert_config else f"你是专业的{role}"
        )

        context = self._build_dialogue_context(role, results_map, agent_messages, blackboard, case_info)

        template = self.debate_config.get(
            "dialogue_prompt_template",
            "你正在与其他脑卒中教育专家进行会诊讨论（第{round}轮）。\n\n"
            "【当前会诊背景】\n{dialogue_context}\n\n"
            "【硬性规则】不得输出纯认同，每条消息必须带来信息增量（新证据/冲突/缺失/决策）。\n"
            "请输出 0~2 条结构化消息（JSON 数组）。可选类型：\n"
            '- {"kind":"question","to":"某专家","content":"向该专家提问的问题"}\n'
            '- {"kind":"object","to":"某专家","content":"指出对方观点的问题并给出证据"}\n'
            '- {"kind":"reply","to":"某专家","content":"回答对方对你的提问"}\n'
            '- {"kind":"revise","to":"__all__","content":"基于讨论修正你的最终意见"}\n'
            '- {"kind":"finding","to":"__all__","content":"补充一条你认为重要的新发现"}\n'
            "如果无话可说，输出 []。只输出 JSON 数组，不要任何解释。",
        )
        # 用 replace 而非 format：模板内含 JSON 字面量（{...}），format 会误解析
        prompt = (
            template.replace("{round}", str(round_num))
            .replace("{dialogue_context}", context)
        )

        try:
            res = await self.llm.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=prompt),
            ])
            return getattr(res, "content", "") or ""
        except Exception as e:
            logger.error(f"[dialogue] {role} 对话发言失败: {e}")
            return ""

    def _build_dialogue_context(
        self,
        role: str,
        results_map: Dict[str, str],
        agent_messages: List[Dict],
        blackboard: List[Dict],
        case_info: str,
    ) -> str:
        parts = [f"【学习资料】\n{case_info[:1500]}\n"]

        # 黑板：各专家当前发现（截断保持上下文可控）
        parts.append("【会诊黑板（各专家当前观点）】")
        for entry in blackboard[-12:]:
            who = entry.get("role", "?")
            if who == role:
                continue
            content = entry.get("content", "") or ""
            parts.append(f"- {who}（第{entry.get('round', 0)}轮）: {content[:300]}")

        # 最近消息记录
        recent = agent_messages[-10:]
        if recent:
            parts.append("\n【最近对话记录】")
            for m in recent:
                parts.append(
                    f"- 第{m.get('round', 0)}轮 {m.get('from', '?')} → {m.get('to', '?')} "
                    f"[{m.get('kind', '')}]: {(m.get('content', '') or '')[:200]}"
                )

        # 自己的当前观点
        own = results_map.get(role, "")
        parts.append(f"\n【你的当前观点】\n{own[:800]}")

        return "\n".join(parts)

    def _parse_messages(self, role: str, raw: str, round_num: int) -> List[Dict]:
        """解析 LLM 输出的 JSON 消息数组，做白名单/结构校验。"""
        if not raw or not raw.strip():
            return []
        text = raw.strip()
        # 去掉可能的 markdown 代码围栏
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:].strip()
        try:
            import json
            data = json.loads(text)
            if not isinstance(data, list):
                data = [data]
        except Exception:
            return []

        messages = []
        for item in data:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind", "")).strip()
            to = str(item.get("to", "__all__")).strip() or "__all__"
            content = str(item.get("content", "")).strip()
            if kind not in MSG_KINDS or not content:
                continue
            # 清洗 to 字段：LLM 可能把黑板条目标签（如「（第0轮）」）带进收件人
            to = re.sub(r"（第\d+轮）|\(round\s*\d+\)", "", to).strip() or "__all__"
            messages.append({
                "from": role,
                "to": to,
                "round": round_num,
                "kind": kind,
                "content": content[:800],
            })
        return messages[:2]

    def _update_blackboard(self, blackboard: List[Dict], role: str, content: str, round_num: int):
        """修订黑板中该专家最近一条发现（原地替换为新版）。"""
        for i in range(len(blackboard) - 1, -1, -1):
            entry = blackboard[i]
            if entry.get("role") == role and entry.get("kind") == "finding":
                blackboard[i] = {
                    "role": role,
                    "round": round_num,
                    "kind": "finding",
                    "content": content,
                }
                return
        blackboard.append({
            "role": role,
            "round": round_num,
            "kind": "finding",
            "content": content,
        })

    # ── M3 收敛与仲裁 ─────────────────────────────────────────────────────

    async def _run_convergence(
        self,
        blackboard: List[Dict],
        agent_messages: List[Dict],
        case_info: str,
        evidence: str,
    ) -> str:
        """教学总监视角收敛：从黑板最终发现 + 对话消息提炼共识点。"""
        findings = [e for e in blackboard if e.get("kind") == "finding"]
        if len(findings) < 2:
            return ""

        findings_text = "\n".join(
            f"- {e.get('role')}: {(e.get('content') or '')[:400]}"
            for e in findings
        )
        msg_summary = ""
        if agent_messages:
            msg_summary = "\n".join(
                f"- 第{m.get('round', 0)}轮 {m.get('from')} → {m.get('to')} "
                f"[{m.get('kind')}]: {(m.get('content') or '')[:150]}"
                for m in agent_messages[-12:]
            )

        prompt = (
            "你是教学总监。以下是专家会诊的最终发现与对话记录，请提炼各专家的共识点、分歧点，"
            "并给出一段 200 字以内的收敛结论（供最终综合使用）。\n\n"
            f"【学习资料】\n{case_info[:800]}\n\n"
            f"【黑板最终发现】\n{findings_text}\n\n"
            f"【对话消息摘要】\n{msg_summary if msg_summary else '（无）'}"
        )
        try:
            res = await self.llm_synthesis.ainvoke([
                SystemMessage(content="你是严谨的教学总监，擅长在多专家会诊后收敛共识。"),
                HumanMessage(content=prompt),
            ])
            content = getattr(res, "content", "") or ""
            logger.info(f"[dialogue] 收敛结论: {content[:120]}")
            return content[:2000]
        except Exception as e:
            logger.error(f"[dialogue] 收敛失败: {e}")
            return ""

    async def _run_arbitration(
        self,
        agent_messages: List[Dict],
        blackboard: List[Dict],
        debate_history: List[Dict],
        evidence: str,
    ) -> str:
        """仲裁智能体依据对话记录 + 黑板裁决。"""
        arbitrator_config = self.expert_manager.get_expert_by_role(self.arbitrator_role)
        system_prompt = (
            arbitrator_config.get("system_prompt", "你是公正严谨的教育仲裁专家。")
            if arbitrator_config else "你是公正严谨的教育仲裁专家。"
        )

        msg_text = "\n".join(
            f"第{m.get('round', 0)}轮 {m.get('from')} → {m.get('to')} "
            f"[{m.get('kind')}]: {(m.get('content') or '')[:400]}"
            for m in agent_messages[-20:]
        )
        findings_text = "\n".join(
            f"{e.get('role')}: {(e.get('content') or '')[:400]}"
            for e in blackboard if e.get("kind") == "finding"
        )
        history_text = "\n".join(
            f"第{r['round']}轮 {r['role']}: {r['content'][:500]}"
            for r in debate_history
        )

        arbitration_template = self.debate_config.get(
            "arbitration_prompt_template",
            "作为仲裁智能体，请根据以下专家对话记录、黑板发现和证据链裁决。\n"
            "【专家对话记录】\n{agent_messages}\n【黑板发现】\n{findings}\n"
            "【辩论记录】\n{debate_history}\n【可用证据】\n{evidence}",
        )

        prompt = arbitration_template.format(
            agent_messages=msg_text or "（无）",
            findings=findings_text or "（无）",
            debate_history=history_text or "（无）",
            evidence=evidence[:2000] if evidence else "无",
        )

        try:
            res = await self.llm_synthesis.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=prompt),
            ])
            content = getattr(res, "content", "")
            logger.info("[dialogue] ══════════ 仲裁裁决 ══════════")
            logger.info(f"[dialogue][仲裁·裁决] {self.arbitrator_role}:\n{content}")
            return content
        except Exception as e:
            logger.error(f"[dialogue] 仲裁裁决失败: {e}")
            return "仲裁失败，请基于专家意见自行判断。"
