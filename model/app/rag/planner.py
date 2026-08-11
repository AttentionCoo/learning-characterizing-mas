"""
临床决策规划 — Clinical Decision Planner
=========================================

把用户的临床问题拆成"决策节点"（Decision Nodes），并按临床优先级排序。

决策链路（急性缺血性卒中的临床推理顺序）：
    再灌注治疗（时间窗内溶栓/取栓）→ 大血管闭塞(LVO)评估 → 血压管理 → 病因评估 → 二级预防

设计原则：
    - 规则优先：关键词加权打分，确定性、离线可测、零 API 开销。
    - LLM 增强为可选项（传入 llm 参数时做二次确认，失败自动回退规则结果）。

用法：
    plan_decision_nodes("左侧MCA闭塞，发病3小时，能否静脉溶栓？")
    # → ["reperfusion", "lvo"]（按临床优先级顺序）
"""

import logging
import re
from typing import List, Optional

from .labels import (
    DECISION_NODE_KEYWORDS,
    DECISION_NODE_NAMES_CN,
    DECISION_NODES,
)

logger = logging.getLogger(__name__)


def _score_nodes(text: str) -> dict:
    """对每个决策节点做关键词加权打分。"""
    lowered = (text or "").lower()
    scores: dict = {}
    for node in DECISION_NODES:
        score = 0
        for keyword, weight in DECISION_NODE_KEYWORDS[node].items():
            if keyword.lower() in lowered:
                score += weight
        if score > 0:
            scores[node] = score
    return scores


def plan_decision_nodes(question: str) -> List[str]:
    """
    把临床问题拆成决策节点，按临床优先级顺序返回命中的节点。

    优先级固定：reperfusion → lvo → blood_pressure → etiology → secondary_prevention。

    参数:
        question: 用户临床问题 / 学习问题

    返回:
        命中且按优先级排序的决策节点 key 列表（可为空）
    """
    if not question or not question.strip():
        return []
    scores = _score_nodes(question)
    if not scores:
        return []
    return [node for node in DECISION_NODES if node in scores]


def plan_decision_nodes_with_llm(
    question: str,
    llm=None,
) -> List[str]:
    """
    规则优先 + 可选 LLM 增强的决策规划。

    规则已给出确定结果时直接返回；LLM 仅在传入且规则结果为空时用于兜底判断。
    任何 LLM 异常都回退规则结果，保证链路不因外部依赖而中断。
    """
    rule_result = plan_decision_nodes(question)
    if rule_result or llm is None:
        return rule_result

    try:
        from langchain_core.messages import HumanMessage
        from langchain_core.output_parsers import StrOutputParser
        from langchain_core.prompts import ChatPromptTemplate

        prompt = ChatPromptTemplate.from_messages([
            ("system", (
                "你是临床决策规划专家。将问题拆解为下列决策节点（可多选）："
                "reperfusion(再灌注治疗)、lvo(大血管闭塞评估)、"
                "blood_pressure(血压管理)、etiology(病因评估)、"
                "secondary_prevention(二级预防)。"
                "只输出 JSON 数组，如 [\"reperfusion\",\"lvo\"]。"
            )),
            ("human", f"问题：{question}\n输出 JSON 数组："),
        ])
        chain = prompt | llm | StrOutputParser()
        content = chain.invoke({"question": question})
        match = re.search(r"\[[^\]]*\]", content)
        if not match:
            return rule_result
        import json
        nodes = json.loads(match.group(0))
        valid = [n for n in nodes if n in DECISION_NODES]
        # 按临床优先级排序
        return [n for n in DECISION_NODES if n in valid]
    except Exception as exc:
        logger.warning("[planner] LLM 决策规划失败，回退规则结果: %s", exc)
        return rule_result


def format_decision_plan(nodes: List[str]) -> str:
    """把决策节点列表格式化为可读的中文说明（用于日志/证据标注）。"""
    if not nodes:
        return "无特定决策节点"
    return " → ".join(
        DECISION_NODE_NAMES_CN.get(node, node) for node in nodes
    )
