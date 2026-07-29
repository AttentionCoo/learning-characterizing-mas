"""核心推理流式接口：Java 后端所有 SSE 业务均经由 /model/get_result 进入。"""
import asyncio
import json
import logging
import uuid
from typing import List

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.runtime import resources, verify_token
from app.services.agent_runner import run_agent_background, stream_task_events

logger = logging.getLogger(__name__)
router = APIRouter()


class QueryRequest(BaseModel):
    question: str
    round: int = 2
    all_info: str = ""
    token: str
    report_mode: str = "emergency"
    show_thinking: bool = True
    images: List[str] = Field(default_factory=list)


@router.post("/model/get_result")
async def get_model_result(request: QueryRequest):
    """多智能体推理统一入口（SSE 流式 + 后台持久化）"""
    verify_token(request.token)

    agent = resources.get("model")
    if not agent:
        raise HTTPException(status_code=503, detail="Model service not ready")

    task_mgr = resources["task_manager"]
    task_id = uuid.uuid4().hex

    task_mgr.create_task(task_id, "legacy_query", {})

    asyncio.create_task(run_agent_background(
        task_id=task_id,
        agent=agent,
        case_text=request.question,
        all_info=request.all_info,
        report_mode=request.report_mode,
        task_mgr=task_mgr,
        naming_model=resources.get("naming_model") if not request.all_info else None,
        executor=resources.get("executor"),
        naming_input=request.question if not request.all_info else None,
        update_all_info=True,
        original_all_info=request.all_info,
        images=request.images,
    ))

    init_event = {"type": "init", "taskId": task_id}
    return EventSourceResponse(stream_task_events(task_id, task_mgr, init_event), ping=15)


@router.get("/model/tasks/{task_id}")
async def get_task_status(task_id: str = Path(...)):
    """查询后台任务状态与结果（切换页面后轮询此接口获取结果）"""
    task_mgr = resources["task_manager"]
    task = task_mgr.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    token_events = []
    for e in task.events:
        if e.get("type") == "token":
            token_events.append(e.get("content", ""))

    return {
        "taskId": task.task_id,
        "taskType": task.task_type,
        "status": task.status,
        "result": task.result,
        "content": "".join(token_events),
        "events": task.events,
        "metadata": task.metadata,
        "createdAt": task.created_at,
        "completedAt": task.completed_at,
    }


@router.get("/model/tasks/{task_id}/stream")
async def stream_task_result(
    task_id: str = Path(...),
    last_event_index: int = Query(0, ge=0, description="上次接收到的最后事件索引"),
):
    """重连后台任务的 SSE 流（切换页面后用此接口继续接收事件）"""
    task_mgr = resources["task_manager"]
    task = task_mgr.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return EventSourceResponse(
        stream_task_events(task_id, task_mgr, None) if last_event_index == 0 else _resume_events(task_id, task_mgr, last_event_index),
        ping=15,
    )


async def _resume_events(task_id: str, task_mgr, last_event_index: int):
    event_index = last_event_index
    while True:
        task = task_mgr.get_task(task_id)
        if not task:
            yield json.dumps({"type": "error", "content": "Task not found"}, ensure_ascii=False)
            return
        while event_index < len(task.events):
            yield json.dumps(task.events[event_index], ensure_ascii=False)
            event_index += 1
        if task.status in ("completed", "failed"):
            return
        await task.wait_for_new_event(event_index, timeout=2.0)
