"""学习画像维度抽取：从师生对话中提取 8 维度结构化画像。

供 /model/profile/extract 端点与画像构建后台任务共用。
"""
import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.utils.json_parser import JsonParser

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = "你是一位专业的学习画像分析专家，只输出 JSON 格式的画像维度数据。"

_EXTRACT_PROMPT_TEMPLATE = """你是一位专业的学习画像分析专家。请从以下师生对话内容中，自动抽取学生的结构化学习画像维度。

对话内容：
{conversation}

请严格按以下 JSON 格式输出，不要输出任何其他内容，不要使用 markdown 代码块：

{{
  "knowledgeBase": {{
    "level": "beginner/intermediate/advanced",
    "description": "用1-2句话概括该学生的知识基础水平，要具体、有信息量",
    "masteredTopics": ["已掌握知识点1", "已掌握知识点2"],
    "weakTopics": ["薄弱知识点1", "薄弱知识点2"]
  }},
  "cognitiveStyle": {{
    "type": "visual/auditory/kinesthetic/reading",
    "description": "用1-2句话描述该学生的认知风格特征",
    "preferences": ["偏好1", "偏好2"]
  }},
  "learningGoal": {{
    "shortTerm": "短期目标",
    "longTerm": "长期目标",
    "currentCourse": "当前课程"
  }},
  "errorPattern": {{
    "description": "用1-2句话描述该学生的易错模式",
    "frequentErrors": ["高频错误1", "高频错误2"],
    "errorType": "conceptual/careful/procedural"
  }},
  "learningPace": {{
    "speed": "slow/moderate/fast",
    "description": "用1-2句话描述该学生的学习节奏",
    "weeklyHours": 0
  }},
  "resourcePreference": {{
    "preferences": ["video", "document", "quiz"],
    "description": "用1-2句话描述该学生的资源偏好"
  }},
  "clinicalExperience": {{
    "level": "none/basic/moderate/extensive",
    "description": "用1-2句话描述该学生的临床经验"
  }},
  "emotionState": {{
    "status": "motivated/anxious/confident/overwhelmed",
    "description": "用1-2句话描述该学生当前的情绪状态"
  }}
}}

注意：
1. 只输出 JSON，不要任何解释文字
2. description 必须具体、有信息量，不要写"根据对话推断""暂无信息""信息不足"等无意义的话；如果某维度确实无法判断，description 留空字符串
3. masteredTopics/weakTopics/frequentErrors/preferences 列表中的元素要具体，不要写"待补充"等占位文字；如果无法提取则留空列表
4. level/speed/errorType 等枚举值必须从给定选项中选择"""


async def extract_profile_dimensions(llm, conversation: str) -> dict | None:
    """调用 LLM 抽取画像维度，失败返回 None。"""
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
            logger.info(f"[profile_extract] 成功提取 {len(dimensions)} 个画像维度")
            return dimensions
        logger.warning("[profile_extract] 提取结果为空或格式错误")
        return None
    except Exception as e:
        logger.error(f"[profile_extract] 画像提取异常: {e}", exc_info=True)
        return None
