"""学习画像维度抽取：从师生对话中提取 8 维度结构化画像，并携带证据链元数据。

每维度附带 source/confidence/evidence/updated_at：
- source:     user_statement（用户明确陈述）| inferred（系统推断）|
              case_performance（答题/测验表现）| unknown（无法判断）
- confidence: 0~1，置信度
- evidence:   对话原文引用（证据链，无则空）
- updated_at: 提取日期（模型层统一打戳，不依赖 LLM）

供 /model/profile/extract 端点与画像构建后台任务共用。
"""
import logging
from datetime import date

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.utils.json_parser import JsonParser

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = "你是一位专业的学习画像分析专家，只输出 JSON 格式的画像维度数据。"

# 允许的来源枚举
_SOURCE_VALUES = ("user_statement", "inferred", "case_performance", "unknown")

# 8 个画像维度（knowledgeBase 携带 topic 级知识状态）
_DIMENSION_KEYS = (
    "knowledgeBase", "cognitiveStyle", "learningGoal", "errorPattern",
    "learningPace", "resourcePreference", "clinicalExperience", "emotionState",
)

# Knowledge State 子主题（脑卒中脑血管解剖）
_KNOWLEDGE_TOPICS = (
    "willis_circle", "ica_system", "mca", "aca", "pca",
    "vertebrobasilar", "brainstem", "cerebellum", "venous_system",
)

_TOPIC_STATUS_VALUES = ("unknown", "weak", "ok")

# 证据状态五态（Evidence Status）
_STATUS_VALUES = ("confirmed", "observed", "inferred", "suspected", "unknown")


def _derive_status(source: str, evidence: str) -> str:
    """由来源+证据推导证据状态五态。"""
    if source == "user_statement":
        return "confirmed"
    if source == "case_performance":
        return "observed"
    if source == "unknown":
        return "unknown"
    # inferred：有原话证据 = 有依据推断；无证据 = 存疑待验证
    return "inferred" if evidence else "suspected"


def _topic_meta():
    return {
        "status": "unknown",          # 知识掌握状态 unknown/weak/ok
        "ev_status": "unknown",       # 证据状态五态
        "source": "unknown",
        "confidence": 0.2,
        "evidence": "",
        "updated_at": date.today().isoformat(),
    }


def _meta_field(source: str = "inferred", confidence: float = 0.5, evidence: str = ""):
    source = source if source in _SOURCE_VALUES else "inferred"
    confidence = round(max(0.0, min(1.0, confidence)), 2)
    evidence = (evidence or "").strip()
    return {
        "source": source,
        "status": _derive_status(source, evidence),
        "confidence": confidence,
        "evidence": evidence,
        "updated_at": date.today().isoformat(),
    }


def _normalize_topics(topics: dict) -> dict:
    """补齐 topic 树：缺省子主题给 unknown 状态与证据链元数据。"""
    normalized = {}
    raw = topics if isinstance(topics, dict) else {}
    for key in _KNOWLEDGE_TOPICS:
        value = raw.get(key)
        if not isinstance(value, dict):
            normalized[key] = _topic_meta()
            continue
        meta = _topic_meta()
        status = str(value.get("status", "")).strip().lower()
        if status in _TOPIC_STATUS_VALUES:
            meta["status"] = status
        src = str(value.get("source", "")).strip().lower()
        if src in _SOURCE_VALUES:
            meta["source"] = src
        try:
            conf = float(value.get("confidence", 0.2))
        except (TypeError, ValueError):
            conf = 0.2
        meta["confidence"] = round(max(0.0, min(1.0, conf)), 2)
        meta["evidence"] = str(value.get("evidence", "") or "").strip()
        meta["ev_status"] = _derive_status(meta["source"], meta["evidence"])
        # 克制：非事实证据的知识掌握状态清为 unknown
        if meta["source"] not in ("user_statement", "case_performance"):
            meta["status"] = "unknown"
        normalized[key] = {**value, **meta}
    return normalized


# 字段级证据提示词：枚举/数值字段只有在证据原文中出现这些提示时才保留
_FIELD_HINTS = {
    "knowledgeBase": {"level": ("水平", "基础", "掌握", "入门", "进阶", "高级", "零基础", "了解", "熟悉")},
    "cognitiveStyle": {"type": ("视觉", "听觉", "动觉", "阅读", "visual", "auditory", "kinesthetic", "reading")},
    "errorPattern": {"errorType": ("易错", "搞混", "混淆", "常错", "粗心", "概念", "程序", "细节", "记混")},
    "learningPace": {
        "speed": ("节奏", "快", "慢", "适中", "速度"),
        "weeklyHours": ("小时", "每周", "学时"),
    },
    "clinicalExperience": {"level": ("实习", "见习", "规培", "轮转", "临床经验", "无临床", "临床接触", "临床经历")},
}


