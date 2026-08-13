import logging
import json
from typing import Dict, Any
from langchain_core.messages import HumanMessage
from app.agents.core.schema import LearningState
from app.agents.orchestrators.nodes.base import BaseNode
from app.agents.constants import MAX_SUB_QUESTIONS
from app.agents.utils.json_parser import JsonParser

logger = logging.getLogger(__name__)


class AnalysisNode(BaseNode):

    INTENT_CONTEXT_TEMPLATES = {
        "resource": json.dumps({
            "目标知识点": "",
            "资源类型": "",
            "内容范围": "",
            "难度级别": "",
            "核心概念列表": [],
            "需要覆盖的机制/流程": [],
            "适用场景": "",
            "个性化适配要点": {
                "知识基础": "",
                "认知偏好": "",
                "目标水平": ""
            }
        }, ensure_ascii=False, indent=2),

        "profile": json.dumps({
            "基本信息": {"专业": "", "年级": "", "当前课程": ""},
            "学习需求": "",
            "主要问题": [],
            "知识水平评估": {},
            "认知风格": "",
            "学习目标": [],
            "易错点": [],
            "学习节奏": {},
            "资源偏好": []
        }, ensure_ascii=False, indent=2),

        "tutor": json.dumps({
            "核心问题": "",
            "相关概念": [],
            "理解障碍": "",
            "当前理解水平": "",
            "期望解答方式": "",
            "个性化适配要点": {
                "知识基础": "",
                "认知偏好": ""
            }
        }, ensure_ascii=False, indent=2),

        "assessment": json.dumps({
            "评估对象": "",
            "评估维度": [],
            "当前水平": "",
            "待提升领域": [],
            "进步空间": [],
            "个性化适配要点": {
                "知识基础": "",
                "学习目标": ""
            }
        }, ensure_ascii=False, indent=2),

        "learning_path": json.dumps({
            "学习目标": "",
            "当前起点": "",
            "目标水平": "",
            "可用时间": "",
            "关键里程碑": [],
            "前置知识": [],
            "个性化适配要点": {
                "知识基础": "",
                "学习节奏": "",
                "资源偏好": ""
            }
        }, ensure_ascii=False, indent=2),
    }

    DEFAULT_CONTEXT_TEMPLATE = json.dumps({
        "核心需求": "",
        "关键信息": [],
        "个性化适配要点": {}
    }, ensure_ascii=False, indent=2)

    INTENT_TASK_LABELS = {
        "resource": "学习资源内容生成",
        "profile": "学生画像构建与更新",
        "tutor": "个性化问题辅导",
        "assessment": "学习效果评估",
        "learning_path": "学习路径规划",
    }

    def __init__(self, llm):
        self.llm = llm

    async def run(self, state: LearningState) -> Dict:
        analysis = await self._unified_analysis(state)
        learning_questions = analysis.get("learning_questions", ["该学生当前最紧急的学习问题和辅导要点"])

        return {
            "context": analysis.get("structured_context", {"原始输入": state["case_text"]}),
            "learning_questions": learning_questions[:MAX_SUB_QUESTIONS],
            "key_risks": analysis.get("key_risks", []),
            "complexity": analysis.get("complexity", "high"),
            "user_questions": analysis.get("user_questions", []),
        }

    async def _unified_analysis(self, state: LearningState) -> Dict[str, Any]:
        intent_type = state.get('intent_type', 'profile')
        case_text = state.get('case_text', '')
        all_info = state.get('all_info', '')

        context_template = self.INTENT_CONTEXT_TEMPLATES.get(
            intent_type,
            self.DEFAULT_CONTEXT_TEMPLATE
        )

        task_label = self.INTENT_TASK_LABELS.get(intent_type, "学习需求分析")

        intent_hint = self._get_intent_hint(intent_type, case_text)

        prompt = f"""你是高等教育学习分析专家。请对以下学生信息完成分析任务，一次性输出。

【任务类型：{task_label}】

【学生输入】
{case_text}

【历史上下文】
{all_info if all_info else "无"}

请直接输出 JSON（不要用 markdown 代码块包裹）：

{{
    "structured_context": {context_template},
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
- structured_context: 严格按照上方JSON模板结构输出，不要添加模板中没有的字段
- complexity: critical=学习困境严重
- learning_questions: 【重要】{intent_hint} 问题必须用中文，每条30字以内，用于检索教育资料
- user_questions: 若输入中学生明确提出了若干具体问题，请将每个问题原文提取为字符串数组；若无，则返回空数组。"""

        response = await self.llm.ainvoke([HumanMessage(content=prompt)])
        result = JsonParser.parse(getattr(response, "content", ""), None)

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

    @staticmethod
    def _get_intent_hint(intent_type: str, case_text: str) -> str:
        hints = {
            "resource": "资源生成方向：重点生成资源类型、难度匹配、知识点覆盖、个性化适配类问题。",
            "profile": "画像构建方向：重点生成知识基础、认知风格、学习目标、易错点、学习节奏、资源偏好类问题。",
            "tutor": "辅导答疑方向：重点生成概念理解、解题思路、易错点提示类问题。",
            "assessment": "学习评估方向：重点生成知识掌握度、技能水平、学习投入度类问题。",
            "learning_path": "路径规划方向：重点生成学习阶段、时间安排、目标分解类问题。",
        }
        return hints.get(intent_type, "综合分析方向：按学习需求优先级生成最需分析的问题，优先覆盖核心需求。")