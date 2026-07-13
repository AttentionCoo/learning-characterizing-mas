"""代码执行接口：赛题「代码辅助开发」模块。

代码辅助（补全/诊断/优化）为 SSE 流式业务，统一走 /model/get_result
的 report_mode=code_assist；本路由同时提供沙箱执行和独立的代码辅助 SSE 端点。
"""
import asyncio
import json
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.runtime import resources, verify_token
from app.services.agent_runner import run_agent_background, stream_task_events
from app.services.code_sandbox import SUPPORTED_LANGUAGES, run_python
from app.utils.error_codes import build_error_event

logger = logging.getLogger(__name__)
router = APIRouter()


class CodeExecuteRequest(BaseModel):
    code: str
    language: str = "python"
    timeout: int = 30
    input_data: Optional[str] = None


class CodeAssistRequest(BaseModel):
    """代码辅助流式请求（补全/诊断/优化/讲解）。"""
    assistType: str = "complete"  # complete / diagnose / optimize / explain
    prompt: Optional[str] = ""
    language: str = "python"
    existingCode: Optional[str] = ""
    errorMessage: Optional[str] = None


# ── 辅助类型中文标签映射 ──
_ASSIST_TYPE_LABELS = {
    "complete": "代码补全",
    "diagnose": "错误诊断",
    "optimize": "优化建议",
    "explain": "代码讲解",
}


def _build_code_assist_question(params: CodeAssistRequest) -> str:
    """将 CodeAssistRequest 拼接为模型推理用的完整提示词。"""
    parts = []
    label = _ASSIST_TYPE_LABELS.get(params.assistType, params.assistType)
    parts.append(f"辅助类型：{label}")

    if params.prompt and params.prompt.strip():
        parts.append(f"诉求：{params.prompt.strip()}")

    parts.append(f"语言：{params.language or 'python'}")

    if params.existingCode and params.existingCode.strip():
        parts.append(f"现有代码：\n```python\n{params.existingCode.strip()}\n```")

    if params.errorMessage and params.errorMessage.strip():
        parts.append(f"运行报错：\n```\n{params.errorMessage.strip()}\n```")

    return "\n".join(parts)


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


@router.post("/model/code/assist")
async def code_assist(request: CodeAssistRequest):
    """代码辅助 SSE 流式接口：补全/诊断/优化/讲解。

    内部委托给多智能体推理流水线，设置 report_mode=code_assist，
    与 /model/get_result 共享同一推理后端。
    """
    agent = resources.get("model")
    if not agent:
        raise HTTPException(status_code=503, detail="Model service not ready")

    task_mgr = resources["task_manager"]
    task_id = uuid.uuid4().hex

    question = _build_code_assist_question(request)
    logger.info("[code_assist] task_id=%s assistType=%s prompt_len=%d code_len=%d",
                task_id, request.assistType, len(request.prompt or ""), len(request.existingCode or ""))

    task_mgr.create_task(task_id, "code_assist", {})

    asyncio.create_task(run_agent_background(
        task_id=task_id,
        agent=agent,
        case_text=question,
        all_info="",
        report_mode="code_assist",
        task_mgr=task_mgr,
        naming_model=resources.get("naming_model"),
        executor=resources.get("executor"),
        naming_input=question,
        update_all_info=False,
        original_all_info="",
    ))

    init_event = {"type": "init", "taskId": task_id}
    return EventSourceResponse(stream_task_events(task_id, task_mgr, init_event), ping=15)
