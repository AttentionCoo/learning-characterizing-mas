"""请求级实时事件通道（ReasonNode → 外层流式生成器）。

## 为什么需要它

ReasonNode 有两条执行路径：

1. **planner 路径**：作为图节点被 LangGraph 调用，`get_stream_writer()` 可用，
   自定义事件经 `astream(stream_mode="custom")` 正常冒泡；
2. **监督者路径**：被 `consult_experts` 工具**手工调用**（`self.reason_node.run(mini_state)`），
   此时没有 LangGraph 的 writer 上下文，`get_stream_writer()` 拿不到 writer，
   custom 事件**不会冒泡**。

第 2 条路径原先的补救办法是「先攒进 workspace，等监督者返回后由 learning_agent 补发」——
结果是专家发言、会诊对话、黑板、仲裁**全部憋到最后一刻整块出现**，前端看不到实时过程。

本模块用 ContextVar 承载一个请求级 sink：learning_agent 在驱动图之前设置，
ReasonNode 推送事件时优先使用。`asyncio.create_task` 会复制当前 context，
因此图任务内部（含图节点里嵌套调用的 ReasonNode）都能取到同一个 sink，
而不同请求之间互不干扰。
"""
import contextvars
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

EventSink = Callable[[dict], None]

_event_sink: contextvars.ContextVar[Optional[EventSink]] = contextvars.ContextVar(
    "reason_event_sink", default=None
)


def set_event_sink(sink: EventSink):
    """设置当前请求的事件 sink，返回用于恢复的 token。"""
    return _event_sink.set(sink)


def reset_event_sink(token) -> None:
    """恢复上一个 sink；token 失效时静默忽略（跨 context 重置会抛错）。"""
    if token is None:
        return
    try:
        _event_sink.reset(token)
    except Exception:  # noqa: BLE001 - 重置失败不应影响请求收尾
        pass


def get_event_sink() -> Optional[EventSink]:
    """取当前请求的事件 sink；未设置时返回 None。"""
    return _event_sink.get()
