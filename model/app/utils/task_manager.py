import asyncio
import logging
import time
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class TaskInfo:
    def __init__(self, task_id: str, task_type: str, metadata: Dict = None):
        self.task_id = task_id
        self.task_type = task_type
        self.status: str = "running"
        self.events: List[Dict] = []
        self.result: Optional[str] = None
        self.created_at: float = time.time()
        self.completed_at: Optional[float] = None
        self.metadata: Dict = metadata or {}
        self._new_event = asyncio.Event()

    def add_event(self, event: Dict):
        self.events.append(event)
        self._new_event.set()

    def complete(self, result: str = None):
        self.status = "completed"
        self.result = result
        self.completed_at = time.time()
        self._new_event.set()
        logger.info(f"[task] 任务 {self.task_id} 完成, 事件数: {len(self.events)}")

    def fail(self, error: str):
        self.status = "failed"
        self.result = error
        self.completed_at = time.time()
        self._new_event.set()
        logger.error(f"[task] 任务 {self.task_id} 失败: {error}")

    async def wait_for_new_event(self, current_index: int, timeout: float = 2.0) -> bool:
        if current_index < len(self.events):
            return True
        if self.status in ("completed", "failed"):
            return True
        self._new_event.clear()
        if current_index < len(self.events):
            return True
        try:
            await asyncio.wait_for(self._new_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass
        return current_index < len(self.events) or self.status in ("completed", "failed")


class AsyncTaskManager:
    MAX_TASKS = 500
    MAX_AGE_SECONDS = 24 * 3600

    def __init__(self):
        self.tasks: Dict[str, TaskInfo] = {}

    def create_task(self, task_id: str, task_type: str, metadata: Dict = None) -> TaskInfo:
        task = TaskInfo(task_id, task_type, metadata)
        self.tasks[task_id] = task
        self._cleanup_old_tasks()
        logger.info(f"[task] 创建任务 {task_id}, 类型: {task_type}")
        return task

    def get_task(self, task_id: str) -> Optional[TaskInfo]:
        return self.tasks.get(task_id)

    def add_event(self, task_id: str, event: Dict):
        task = self.tasks.get(task_id)
        if task:
            task.add_event(event)

    def complete_task(self, task_id: str, result: str = None):
        task = self.tasks.get(task_id)
        if task:
            task.complete(result)

    def fail_task(self, task_id: str, error: str):
        task = self.tasks.get(task_id)
        if task:
            task.fail(error)

    def _cleanup_old_tasks(self):
        if len(self.tasks) <= self.MAX_TASKS:
            return
        now = time.time()
        expired = [
            tid for tid, task in self.tasks.items()
            if task.status in ("completed", "failed")
            and (now - (task.completed_at or task.created_at)) > self.MAX_AGE_SECONDS
        ]
        for tid in expired:
            del self.tasks[tid]
        if expired:
            logger.info(f"[task] 清理了 {len(expired)} 个过期任务")