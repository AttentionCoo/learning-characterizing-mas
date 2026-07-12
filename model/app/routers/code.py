"""代码执行接口：赛题「代码辅助开发」模块。

代码辅助（补全/诊断/优化）为 SSE 流式业务，统一走 /model/get_result
的 report_mode=code_assist；本路由只承载非流式的沙箱执行。
"""
import asyncio
import logging
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.code_sandbox import SUPPORTED_LANGUAGES, run_python

logger = logging.getLogger(__name__)
router = APIRouter()


class CodeExecuteRequest(BaseModel):
    code: str
    language: str = "python"
    timeout: int = 30
    input_data: Optional[str] = None


@router.post("/model/code/execute")
async def execute_code(request: CodeExecuteRequest):
    """在沙箱中执行代码并返回 stdout/stderr 与运行状态。"""
    language = (request.language or "python").strip().lower()
    if language not in SUPPORTED_LANGUAGES:
        return {"code": 0, "msg": f"暂不支持 {request.language}，当前仅支持 Python", "data": None}

    result = await asyncio.to_thread(
        run_python, request.code, request.input_data, request.timeout
    )
    logger.info("[code_sandbox] 执行完成 success=%s exit=%s time=%.2fs",
                result.success, result.exit_code, result.execution_time)
    return {"code": 1, "msg": "success", "data": result.to_dict()}
