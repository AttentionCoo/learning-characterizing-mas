"""学习方案动态优化接口。"""
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from app.agents.utils.json_parser import JsonParser
from app.runtime import resources

logger = logging.getLogger(__name__)
router = APIRouter()


class EvaluationOptimizeRequest(BaseModel):
    pathId: int
    triggerReason: str = "auto"
    evaluationData: Optional[Dict[str, Any]] = None
    pathInfo: Optional[Dict[str, Any]] = None
    steps: Optional[List[Dict[str, Any]]] = None


@router.post("/model/evaluation/optimize")
async def optimize_learning(request: EvaluationOptimizeRequest):
    """触发学习方案动态优化"""
    llm_turbo = resources.get("llm_turbo")
    if not llm_turbo:
        raise HTTPException(status_code=503, detail="LLM service not ready")

    try:
        evaluation_str = json.dumps(request.evaluationData, ensure_ascii=False) if request.evaluationData else "无评估数据"
        path_info_str = json.dumps(request.pathInfo, ensure_ascii=False) if request.pathInfo else "无路径信息"
        steps_str = json.dumps(request.steps, ensure_ascii=False) if request.steps else "无步骤信息"

        completed_count = sum(1 for s in (request.steps or []) if s.get("status") == "completed")
        not_started_count = sum(1 for s in (request.steps or []) if s.get("status") == "not_started")
        overall_score = 0
        if request.evaluationData and isinstance(request.evaluationData, dict):
            overall_score = request.evaluationData.get("overallScore", 0)

        prompt = f"""你是高等教育学习方案优化专家。请根据以下评估数据和学习路径信息，给出具体的优化方案。

学习路径ID：{request.pathId}
触发原因：{request.triggerReason}
综合评分：{overall_score}

学习路径信息：{path_info_str}

学习步骤详情：{steps_str}

完成情况：已完成{completed_count}步，未开始{not_started_count}步

评估数据：{evaluation_str}

请分析评估数据中的薄弱点，结合学习步骤的实际完成情况，给出优化方案。

重要规则：
- 如果综合评分>=80且无明显薄弱点，设置optimizationApplied为false
- 对于未完成且难度偏高的步骤，降低难度（adjust_difficulty）
- 对于薄弱知识点，可以插入补充步骤（insert_step）
- adjust_difficulty必须使用steps中真实的stepId
- insert_step的description写步骤标题，reason写插入原因

请直接输出JSON（不要用markdown代码块包裹）：
{{
    "pathId": {request.pathId},
    "optimizationApplied": true,
    "changes": [
        {{
            "type": "adjust_difficulty",
            "stepId": 真实步骤ID,
            "newDifficulty": "beginner或intermediate或advanced",
            "description": "调整描述",
            "reason": "调整原因"
        }}
    ],
    "newEstimatedDays": 30,
    "profileUpdated": false,
    "profileChanges": {{}}
}}"""

        response = await llm_turbo.ainvoke([HumanMessage(content=prompt)])
        content = getattr(response, "content", "")

        result = JsonParser.parse(content, default={})
        if not result:
            result = {"pathId": request.pathId, "optimizationApplied": False, "changes": [], "newEstimatedDays": 0, "profileUpdated": False, "profileChanges": {}}

        if "pathId" not in result:
            result["pathId"] = request.pathId
        if "optimizationApplied" not in result:
            result["optimizationApplied"] = False
        if "changes" not in result:
            result["changes"] = []

        return {"code": 1, "msg": "success", "data": result}

    except Exception as e:
        logger.error(f"[optimize] 学习方案优化失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
