"""Profile Update Candidate 生成器。

多 Agent 会话结束后，从对话中提取"有证据支撑的画像更新候选"：
- 只收录学生明确陈述或表现型证据（user_statement / case_performance）；
- 每条候选必须携带 evidence（原话引用/表现数据），无证据的候选直接丢弃；
- 候选经后端 ProfileMergePolicy 状态感知合并后才决定是否写入长期画像，
  实现"Reasoning → Candidate → 校验 → Profile"的闭环，杜绝推理结果污染画像。

供 agent_runner 在所有会话类型（profile/tutor/assessment 等）结束时调用。
"""
import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.utils.json_parser import JsonParser

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = "你是学习画像更新评估专家，只输出 JSON 数组。"

_SOURCE_VALUES = ("user_statement", "inferred", "case_performance", "unknown")

# 允许更新的维度白名单
_DIMENSION_KEYS = (
    "knowledgeBase", "cognitiveStyle", "learningGoal", "errorPattern",
    "learningPace", "resourcePreference", "clinicalExperience", "emotionState",
)

# knowledgeBase 子主题白名单
_TOPIC_KEYS = (
    "willis_circle", "ica_system", "mca", "aca", "pca",
    "vertebrobasilar", "brainstem", "cerebellum", "venous_system",
)

# 允许更新的标量字段白名单
_FIELD_KEYS = (
    "level", "weeklyHours", "shortTerm", "longTerm", "currentCourse",
    "speed", "type", "status", "errorType",
)

_PROMPT_TEMPLATE = """你是学习画像更新评估专家。请从以下对话中，找出【值得写入学生长期学习画像的事实更新】。

对话内容：
{conversation}

只收录以下两类信息：
1. user_statement：学生明确陈述的身份、基础、目标、薄弱点、偏好、时间安排、临床经验、情绪
   （如"我每周能学12小时""MCA和PCA供血区域比较容易搞混""我偏好看视频"）
2. case_performance：本次会话中出现的答题/测验/病例表现证据

不收录：
- 系统给出的建议、鼓励语、教学内容、指南摘录
- 学生没有明确表述、纯属推测的内容
- 已经存在于对话历史但本次没有新信息的重复内容

输出 JSON 数组（没有则输出 []）：
[
  {{
    "dimension": "knowledgeBase/cognitiveStyle/learningGoal/errorPattern/learningPace/resourcePreference/clinicalExperience/emotionState",
    "field": "level/weeklyHours/shortTerm/longTerm/currentCourse/speed/type/status/errorType（可选，与 topic 二选一）",
    "value": 字段新值,
    "topic": "willis_circle/ica_system/mca/aca/pca/vertebrobasilar/brainstem/cerebellum/venous_system（可选，仅 dimension 为 knowledgeBase 时）",
    "topic_status": "unknown/weak/ok（可选，topic 存在时必填）",
    "source": "user_statement/case_performance",
    "confidence": 0.0,
    "evidence": "学生原话引用或表现数据（必填，无法引用则不要输出该条）",
    "reason": "一句话说明为什么值得更新"
  }}
]

规则：
- source 只用 user_statement 或 case_performance；拿不准就丢弃该条
- evidence 必须直接引用学生原话（可截取）或具体表现数据，否则丢弃
- confidence：user_statement 0.8~1.0；case_performance 按正确率 0.5~0.9
- 只输出 JSON 数组，不要 markdown 代码块，不要任何解释"""


def _normalize_candidates(raw_list) -> list:
    """过滤非法维度/主题/字段/来源，丢弃无证据的候选。"""
    if not isinstance(raw_list, list):
        return []
    normalized = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        dimension = str(item.get("dimension", "")).strip()
        if dimension not in _DIMENSION_KEYS:
            continue
        source = str(item.get("source", "")).strip().lower()
        if source not in ("user_statement", "case_performance"):
            continue
        evidence = str(item.get("evidence", "") or "").strip()
        if not evidence:
            continue
        try:
            confidence = float(item.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        confidence = round(max(0.0, min(1.0, confidence)), 2)
        candidate = {
            "dimension": dimension,
            "source": source,
            "confidence": confidence,
            "evidence": evidence,
            "reason": str(item.get("reason", "") or "").strip(),
        }
        topic = str(item.get("topic", "") or "").strip()
        if topic:
            if dimension != "knowledgeBase" or topic not in _TOPIC_KEYS:
                continue
            topic_status = str(item.get("topic_status", "") or "").strip().lower()
            if topic_status not in ("unknown", "weak", "ok"):
                continue
            candidate["topic"] = topic
            candidate["topic_status"] = topic_status
        else:
            field = str(item.get("field", "") or "").strip()
            if field not in _FIELD_KEYS:
                continue
            candidate["field"] = field
            candidate["value"] = item.get("value")
        normalized.append(candidate)
    return normalized


async def generate_profile_candidates(llm, conversation: str) -> list:
    """从对话生成画像更新候选；失败或空对话返回 []。"""
    if not llm or not (conversation or "").strip():
        return []
    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=_PROMPT_TEMPLATE.format(
            conversation=(conversation or "")[:6000],
        )),
    ]
    try:
        response = await llm.ainvoke(messages)
        content = getattr(response, "content", "")
        raw = JsonParser.parse(content)
        candidates = _normalize_candidates(raw)
        if candidates:
            logger.info(
                "[profile_candidates] 生成 %d 条画像更新候选",
                len(candidates),
            )
        return candidates
    except Exception as e:
        logger.error(f"[profile_candidates] 候选生成异常: {e}", exc_info=True)
        return []
