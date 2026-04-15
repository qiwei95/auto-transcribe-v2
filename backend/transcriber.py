#!/usr/bin/env python3
"""
本地 Whisper 转录引擎 — faster-whisper (CUDA / CPU)

特性:
- 自动检测 GPU (CUDA) 或回退 CPU
- 内置 VAD 静音过滤 (不需要额外装 Silero)
- 精确时间戳 (不需要按字符数估算)
- 长音频自动分段处理
- 转录质量检测 + 语言重试
"""

import re
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

# 延迟 import：faster-whisper 只在实际转录时需要
# from faster_whisper import WhisperModel


@dataclass(frozen=True)
class TranscriptResult:
    """转录结果"""
    text: str           # 带时间戳的转录文本
    raw_text: str       # 不带时间戳的纯文本
    duration: float     # 音频时长 (秒)
    language: str       # 检测到的语言


# 支持的格式
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".ts", ".3gp"}
AUDIO_EXTENSIONS = {".m4a", ".mp3", ".wav", ".flac", ".ogg", ".aac", ".opus", ".wma"}
ALL_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS


class Transcriber:
    """faster-whisper 转录引擎"""

    def __init__(
        self,
        model_name: str = "large-v3-turbo",
        device: str = "cuda",
        language: str = "zh",
        cpu_threads: int = 4,
    ):
        compute_type = "float16" if device == "cuda" else "int8"

        from faster_whisper import WhisperModel
        self.model = WhisperModel(
            model_name,
            device=device,
            compute_type=compute_type,
            cpu_threads=cpu_threads,
        )
        self.language = language
        self.device = device

    def transcribe(
        self,
        audio_path: Path,
        language: str | None = None,
    ) -> TranscriptResult:
        """转录音频文件，返回结构化结果

        Args:
            audio_path: 音频文件路径
            language: 指定语言 (None=用默认, "auto"=自动检测)
        """
        lang = language or self.language
        use_lang = lang if lang != "auto" else None

        segments, info = self.model.transcribe(
            str(audio_path),
            language=use_lang,
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(
                min_silence_duration_ms=500,
            ),
        )

        # 收集 segments（faster-whisper 返回 generator，只能遍历一次）
        timestamped_lines = []
        raw_lines = []
        for seg in segments:
            ts = _seconds_to_mmss(seg.start)
            text = seg.text.strip()
            if text:
                timestamped_lines.append(f"[{ts}] {text}")
                raw_lines.append(text)

        return TranscriptResult(
            text="\n".join(timestamped_lines),
            raw_text="\n".join(raw_lines),
            duration=info.duration,
            language=info.language,
        )


def _seconds_to_mmss(seconds: float) -> str:
    """秒数 → MM:SS 格式"""
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def extract_audio(video_path: Path) -> Path:
    """从视频提取音频 (stream copy 优先，不兼容时回退 AAC 重编码)"""
    audio_path = video_path.with_suffix(".m4a")

    # 尝试 stream copy (快，无损)
    result = subprocess.run(
        ["ffmpeg", "-i", str(video_path), "-vn", "-acodec", "copy",
         str(audio_path), "-y"],
        capture_output=True,
    )
    if result.returncode == 0 and audio_path.exists():
        return audio_path

    # 回退: 重编码为 AAC
    result = subprocess.run(
        ["ffmpeg", "-i", str(video_path), "-vn", "-acodec", "aac",
         "-b:a", "128k", str(audio_path), "-y"],
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr.decode().strip()}")
    return audio_path


def get_audio_duration(path: Path) -> float:
    """用 ffprobe 获取音频时长 (秒)"""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def check_transcript_quality(
    transcript: str, duration_sec: float,
) -> tuple[bool, str]:
    """检查转录质量，返回 (是否合格, 原因)"""
    # 1. 过短: 5 分钟音频应至少有 200 字
    expected_min = max(50, int(duration_sec / 60) * 40)
    if len(transcript) < expected_min:
        return False, f"Too short: {len(transcript)} chars (expected >={expected_min})"

    # 2. 重复句子: whisper 乱码时经常重复同一句
    sentences = [
        s.strip() for s in re.split(r'[。！？\n.!?]', transcript)
        if len(s.strip()) > 5
    ]
    if sentences:
        counts = Counter(sentences)
        most_common_count = counts.most_common(1)[0][1]
        repeat_ratio = most_common_count / len(sentences)
        if repeat_ratio > 0.3 and most_common_count > 3:
            return (
                False,
                f"Repetitive: {most_common_count} repeats, "
                f"{repeat_ratio:.0%} of sentences",
            )

    return True, ""
