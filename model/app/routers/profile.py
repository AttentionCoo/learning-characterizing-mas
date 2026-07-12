"""学习画像维度抽取接口（画像数据本身由 Java 侧 MySQL 持久化）。"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.runtime import resources
from app.services.profile_extractor import extract_profile_dimensions

logger = logging.getLogger(__name__)
router = APIRouter()


class ProfileExtractRequest(BaseModel):
    conversation: str
    userId: Optional[int] = None


@router.post("/model/profile/extract")
async def extract_profile(request: ProfileExtractRequest):
    """从对话内容中抽取画像维度"""
    llm = resources.get("llm_turbo")
    if not llm:
        raise HTTPException(status_code=503, detail="Model service not ready")

    dimensions = await extract_profile_dimensions(llm, request.conversation)
    if dimensions is None:
        raise HTTPException(status_code=500, detail="画像维度抽取失败")
    return {"code": 1, "msg": "success", "data": {"dimensions": dimensions}}
