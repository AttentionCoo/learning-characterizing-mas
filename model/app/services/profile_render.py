"""学习画像证据渲染器。

把证据链画像维度确定性渲染为"克制"报告，替代 LLM 自由生成的画像报告，
杜绝下游 Report Generator 二次推断（beginner/none 等）污染 Profile。

只渲染有证据支撑的事实，其余一律"待评估"。
"""
from typing import Dict, List

_DIM_LABELS = {
    "knowledgeBase": "知识基础",
    "cognitiveStyle": "认知风格",
    "learningGoal": "学习目标",
    "errorPattern": "易错模式",
    "learningPace": "学习节奏",
    "resourcePreference": "资源偏好",
    "clinicalExperience": "临床经验",
    "emotionState": "当前状态",
}

_STATUS_ICON = {
    "confirmed": "✅",
    "observed": "📝",
    "inferred": "🧠",
    "suspected": "⚠️",
    "unknown": "❓",
}

# 缺失字段 → 最有信息增益的追问（Diagnostic Interview：优先问能同时补全多个维度的问题）
_MISSING_QUESTIONS = {
    "knowledgeBase": "如果不看资料，你能否说出大脑中动脉主要供应哪些区域？（可同时判断知识水平与解剖薄弱点）",
    "clinicalExperience": "你有无临床实习/见习经历？（判断临床经验维度）",
    "learningPace": "你每周大概能投入多少小时、单次学多久？（判断学习节奏）",
    "errorPattern": "你最近做题或看书时，最容易在哪些知识点出错或混淆？（判断易错模式）",
    "cognitiveStyle": "除了视频，你还偏好阅读、画图还是动手练习？（补充认知风格）",
}


def _collect_facts(key: str, dim: Dict) -> List[str]:
    """收集该维度中有值的用户事实字段（仅 confirmed/observed 维度的非空字段）。"""
    facts: List[str] = []
    if key == "learningGoal":
        if dim.get("currentCourse"):
            facts.append(f"当前课程「{dim['currentCourse']}」")
        if dim.get("shortTerm"):
            facts.append(f"短期目标「{dim['shortTerm']}」")
        if dim.get("longTerm"):
            facts.append(f"长期目标「{dim['longTerm']}」")
    elif key == "knowledgeBase":
        if dim.get("weakTopics"):
            facts.append(f"薄弱「{'、'.join(dim['weakTopics'])}」")
        if dim.get("masteredTopics"):
            facts.append(f"已掌握「{'、'.join(dim['masteredTopics'])}」")
        topics = dim.get("topics") or {}
        known_topics = [
            t for t in topics.values()
            if isinstance(t, dict) and t.get("status") in ("weak", "ok")
            and t.get("ev_status") in ("confirmed", "observed")
        ]
        if known_topics:
            for t in known_topics:
                facts.append(f"知识点「{t.get('label', t.get('key', ''))}」{t['status']}")
    elif key in ("resourcePreference", "cognitiveStyle"):
        if dim.get("preferences"):
            facts.append(f"偏好「{'、'.join(dim['preferences'])}」")
    elif key == "learningPace":
        if dim.get("weeklyHours"):
            facts.append(f"每周 {dim['weeklyHours']} 小时")
    elif key == "clinicalExperience":
        if dim.get("level"):
            facts.append(dim["level"])
    elif key == "errorPattern":
        if dim.get("frequentErrors"):
            facts.append(f"易错「{'、'.join(dim['frequentErrors'])}」")
    elif key == "emotionState":
        if dim.get("status"):
            facts.append(dim["status"])
    return facts


def _is_pending(key: str, dim: Dict) -> bool:
    """判断该维度是否有"待评估"的枚举/数值字段（无证据）。"""
    if key == "knowledgeBase":
        return not dim.get("level")
    if key == "cognitiveStyle":
        return not dim.get("type")
    if key == "errorPattern":
        return not dim.get("errorType")
    if key == "learningPace":
        return not dim.get("weeklyHours") and not dim.get("speed")
    if key == "clinicalExperience":
        return not dim.get("level")
    return False


def render_profile_report(dimensions: Dict) -> str:
    """把证据链画像维度渲染为"克制"的 Markdown 报告。"""
    if not dimensions:
        return "## 🧠 学习画像\n\n暂无已确认的画像信息。"

    lines = ["## 🧠 学习画像", ""]
    confirmed: List[str] = []
    pending: List[str] = []

    for key, label in _DIM_LABELS.items():
        dim = dimensions.get(key)
        if not isinstance(dim, dict):
            continue
        ev_status = dim.get("ev_status", "unknown")
        facts = _collect_facts(key, dim)
        if facts and ev_status in ("confirmed", "observed"):
            icon = _STATUS_ICON.get(ev_status, "✅")
            confirmed.append(f"- **{label}**：{'；'.join(facts)} {icon}")
        elif _is_pending(key, dim):
            pending.append(label)

    if confirmed:
        lines.append("### ✅ 已确认（有证据）")
        lines.extend(confirmed)
        lines.append("")

    if pending:
        lines.append("### ❓ 待评估（暂无证据）")
        lines.append("、".join(pending))
        lines.append("")

    # 自适应诊断式追问：优先问信息增益最高、能一次补全多个维度的缺失项
    questions = [
        f"- {_MISSING_QUESTIONS[k]}"
        for k in _DIM_LABELS
        if k in pending and k in _MISSING_QUESTIONS
    ]
    if questions:
        lines.append("### 💬 建议补充（优先回答最有价值的问题）")
        lines.extend(questions[:3])
        lines.append("")

    lines.append("> 本画像只记录有证据支撑的事实；待评估项会在你补充信息或完成测验后更新。")
    return "\n".join(lines)
