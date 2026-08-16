"""推理并发治理。

/model/get_result 与 /model/code/assist 用 asyncio.create_task 无界启动推理任务，
外部模型（DashScope）有 QPS/并发配额，突发流量会打爆配额并雪崩。
本模块提供进程级信号量，把「模型推理并发」限制在可配置上限内：
槽位占满时新请求等待 INFERENCE_SLOT_TIMEOUT 秒，超时由调用方转 503。
"""
import asyncio
import logging
import os

logger = logging.getLogger(__name__)

MAX_CONCURRENT_TASKS = int(os.getenv("MAX_CONCURRENT_TASKS", "10"))
INFERENCE_SLOT_TIMEOUT = float(os.getenv("INFERENCE_SLOT_TIMEOUT", "5"))

_semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)

logger.info(
    "🔒 推理并发治理已启用: max_concurrent=%d, acquire_timeout=%.1fs",
    MAX_CONCURRENT_TASKS,
    INFERENCE_SLOT_TIMEOUT,
)


class InferenceSlot:
    """异步上下文管理器：进入时获取推理槽位，退出时释放。

    获取超时抛出 TimeoutError，调用方应转换为 HTTP 503（服务繁忙）。
    """

    def __init__(self, timeout: float = INFERENCE_SLOT_TIMEOUT):
        self._timeout = timeout
        self._acquired = False

    async def __aenter__(self):
        try:
            await asyncio.wait_for(_semaphore.acquire(), timeout=self._timeout)
        except (asyncio.TimeoutError, TimeoutError):
            logger.warning(
                "⚠️ 推理槽位获取超时（并发已达上限 %d）", MAX_CONCURRENT_TASKS
            )
            raise TimeoutError(
                f"模型服务繁忙：并发推理已达上限 {MAX_CONCURRENT_TASKS}，请稍后重试"
            )
        self._acquired = True
        return self

    async def __aexit__(self, *exc_info):
        if self._acquired:
            _semaphore.release()
            self._acquired = False
        return False


async def acquire_slot(timeout: float = INFERENCE_SLOT_TIMEOUT) -> InferenceSlot:
    """获取推理槽位（便捷函数）。超时抛 TimeoutError。"""
    slot = InferenceSlot(timeout)
    await slot.__aenter__()
    return slot
