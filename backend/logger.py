#!/usr/bin/env python3
"""简单日志工具"""

import sys
from datetime import datetime

# 强制行缓冲（后台运行时确保日志实时输出）
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)


def log(msg: str) -> None:
    """打印带时间戳的日志"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")