def _apply_restraint(dimensions: dict) -> dict:
    """克制校验（字段级）：枚举/数值字段只有同时满足
    ① source 为用户陈述/测验表现 ② 证据原文包含对应提示词 才保留，
    否则清空为"待评估"，杜绝"Agent 推断 → 画像事实"。"""
    for key, value in dimensions.items():
        if not isinstance(value, dict):
            continue
        source = value.get("source", "inferred")
        evidence = (value.get("evidence") or "").strip()
        factual = source in ("user_statement", "case_performance")
        hints = _FIELD_HINTS.get(key, {})
        for field, keywords in hints.items():
            if field not in value:
                continue
            keep = factual and any(k in evidence for k in keywords)
            if not keep:
                current = value[field]
                if isinstance(current, (int, float)):
                    value[field] = 0
                else:
                    value[field] = ""
    return dimensions


def _normalize_dimensions(dimensions: dict) -> dict:
    """为每个维度补齐证据链元数据；source 非法值回退 inferred，confidence 收敛到 0~1，
    并执行克制校验（非事实证据的枚举/数值字段清空）。"""
    normalized = {}
    for key, value in (dimensions or {}).items():
        if key not in _DIMENSION_KEYS or not isinstance(value, dict):
            normalized[key] = value
            continue
        meta = _meta_field()
        raw_source = str(value.get("source", "")).strip().lower()
        if raw_source in _SOURCE_VALUES:
            meta["source"] = raw_source
        try:
            raw_conf = float(value.get("confidence", 0.5))
        except (TypeError, ValueError):
            raw_conf = 0.5
        meta["confidence"] = round(max(0.0, min(1.0, raw_conf)), 2)
        meta["evidence"] = str(value.get("evidence", "") or "").strip()
        meta["status"] = _derive_status(meta["source"], meta["evidence"])
        # 情绪状态属于"当前状态"，额外记录观测时间
        if key == "emotionState":
            meta["observed_at"] = date.today().isoformat()
        # knowledgeBase 的 topic 树：逐子主题补齐状态与证据链
        if key == "knowledgeBase":
            value = {**value, "topics": _normalize_topics(value.get("topics"))}
        normalized[key] = {**value, **meta}
    return _apply_restraint(normalized)


