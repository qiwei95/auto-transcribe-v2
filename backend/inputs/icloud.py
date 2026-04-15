#!/usr/bin/env python3
"""
iCloud 录音收件箱同步 (Mac only)

轮询 iCloud Drive 录音收件箱 → 复制到本地 inbox/
由后台线程定时执行，非 Mac 系统自动跳过。
"""

import json
import platform
import shutil
import subprocess
import threading
import time
from pathlib import Path

from logger import log
from transcriber import ALL_EXTENSIONS

# iCloud 占位符后缀
_ICLOUD_SUFFIX = ".icloud"


def is_mac() -> bool:
    return platform.system() == "Darwin"


def is_icloud_placeholder(path: Path) -> bool:
    """检查是否是 iCloud 占位符（未下载的文件）"""
    return path.name.startswith(".") and path.name.endswith(_ICLOUD_SUFFIX)


def trigger_icloud_download(path: Path) -> None:
    """用 brctl 触发 iCloud 文件下载"""
    subprocess.run(
        ["brctl", "download", str(path)],
        capture_output=True, timeout=10,
    )


def wait_for_download(
    path: Path, stable_seconds: int = 5, max_wait: int = 120,
) -> bool:
    """等待 iCloud 文件下载完成（文件大小稳定 N 秒）"""
    prev_size = -1
    stable_count = 0
    for _ in range(max_wait):
        if not path.exists():
            return False
        size = path.stat().st_size
        if size == prev_size and size > 0:
            stable_count += 1
            if stable_count >= stable_seconds:
                return True
        else:
            stable_count = 0
        prev_size = size
        time.sleep(1)
    return False


def sync_once(
    icloud_inbox: Path,
    local_inbox: Path,
    stable_seconds: int = 5,
) -> int:
    """扫描一次 iCloud 收件箱，返回同步的文件数"""
    if not icloud_inbox.exists():
        return 0

    local_inbox.mkdir(parents=True, exist_ok=True)
    count = 0

    for f in sorted(icloud_inbox.iterdir()):
        # 跳过隐藏文件和占位符
        if f.name.startswith("."):
            if is_icloud_placeholder(f):
                log(f"  [icloud] Skip (not downloaded): {f.name}")
            continue

        if f.suffix.lower() not in ALL_EXTENSIONS:
            continue

        # 跳过已存在的文件
        dest = local_inbox / f.name
        if dest.exists():
            continue

        # 触发 iCloud 下载
        log(f"  [icloud] Downloading: {f.name}")
        trigger_icloud_download(f)

        if not wait_for_download(f, stable_seconds):
            log(f"  [icloud] Download timeout: {f.name}")
            continue

        # 复制到 inbox，验证大小一致
        shutil.copy2(str(f), str(dest))
        if dest.stat().st_size == 0 or dest.stat().st_size != f.stat().st_size:
            log(f"  [icloud] Copy size mismatch, removing: {f.name}")
            dest.unlink()
            continue

        # 写 .meta sidecar
        meta = {"platform": "", "language": "", "source": "icloud"}
        meta_path = Path(str(dest) + ".meta")
        meta_path.write_text(json.dumps(meta))

        log(f"  [icloud] Synced: {f.name} ({f.stat().st_size} bytes)")
        count += 1

    return count


class ICloudSync:
    """iCloud 录音收件箱后台同步"""

    def __init__(
        self,
        icloud_inbox: Path,
        local_inbox: Path,
        interval_sec: int = 60,
        stable_seconds: int = 5,
    ):
        self.icloud_inbox = icloud_inbox
        self.local_inbox = local_inbox
        self.interval_sec = interval_sec
        self.stable_seconds = stable_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """启动后台同步线程"""
        if not is_mac():
            log("[icloud] Not macOS, skipping iCloud sync")
            return

        if not self.icloud_inbox.exists():
            log(f"[icloud] Inbox not found: {self.icloud_inbox}")
            log("[icloud] Skipping — create the folder to enable sync")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="icloud-sync",
        )
        self._thread.start()
        log(f"[icloud] Started (every {self.interval_sec}s): {self.icloud_inbox}")

    def stop(self) -> None:
        """停止后台同步"""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)
            self._thread = None
            log("[icloud] Stopped")

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                n = sync_once(
                    self.icloud_inbox,
                    self.local_inbox,
                    self.stable_seconds,
                )
                if n > 0:
                    log(f"[icloud] Synced {n} file(s)")
            except Exception as e:
                log(f"[icloud] Error: {e}")

            self._stop_event.wait(self.interval_sec)
