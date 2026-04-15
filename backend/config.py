#!/usr/bin/env python3
"""
配置加载模块 — 跨平台 (Windows / macOS / Linux)

搜索顺序:
1. ./config.yaml (项目目录)
2. ~/.config/auto-transcribe/config.yaml (用户目录)
3. 全用默认值
"""

import os
import platform
from dataclasses import dataclass, field
from pathlib import Path

import yaml


def _detect_device() -> str:
    """自动检测最佳转录设备"""
    system = platform.system()

    # macOS: 尝试 MPS (Apple Silicon Metal)
    if system == "Darwin":
        try:
            import torch
            if torch.backends.mps.is_available():
                return "cuda"  # faster-whisper 用 "cuda" 代表 GPU
        except (ImportError, AttributeError):
            pass

    # Windows/Linux: 尝试 CUDA (NVIDIA)
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
    except ImportError:
        pass

    # 无 torch 时用 ctranslate2 检测
    try:
        import ctranslate2
        if "cuda" in ctranslate2.get_supported_compute_types("default"):
            return "cuda"
    except Exception:
        pass

    return "cpu"


def _default_obsidian_output() -> Path:
    return Path.home() / "Documents" / "Obsidian Vault" / "recording-notes"


def _default_captures_output() -> Path:
    return Path.home() / "Documents" / "Obsidian Vault" / "social-captures"


def _default_icloud_inbox() -> Path:
    """macOS iCloud 录音收件箱默认路径"""
    return (
        Path.home() / "Library" / "Mobile Documents"
        / "com~apple~CloudDocs" / "录音收件箱"
    )


@dataclass
class Config:
    # ── 路径 ──
    base_dir: Path = field(
        default_factory=lambda: Path.home() / "auto-transcribe"
    )
    obsidian_output: Path = field(default_factory=_default_obsidian_output)
    captures_output: Path = field(default_factory=_default_captures_output)

    # ── Whisper 转录 ──
    whisper_model: str = "large-v3-turbo"
    whisper_language: str = "zh"
    whisper_device: str = "auto"  # auto / cuda / cpu
    whisper_threads: int = 4     # CPU 线程数限制

    # ── 进程控制 ──
    process_priority: str = "below_normal"  # normal / below_normal / low

    # ── Claude CLI ──
    claude_timeout: int = 1800
    claude_max_retries: int = 3
    max_transcript_chars: int = 80000

    # ── 文件处理 ──
    file_stable_seconds: int = 5

    # ── Telegram Bot (可选) ──
    telegram_bot_token: str = ""
    telegram_allowed_users: list[int] = field(default_factory=list)

    # ── Plaud (可选) ──
    plaud_enabled: bool = False

    # ── iCloud (Mac only, 可选) ──
    icloud_enabled: bool = False
    icloud_inbox: Path = field(default_factory=_default_icloud_inbox)

    # ── 派生路径 (不在 config.yaml 中设置) ──
    @property
    def inbox_dir(self) -> Path:
        return self.base_dir / "inbox"

    @property
    def processing_dir(self) -> Path:
        return self.base_dir / "processing"

    @property
    def done_dir(self) -> Path:
        return self.base_dir / "done"

    @property
    def failed_dir(self) -> Path:
        return self.base_dir / "failed"

    @property
    def transcripts_dir(self) -> Path:
        return self.base_dir / "transcripts"

    @property
    def prompts_dir(self) -> Path:
        return self.base_dir / "prompts"

    @property
    def db_path(self) -> Path:
        return self.base_dir / "auto-transcribe.db"


# 需要从 YAML 字符串展开为 Path 的字段
_PATH_FIELDS = {
    "base_dir", "obsidian_output", "captures_output", "icloud_inbox",
}


def load_config() -> Config:
    """加载配置，找不到文件则用默认值"""
    candidates = [
        Path(__file__).resolve().parent / "config.yaml",
        Path.cwd() / "config.yaml",
        Path.home() / ".config" / "auto-transcribe" / "config.yaml",
    ]

    raw: dict = {}
    for path in candidates:
        if path.exists():
            raw = yaml.safe_load(path.read_text()) or {}
            break

    if not raw:
        cfg = Config()
    else:
        kwargs = {}
        for key, value in raw.items():
            if key in _PATH_FIELDS and isinstance(value, str):
                kwargs[key] = Path(value).expanduser()
            else:
                kwargs[key] = value
        cfg = Config(**kwargs)

    # 环境变量覆盖
    if not cfg.telegram_bot_token:
        cfg.telegram_bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")

    # 自动检测设备
    if cfg.whisper_device == "auto":
        cfg.whisper_device = _detect_device()

    return cfg
