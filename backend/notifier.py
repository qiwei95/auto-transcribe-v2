#!/usr/bin/env python3
"""跨平台桌面通知"""

import os
import platform
import subprocess

from logger import log


def notify(title: str, message: str) -> None:
    """发送桌面通知（静默失败，不影响主流程）"""
    try:
        system = platform.system()
        if system == "Darwin":
            _notify_macos(title, message)
        elif system == "Windows":
            _notify_windows(title, message)
        else:
            _notify_linux(title, message)
    except Exception as e:
        log(f"  Notification failed: {e}")


def notify_telegram(
    token: str, chat_id: int, text: str,
) -> None:
    """通过 Telegram API 发送通知（静默失败）"""
    if not token or not chat_id:
        return
    try:
        import httpx
        httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
    except Exception as e:
        log(f"  Telegram notification failed: {e}")


def _notify_macos(title: str, message: str) -> None:
    """macOS 原生通知"""
    script = (
        'on run argv\n'
        '  display notification (item 2 of argv) with title (item 1 of argv)\n'
        'end run'
    )
    subprocess.run(
        ["osascript", "-e", script, title, message],
        capture_output=True,
    )


def _notify_windows(title: str, message: str) -> None:
    """Windows toast 通知"""
    from plyer import notification
    notification.notify(title=title, message=message, timeout=5)


def _notify_linux(title: str, message: str) -> None:
    """Linux 通知 (notify-send)"""
    subprocess.run(
        ["notify-send", title, message],
        capture_output=True,
    )