_EXTRACT_PROMPT_TEMPLATE = """你是一位专业的学习画像分析专家。请从以下师生对话内容中，自动抽取学生的结构化学习画像维度。

对话内容：
{conversation}

请严格按以下 JSON 格式输出，不要输出任何其他内容，不要使用 markdown 代码块：

{{
  "knowledgeBase": {{
    "level": "beginner/intermediate/advanced",
    "description": "用1-2句话概括该学生的知识基础水平，要具体、有信息量",
    "masteredTopics": ["已掌握知识点1", "已掌握知识点2"],
    "weakTopics": ["薄弱知识点1", "薄弱知识点2"],
    "topics": {{
      "willis_circle": {{"status": "unknown/weak/ok", "source": "user_statement/inferred/case_performance/unknown", "confidence": 0.0, "evidence": "原话引用（没有则空）"}},
      "ica_system": {{"status": "unknown/weak/ok", "source": "user_statement/inferred/case_performance/unknown", "confidence": 0.0, "evidence": ""}},
      "mca": {{"status": "unknown/weak/ok", "source": "user_statement/inferred/case_performance/unknown", "confidence": 0.0, "evidence": ""}},
      "aca": {{"status": "unknown/weak/ok", "source": "user_statement/inferred/case_performance/unknown", "confidence": 0.0, "evidence": ""}},
      "pca": {{"status": "unknown/weak/ok", "source": "user_statement/inferred/case_performance/unknown", "confidence": 0.0, "evidence": ""}},
      "vertebrobasilar": {{"status": "unknown/weak/ok", "source": "user_statement/inferred/case_performance/unknown", "confidence": 0.0, "evidence": ""}},
      "brainstem": {{"status": "unknown/weak/ok", "source": "user_statement/inferred/case_performance/unknown", "confidence": 0.0, "evidence": ""}},
      "cerebellum": {{"status": "unknown/weak/ok", "source": "user_statement/inferred/case_performance/unknown", "confidence": 0.0, "evidence": ""}},
      "venous_system": {{"status": "unknown/weak/ok", "source": "user_statement/inferred/case_performance/unknown", "confidence": 0.0, "evidence": ""}}
    }},
    "source": "user_statement/inferred/case_performance/unknown",
    "confidence": 0.0,
    "evidence": "对话原文引用（学生原话截取，没有则留空字符串）"
  }},
  "cognitiveStyle": {{
    "type": "visual/auditory/kinesthetic/reading",
    "description": "用1-2句话描述该学生的认知风格特征",
    "preferences": ["偏好1", "偏好2"],
    "source": "user_statement/inferred/case_performance/unknown",
    "confidence": 0.0,
    "evidence": "对话原文引用（没有则留空字符串）"
  }},
  "learningGoal": {{
    "shortTerm": "短期目标",
    "longTerm": "长期目标",
    "currentCourse": "当前课程",
    "source": "user_statement/inferred/case_performance/unknown",
    "confidence": 0.0,
    "evidence": "对话原文引用（没有则留空字符串）"
  }},
  "errorPattern": {{
    "description": "用1-2句话描述该学生的易错模式",
    "frequentErrors": ["高频错误1", "高频错误2"],
    "errorType": "conceptual/careful/procedural",
    "source": "user_statement/inferred/case_performance/unknown",
    "confidence": 0.0,
    "evidence": "对话原文引用（没有则留空字符串）"
  }},
  "learningPace": {{
    "speed": "slow/moderate/fast",
    "description": "用1-2句话描述该学生的学习节奏",
    "weeklyHours": 0,
    "source": "user_statement/inferred/case_performance/unknown",
    "confidence": 0.0,
    "evidence": "对话原文引用（没有则留空字符串）"
  }},
  "resourcePreference": {{
    "preferences": ["video", "document", "quiz"],
    "description": "用1-2句话描述该学生的资源偏好",
    "source": "user_statement/inferred/case_performance/unknown",
    "confidence": 0.0,
    "evidence": "对话原文引用（没有则留空字符串）"
  }},
  "clinicalExperience": {{
    "level": "none/basic/moderate/extensive",
    "description": "用1-2句话描述该学生的临床经验",
    "source": "user_statement/inferred/case_performance/unknown",
    "confidence": 0.0,
    "evidence": "对话原文引用（没有则留空字符串）"
  }},
  "emotionState": {{
    "status": "motivated/anxious/confident/overwhelmed",
    "description": "用1-2句话描述该学生当前的情绪状态",
    "source": "user_statement/inferred/case_performance/unknown",
    "confidence": 0.0,
    "evidence": "对话原文引用（没有则留空字符串）"
  }}
}}

source 判定规则（重要）：
- user_statement：学生明确说出（如"我是大三""我喜欢看视频"），confidence 0.8~1.0
- inferred：从对话合理推断（如"想系统学习脑卒中"推断学习动机强），confidence 0.4~0.79
- case_performance：来自答题/测验/病例表现，confidence 按正确率
- unknown：完全无法判断，confidence 0.0~0.3
- evidence 必须直接引用学生原话（可截取），没有明确原话支撑的字段 evidence 留空

knowledgeBase.topics 子主题状态判定（脑血管解剖知识状态）：
- ok：学生表现出掌握或确认已学会，confidence 0.7~1.0
- weak：学生明确说薄弱/易混淆，或表现显示掌握不佳，confidence 0.6~1.0
- unknown：对话中未提及该子主题，confidence 0.0~0.3
- 学生只说"脑血管解剖薄弱"而没有细分时，仅把被明确提到的子主题标 weak，
  其余全部 unknown，不要把整组都猜成 weak

注意：
1. 只输出 JSON，不要任何解释文字
2. description 必须具体、有信息量，不要写"根据对话推断""暂无信息""信息不足"等无意义的话；如果某维度确实无法判断，description 留空字符串
3. masteredTopics/weakTopics/frequentErrors/preferences 列表中的元素要具体，不要写"待补充"等占位文字；如果无法提取则留空列表
4. level/speed/errorType/type/status 等枚举值必须从给定选项中选择
5. 【克制】枚举与数值字段（level/type/errorType/speed/weeklyHours 等）只填写学生明确陈述的内容：
   - 学生说"我基础一般/基本掌握"才填 level；仅说"脑血管解剖薄弱"不能推断 level，level 留空
   - 学生说"我是视觉型"才填 cognitiveStyle.type；只说"喜欢看视频"只记 preferences，type 留空
   - 学生明确说每周学时/单次时长才填 weeklyHours；"建议每周几次"等系统建议绝不算学生事实
   - 学生说"我容易把 X 和 Y 搞混"才填 errorType/frequentErrors；只说"薄弱"不能推断具体易错点
6. 【建议与画像分离·只取用户陈述】输入的【用户陈述】才是事实来源；对话中助手/系统给出的"建议""推荐""计划""鼓励"（如"建议每周2-3次每次60分钟"）不是用户事实，绝不能提取为画像字段，也绝不能作为 evidence 引用
7. source 与 evidence 必须一致：evidence 引用的是学生原话才可用 user_statement；无法引用原话的推断用 inferred 且 confidence ≤ 0.6；完全拿不准用 unknown"""


async def extract_profile_dimensions(llm, conversation: str) -> dict | None:
    """调用 LLM 抽取画像维度（含证据链元数据），失败返回 None。"""
    if not llm:
        logger.warning("[profile_extract] LLM未就绪，无法提取画像")
        return None

    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=_EXTRACT_PROMPT_TEMPLATE.format(conversation=conversation)),
    ]
    try:
        response = await llm.ainvoke(messages)
        content = getattr(response, "content", "")
        dimensions = JsonParser.parse(content)
        if dimensions and isinstance(dimensions, dict):
            normalized = _normalize_dimensions(dimensions)
            logger.info(
                "[profile_extract] 成功提取 %d 个画像维度（含证据链）",
                len(normalized),
            )
            return normalized
        logger.warning("[profile_extract] 提取结果为空或格式错误")
        return None
    except Exception as e:
        logger.error(f"[profile_extract] 画像提取异常: {e}", exc_info=True)
        return None
