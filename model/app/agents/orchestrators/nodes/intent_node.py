import logging
import json
from typing import Dict
from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from app.agents.core.schema import LearningState
from app.agents.orchestrators.nodes.base import BaseNode

logger = logging.getLogger(__name__)


_INTENT_PROMPT = ChatPromptTemplate.from_messages([
    ("human", """你是意图分类专家。请判断以下输入的类型和难度：

- profile: 学习画像构建或更新（包含学生专业、年级、学习背景、知识水平等信息）
- resource: 个性化学习资源生成（请求生成文档、题目、思维导图等学习资源）
- tutor: 智能辅导问答（学习问题咨询、知识点讲解、解题辅导等）
- assessment: 学习评估（评估学习效果、知识掌握程度等）
- learning_path: 学习路径规划（请求规划学习路径、学习计划等）
- knowledge: 通用教育知识询问（学习方法、概念解释等，无个性化需求）
- irrelevant: 非教育学习相关

输入：{case_text}

输出 JSON：

{{
    "type": "profile/resource/tutor/assessment/learning_path/knowledge/irrelevant",
    "reason": "简要原因",
    "difficulty_score": 0.0
}}

difficulty_score 评分标准：
- 0.0-0.2: 极简问题（如单个概念解释、简单选择题生成）
- 0.2-0.4: 简单问题（如单维度画像更新、基础知识点讲解）
- 0.4-0.6: 中等难度（如多维度画像构建、中等复杂度资源生成）
- 0.6-0.8: 较高难度（如综合评估、跨知识点资源生成、争议性医学问题）
- 0.8-1.0: 高难度（如复杂临床案例推理、多路径规划、需要深度辩论的问题）

严格区分：如果有学生具体信息和画像需求，为profile；如果是请求生成资源，为resource；如果是辅导问题，为tutor；如果是评估请求，为assessment；如果是路径规划，为learning_path；如果是一般性问题，为knowledge；否则irrelevant。""")
])


class IntentNode(BaseNode):

    def __init__(self, llm):
        self.chain = _INTENT_PROMPT | llm | StrOutputParser()

    async def run(self, state: LearningState) -> Dict:
        content = await self.chain.ainvoke({"case_text": state["case_text"]})
        result = self._parse_json(content)
        intent_type = result.get("type", "irrelevant")
        difficulty_score = result.get("difficulty_score", 0.5)

        try:
            difficulty_score = float(difficulty_score)
            difficulty_score = max(0.0, min(1.0, difficulty_score))
        except (ValueError, TypeError):
            difficulty_score = 0.5

        logger.info(f"[intent] 分类结果: {intent_type}, 难度评分: {difficulty_score:.2f}")
        return {"intent_type": intent_type, "difficulty_score": difficulty_score}

    def _parse_json(self, text: str):
        try:
            return json.loads(text)
        except:
            return {"type": "irrelevant", "difficulty_score": 0.5}