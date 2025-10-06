from __future__ import annotations
import threading, time, traceback, random
from typing import Callable, Dict, List

class ScheduledTask:
    def __init__(self, name: str, interval: int, func: Callable, jitter: float = 0.1):
        self.name = name
        self.interval = interval
        self.func = func
        self.jitter = jitter
        self.last_run: float = 0.0
        self.failures: int = 0
        self.thread: threading.Thread | None = None
        self.running = False

    def _loop(self):
        self.running = True
        while self.running:
            start = time.time()
            try:
                self.func()
                self.failures = 0
            except Exception:
                self.failures += 1
                traceback.print_exc()
            self.last_run = time.time()
            base_sleep = self.interval
            if self.jitter > 0:
                base_sleep *= (1 + random.uniform(-self.jitter, self.jitter))
            time.sleep(max(1, base_sleep))

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._loop, name=f"Task-{self.name}", daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False

_tasks: Dict[str, ScheduledTask] = {}


def register_task(name: str, interval: int, func: Callable, jitter: float = 0.1):
    if name in _tasks:
        return _tasks[name]
    task = ScheduledTask(name, interval, func, jitter=jitter)
    _tasks[name] = task
    return task


def start_all():
    for t in _tasks.values():
        t.start()


def stop_all():
    for t in _tasks.values():
        t.stop()


def list_tasks():
    return {name: {"interval": t.interval, "last_run": t.last_run, "failures": t.failures} for name, t in _tasks.items()}
