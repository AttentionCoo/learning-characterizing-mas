import logging
import json
from typing import Dict
from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from app.agents.core.schema import LearningState
from app.agents.orchestrators.nodes.base import BaseNode

logger = logging.getLogger(__name__)

_STROKE_KEYWORDS = [
    "脑卒中", "中风", "卒中", "脑梗", "脑梗死", "脑出血",
    "缺血性卒中", "出血性卒中", "脑血栓", "脑栓塞", "蛛网膜下腔出血",
    "脑血管", "脑缺血", "腔隙性梗死", "TIA", "短暂性脑缺血",
    "偏瘫", "失语", "吞咽困难", "构音障碍",
    "溶栓", "取栓", "颈动脉", "动脉溶栓", "支架",
    "NIHSS", "mRS", "ASPECTS",
    "rtPA", "阿替普酶", "替奈普酶",
    "stroke", "cerebral infarction", "cerebral hemorrhage",
    "康复训练", "肢体康复", "语言康复", "吞咽康复",
    "脑卒中护理", "卒中单元", "卒中中心",
    "二级预防", "抗血小板", "抗凝", "降脂", "降压",
    "脑卒中指南", "卒中指南",
    "CT", "MRI", "DWI", "CTA", "MRA",
    "静脉溶栓", "机械取栓", "去骨瓣",
    "脑水肿", "颅内压", "脑疝",
    "卒中后抑郁", "卒中后认知",
    "FAST", "BE-FAST", "120",
]

_LEARNING_KEYWORDS = [
    "学习", "复习", "考试", "试题", "题目", "练习", "知识点",
    "课程", "教学", "讲解", "辅导", "答疑", "笔记", "总结",
    "资料", "文献", "论文", "指南", "共识", "教材",
    "病例", "案例", "查房", "实习", "规培", "住院医",
    "思维导图", "记忆", "背诵", "理解", "掌握",
    "评估", "测试", "测验", "考核",
    "路径", "计划", "规划", "进度",
    "画像", "水平", "基础", "薄弱",
]


_INTENT_PROMPT = ChatPromptTemplate.from_messages([
    ("human", """你是意图分类专家。请判断以下输入的类型、难度以及是否与脑卒中学习相关。

类型说明：
- profile: 学习画像构建或更新（包含学生专业、年级、学习背景、知识水平等信息）
- resource: 个性化学习资源生成（请求生成文档、题目、思维导图等学习资源）
- tutor: 智能辅导问答（学习问题咨询、知识点讲解、解题辅导等）
- assessment: 学习评估（评估学习效果、知识掌握程度等）
- learning_path: 学习路径规划（请求规划学习路径、学习计划等）
- knowledge: 通用脑卒中知识询问（概念解释、指南解读等，无个性化需求）
- irrelevant: 与脑卒中学习完全无关的问题

输入：{case_text}

输出 JSON：

{{
    "type": "profile/resource/tutor/assessment/learning_path/knowledge/irrelevant",
    "reason": "简要原因",
    "difficulty_score": 0.0,
    "is_stroke_related": true/false
}}

difficulty_score 评分标准：
- 0.0-0.2: 极简问题（如单个概念解释、简单选择题生成）
- 0.2-0.4: 简单问题（如单维度画像更新、基础知识点讲解）
- 0.4-0.6: 中等难度（如多维度画像构建、中等复杂度资源生成）
- 0.6-0.8: 较高难度（如综合评估、跨知识点资源生成、争议性医学问题）
- 0.8-1.0: 高难度（如复杂临床案例推理、多路径规划、需要深度辩论的问题）

is_stroke_related 判断标准（宽准入）：
- true: 问题与脑卒中学习有直接或间接关联，包括但不限于：
  * 脑卒中的病因、症状、诊断、治疗、康复、预防、护理、并发症
  * 脑卒中相关的病理生理机制、流行病学、临床试验、指南共识
  * 脑卒中相关的影像学（CT/MRI/CTA/MRA/DWI等）
  * 脑卒中相关的药物（溶栓药、抗血小板药、抗凝药等）
  * 脑卒中相关的手术/介入治疗（取栓、支架、去骨瓣等）
  * 脑卒中康复训练、护理技巧、二级预防
  * 脑卒中相关的学习、考试、复习、病例分析、临床实践
  * 脑卒中相关的评分量表（NIHSS/mRS/ASPECTS等）
  * 任何围绕脑卒中展开的学习需求
- false: 问题与脑卒中学习完全无关，如：纯生活娱乐、非医学领域、其他疾病领域且与脑卒中无关联

注意：只要问题涉及脑卒中相关内容的学习，就应该判定为 is_stroke_related=true。""")
])


class IntentNode(BaseNode):

    def __init__(self, llm):
        self.chain = _INTENT_PROMPT | llm | StrOutputParser()

    def _has_stroke_keyword(self, text: str) -> bool:
        text_lower = text.lower()
        return any(kw.lower() in text_lower for kw in _STROKE_KEYWORDS)

    def _has_learning_keyword(self, text: str) -> bool:
        text_lower = text.lower()
        return any(kw.lower() in text_lower for kw in _LEARNING_KEYWORDS)

    def _is_stroke_related(self, value) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() == "true"
        return False

    async def run(self, state: LearningState) -> Dict:
        case_text = state["case_text"]

        has_stroke = self._has_stroke_keyword(case_text)
        has_learning = self._has_learning_keyword(case_text)

        if not has_stroke and not has_learning:
            logger.info(f"[intent] 关键词预检未通过（无脑卒中关键词也无学习关键词），直接拦截")
            return {"intent_type": "non_stroke", "difficulty_score": 0.0}

        content = await self.chain.ainvoke({"case_text": case_text})
        result = self._parse_json(content)
        intent_type = result.get("type", "irrelevant")
        difficulty_score = result.get("difficulty_score", 0.5)
        is_stroke_related = result.get("is_stroke_related", False)

        try:
            difficulty_score = float(difficulty_score)
            difficulty_score = max(0.0, min(1.0, difficulty_score))
        except (ValueError, TypeError):
            difficulty_score = 0.5

        if has_stroke and not self._is_stroke_related(is_stroke_related):
            is_stroke_related = True
            if intent_type == "irrelevant":
                intent_type = "knowledge"
            logger.info(f"[intent] 关键词命中脑卒中但LLM判定为不相关，以关键词为准放行")

        if not self._is_stroke_related(is_stroke_related):
            intent_type = "non_stroke"
            logger.info(f"[intent] LLM判定非脑卒中相关，已拦截")

        logger.info(f"[intent] 分类结果: {intent_type}, 难度评分: {difficulty_score:.2f}, 脑卒中相关: {is_stroke_related}")
        return {"intent_type": intent_type, "difficulty_score": difficulty_score}

    def _parse_json(self, text: str):
        try:
            return json.loads(text)
        except:
            return {"type": "irrelevant", "difficulty_score": 0.5, "is_stroke_related": False}