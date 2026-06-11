import logging
import json
from typing import Dict, Any
from langchain_core.messages import HumanMessage
from app.agents.core.schema import LearningState
from app.agents.orchestrators.nodes.base import BaseNode
from app.agents.constants import MAX_SUB_QUESTIONS

logger = logging.getLogger(__name__)


class AnalysisNode(BaseNode):

    def __init__(self, llm):
        self.llm = llm

    async def run(self, state: LearningState) -> Dict:
        analysis = await self._unified_analysis(state["case_text"], state["all_info"])
        learning_questions = analysis.get("learning_questions", ["该学生当前最紧急的学习问题和辅导要点"])

        return {
            "context": analysis.get("structured_context", {"原始输入": state["case_text"]}),
            "learning_questions": learning_questions[:MAX_SUB_QUESTIONS],
            "key_risks": analysis.get("key_risks", []),
            "complexity": analysis.get("complexity", "high"),
            "user_questions": analysis.get("user_questions", []),
        }

    async def _unified_analysis(self, case_text: str, all_info: str) -> Dict[str, Any]:
        _PROFILE_KW = {"专业", "年级", "课程", "画像", "学习风格", "认知风格", "偏好"}
        _RESOURCE_KW = {"资源", "文档", "题目", "思维导图", "视频", "代码", "练习", "生成"}
        _TUTOR_KW = {"不懂", "为什么", "怎么", "如何", "解释", "区别", "原理", "方法", "辅导"}
        _ASSESSMENT_KW = {"评估", "测试", "成绩", "效果", "掌握程度", "水平"}
        _PATH_KW = {"路径", "规划", "计划", "安排", "进度", "顺序"}

        if any(kw in case_text for kw in _PROFILE_KW):
            intent_hint = "画像构建方向：重点生成知识基础、认知风格、学习目标、易错点、学习节奏、资源偏好类问题。"
        elif any(kw in case_text for kw in _RESOURCE_KW):
            intent_hint = "资源生成方向：重点生成资源类型、难度匹配、知识点覆盖、个性化适配类问题。"
        elif any(kw in case_text for kw in _TUTOR_KW):
            intent_hint = "辅导答疑方向：重点生成概念理解、解题思路、易错点提示类问题。"
        elif any(kw in case_text for kw in _ASSESSMENT_KW):
            intent_hint = "学习评估方向：重点生成知识掌握度、技能水平、学习投入度类问题。"
        elif any(kw in case_text for kw in _PATH_KW):
            intent_hint = "路径规划方向：重点生成学习阶段、时间安排、目标分解类问题。"
        else:
            intent_hint = "综合分析方向：按学习需求优先级生成最需分析的问题，优先覆盖核心需求。"

        prompt = f"""你是高等教育学习分析专家。请对以下学生信息完成三项任务，一次性输出。

【学生输入】
{case_text}

【历史上下文】
{all_info if all_info else "无"}

请直接输出 JSON（不要用 markdown 代码块包裹）：

{{
    "structured_context": {{
        "基本信息": {{"专业": "", "年级": "", "当前课程": ""}},
        "学习需求": "",
        "主要问题": [],
        "知识水平评估": {{}},
        "认知风格": "",
        "学习目标": [],
        "易错点": [],
        "学习节奏": {{}},
        "资源偏好": []
    }},
    "complexity": "low/medium/high/critical",
    "key_risks": ["最紧迫的学习问题1", "最紧迫的学习问题2"],
    "learning_questions": [
        "服务于用户问题方向的检索子问题1（30字以内）",
        "服务于用户问题方向的检索子问题2",
        "服务于用户问题方向的检索子问题3"
    ],
    "user_questions": [
        "如果输入中包含明确的问题列表，请将每个问题原文提取出来；若没有，则返回空列表"
    ]
}}

要求：
- structured_context: 提取所有学习相关信息
- complexity: critical=学习困境严重
- learning_questions: 【重要】{intent_hint} 问题必须用中文，每条30字以内，用于检索教育资料
- user_questions: 若输入中学生明确提出了若干具体问题，请将每个问题原文提取为字符串数组；若无，则返回空数组。"""

        response = await self.llm.ainvoke([HumanMessage(content=prompt)])
        result = self._parse_json(getattr(response, "content", ""), None)

        if result and isinstance(result, dict):
            result.setdefault("user_questions", [])
            return result

        return {
            "structured_context": {"原始输入": case_text},
            "complexity": "high",
            "key_risks": [],
            "learning_questions": ["该学生当前最紧急的学习问题和辅导要点"],
            "user_questions": [],
        }

    def _parse_json(self, text: str, default=None):
        content = (text or "").strip()
        try:
            return json.loads(content)
        except Exception:
            pass
        for marker in ["```json", "```"]:
            if marker in content:
                try:
                    s = content.split(marker)[1].split("```")[0].strip()
                    return json.loads(s)
                except Exception:
                    pass
        for sc, ec in [("{", "}"), ("[", "]")]:
            si, ei = content.find(sc), content.rfind(ec)
            if si != -1 and ei > si:
                try:
                    return json.loads(content[si:ei + 1])
                except Exception:
                    pass
        return default