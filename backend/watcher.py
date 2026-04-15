#!/usr/bin/env python3
"""
文件夹监控 — watchdog 实现

监控 inbox/ 文件夹，有新文件时触发处理管道。
带防抖：文件变化后等 3 秒再触发（等下载完成）。
"""

import threading
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from logger import log
from transcriber import ALL_EXTENSIONS


class _InboxHandler(FileSystemEventHandler):
    """inbox/ 文件变化事件处理器"""

    def __init__(self, callback: Callable[[], None], debounce_sec: float = 3.0):
        self.callback = callback
        self.debounce_sec = debounce_sec
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def on_created(self, event):  # type: ignore[override]
        if event.is_directory:
            return
        # 只关心音视频文件
        suffix = Path(event.src_path).suffix.lower()
        if suffix not in ALL_EXTENSIONS:
            return
        self._debounce()

    def on_moved(self, event):  # type: ignore[override]
        if event.is_directory:
            return
        suffix = Path(event.dest_path).suffix.lower()
        if suffix not in ALL_EXTENSIONS:
            return
        self._debounce()

    def _debounce(self) -> None:
        """防抖：延迟触发回调"""
        with self._lock:
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(self.debounce_sec, self._fire)
            self._timer.start()

    def _fire(self) -> None:
        log("Inbox change detected, triggering processing...")
        try:
            self.callback()
        except Exception as e:
            log(f"Processing error: {e}")


class InboxWatcher:
    """inbox/ 文件夹监控器"""

    def __init__(self, inbox_dir: Path, callback: Callable[[], None]):
        self.inbox_dir = inbox_dir
        self.callback = callback
        self._observer: Observer | None = None

    def start(self) -> None:
        """启动监控（非阻塞）"""
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        handler = _InboxHandler(self.callback)
        self._observer = Observer()
        self._observer.schedule(handler, str(self.inbox_dir), recursive=False)
        self._observer.start()
        log(f"Watching: {self.inbox_dir}")

    def stop(self) -> None:
        """停止监控"""
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
            log("Watcher stopped")
