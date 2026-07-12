"""后台推理任务执行与 SSE 事件流转发。"""
import asyncio
import json
import logging
from typing import List

from app.runtime import resources
from app.services.profile_extractor import extract_profile_dimensions
from app.utils.error_codes import build_error_event
from app.utils.task_manager import AsyncTaskManager

logger = logging.getLogger(__name__)


async def stream_task_events(task_id: str, task_mgr: AsyncTaskManager, init_event: dict = None):
    if init_event:
        yield json.dumps(init_event, ensure_ascii=False)
    event_index = 0
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


async def run_agent_background(
    task_id: str,
    agent,
    case_text: str,
    all_info: str,
    report_mode: str,
    task_mgr: AsyncTaskManager,
    naming_model=None,
    executor=None,
    naming_input: str = None,
    images: List[str] = None,
    image_question: str = None,
    update_all_info: bool = False,
    original_all_info: str = "",
):
    try:
        loop = asyncio.get_running_loop()
        final_parts = []

        naming_future = None
        if naming_model and executor and naming_input:
            naming_future = loop.run_in_executor(executor, naming_model.run_naming, naming_input)

        if images:
            vision_svc = resources.get("vision_service")
            if vision_svc:
                async for event in vision_svc.analyze_stream(
                    images=images,
                    question=image_question or "",
                    all_info="",
                ):
                    if event.get("type") == "thinking":
                        task_mgr.add_event(task_id, {
                            "type": "node_start",
                            "node": "vision",
                            "label": event.get("title", "正在分析图片..."),
                        })
                    elif event.get("type") == "chunk":
                        content_str = str(event.get("content", ""))
                        if content_str:
                            final_parts.append(content_str)
                            task_mgr.add_event(task_id, {"type": "token", "content": content_str})

        async for event in agent.run_learning_reasoning(
            case_text=case_text,
            all_info=all_info,
            report_mode=report_mode,
            show_thinking=True,
        ):
            if not isinstance(event, dict):
                continue
            if event.get("type") == "error":
                task_mgr.add_event(task_id, event)
                task_mgr.fail_task(task_id, event.get("content", "Unknown error"))
                return
            if event.get("type") == "token":
                content_str = str(event.get("content", ""))
                if content_str:
                    final_parts.append(content_str)
            task_mgr.add_event(task_id, event)

        result_text = "".join(final_parts).strip()

        generated_name = None
        if naming_future:
            try:
                generated_name = await naming_future
            except Exception:
                pass

        done_event = {
            "type": "done",
            "taskId": task_id,
            "title": generated_name or "生成完成",
        }

        if update_all_info and result_text and resources.get("context_summary") and executor:
            try:
                summary_result = await loop.run_in_executor(
                    executor,
                    resources["context_summary"].update_all_info,
                    original_all_info,
                    case_text,
                    result_text,
                    0.4,
                )
                done_event["all_info"] = summary_result.get("updated_all_info", original_all_info)
            except Exception:
                done_event["all_info"] = original_all_info

        if report_mode == "profile_build" and result_text:
            try:
                logger.info("[background] 检测到画像构建模式，自动提取学习画像维度...")
                conversation_for_extract = f"用户: {case_text}\n助手: {result_text}"
                extract_result = await asyncio.wait_for(
                    extract_profile_dimensions(resources.get("llm_turbo"), conversation_for_extract),
                    timeout=30,
                )
                if extract_result:
                    done_event["profile_dimensions"] = extract_result
                else:
                    logger.warning("[background] 画像维度提取失败或为空")
            except asyncio.TimeoutError:
                logger.error("[background] 画像提取超时(30s)")
            except Exception as e:
                logger.error(f"[background] 自动提取画像异常: {e}", exc_info=True)

        task_mgr.add_event(task_id, done_event)
        task_mgr.complete_task(task_id, result=result_text)
    except Exception as e:
        logger.error(f"[background] 任务 {task_id} 失败: {e}")
        task_mgr.add_event(task_id, build_error_event(e, talk_id=None))
        task_mgr.fail_task(task_id, str(e))
