"""自实现 SSE（Server-Sent Events）响应组件。

替代已归档、停止维护的 sse-starlette。序列化约定与其 3.x 版本保持一致：
- str 内容包装为 ``data: <内容>`` 帧，多行内容拆成多条 data: 行，事件间空行分隔
- dict 内容序列化为 JSON 后同上
- 带 event/data/id/retry/comment 控制键的 dict 视为命名事件（与 sse-starlette 一致）
- bytes 内容原样透传（调用方已自行格式化）
- 传入 ping=N 时，若上游 N 秒内无输出，自动发送注释帧 ": ping" 作为心跳，
  防止反向代理/连接空闲超时误杀长推理流
"""
import asyncio
import json
import logging
from typing import Any, AsyncIterable, Iterable, Optional, Union

from starlette.responses import StreamingResponse

logger = logging.getLogger(__name__)

_SEP = "\r\n"
_SSE_CONTROL_KEYS = {"event", "data", "id", "retry", "comment"}


def _split_lines(text: str):
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def encode_event(data: Any) -> bytes:
    """把单条事件内容编码为 SSE 帧（含结尾空行分隔符）。"""
    if isinstance(data, bytes):
        return data
    if isinstance(data, dict) and (_SSE_CONTROL_KEYS & set(data.keys())):
        return _encode_named_event(data)
    if isinstance(data, dict):
        text = json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    else:
        text = str(data)
    lines = [f"data: {chunk}" for chunk in _split_lines(text)]
    return (_SEP.join(lines) + _SEP + _SEP).encode("utf-8")


def _encode_named_event(event: dict) -> bytes:
    """编码带控制键的命名事件（event/data/id/retry/comment），顺序与 sse-starlette 一致。"""
    lines = []
    if event.get("comment") is not None:
        lines.extend(f": {chunk}" for chunk in _split_lines(str(event["comment"])))
    if event.get("id") is not None:
        lines.append(f"id: {event['id']}")
    if event.get("event") is not None:
        lines.append(f"event: {event['event']}")
    if event.get("retry") is not None:
        lines.append(f"retry: {event['retry']}")
    if event.get("data") is not None:
        lines.extend(f"data: {chunk}" for chunk in _split_lines(str(event["data"])))
    return (_SEP.join(lines) + _SEP + _SEP).encode("utf-8")


_END = object()  # 流结束哨兵


async def _idle_ping(source: AsyncIterable, ping: float):
    """上游空闲超过 ping 秒时插入心跳注释帧。

    用独立生产者任务 + 队列解耦：心跳超时只取消「队列接收」，
    不会把 CancelledError 传播进上游生成器（asyncio.timeout 直接包裹
    __anext__() 时，超时会取消生成器内部挂起的 await，导致流被截断）。
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=64)

    async def producer():
        try:
            async for item in source:
                await queue.put(item)
        finally:
            await queue.put(_END)

    producer_task = asyncio.create_task(producer())
    try:
        while True:
            try:
                async with asyncio.timeout(ping):
                    item = await queue.get()
            except TimeoutError:
                yield ": ping"
                continue
            if item is _END:
                break
            yield item
    finally:
        producer_task.cancel()


async def _encode_async(source: AsyncIterable):
    async for item in source:
        yield encode_event(item)


def _encode_sync(source: Iterable):
    for item in source:
        yield encode_event(item)


class EventSourceResponse(StreamingResponse):
    """SSE 流式响应（text/event-stream），用法与 sse-starlette 的 EventSourceResponse 一致。"""

    def __init__(
        self,
        content: Union[AsyncIterable, Iterable],
        ping: Optional[float] = None,
        status_code: int = 200,
        headers: Optional[dict] = None,
        media_type: str = "text/event-stream",
    ):
        if hasattr(content, "__aiter__"):
            if ping is not None:
                content = _idle_ping(content, ping)
            body = _encode_async(content)
        else:
            body = _encode_sync(content)

        merged_headers = {
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
        if headers:
            merged_headers.update(headers)

        super().__init__(
            body,
            media_type=media_type,
            status_code=status_code,
            headers=merged_headers,
        )
