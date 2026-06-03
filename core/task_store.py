"""集中式任务存储 — 线程安全、自动 TTL 清理"""
import threading
import time
from typing import Any, Optional

from core.config import TASK_TTL_SECONDS

TaskDict = dict[str, Any]


class TaskStore:
    """线程安全的任务字典，带自动过期清理"""

    def __init__(self, name: str, ttl_seconds: int = TASK_TTL_SECONDS) -> None:
        self._name: str = name
        self._store: dict[str, TaskDict] = {}
        self._lock: threading.Lock = threading.Lock()
        self._ttl: int = ttl_seconds
        self._last_cleanup: float = time.time()

    def put(self, task_id: str, task: TaskDict) -> None:
        """添加新任务"""
        task["_created_at"] = time.time()
        with self._lock:
            self._store[task_id] = task
            self._maybe_cleanup()

    def get(self, task_id: str) -> Optional[TaskDict]:
        """获取任务（返回副本，排除内部字段）"""
        with self._lock:
            task = self._store.get(task_id)
            if task is None:
                return None
            return {k: v for k, v in task.items() if not k.startswith('_')}

    def update(self, task_id: str, **kwargs: Any) -> None:
        """原子更新任务字段"""
        with self._lock:
            if task_id in self._store:
                self._store[task_id].update(kwargs)

    def get_all(self) -> list[TaskDict]:
        """获取所有任务列表（副本）"""
        with self._lock:
            return [
                {k: v for k, v in t.items() if not k.startswith('_')}
                for t in self._store.values()
            ]

    def get_raw(self, task_id: str) -> Optional[TaskDict]:
        """获取原始引用（用于需要直接操作的场景，如 proc 对象）"""
        with self._lock:
            return self._store.get(task_id)

    def _maybe_cleanup(self) -> None:
        """清理已完成超过 TTL 的任务"""
        now = time.time()
        if now - self._last_cleanup < 60:
            return
        self._last_cleanup = now
        expired = [
            tid for tid, t in self._store.items()
            if t.get("status") in ("done", "error")
            and now - t.get("_created_at", 0) > self._ttl
        ]
        for tid in expired:
            del self._store[tid]
