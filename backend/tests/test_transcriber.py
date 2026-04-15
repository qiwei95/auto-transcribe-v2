"""转录引擎辅助函数测试 (不加载模型)"""

import pytest

from transcriber import (
    ALL_EXTENSIONS,
    AUDIO_EXTENSIONS,
    VIDEO_EXTENSIONS,
    _seconds_to_mmss,
    check_transcript_quality,
)


class TestSecondsToMmss:
    def test_zero(self):
        assert _seconds_to_mmss(0) == "00:00"

    def test_seconds_only(self):
        assert _seconds_to_mmss(45) == "00:45"

    def test_minutes_and_seconds(self):
        assert _seconds_to_mmss(125) == "02:05"

    def test_hour_plus(self):
        assert _seconds_to_mmss(3661) == "61:01"

    def test_float_input(self):
        assert _seconds_to_mmss(90.7) == "01:30"


class TestTranscriptQuality:
    def test_good_quality(self):
        # 每句都不同，模拟真实转录
        text = "。".join(f"第{i}个讨论点是关于产品设计方向" for i in range(50))
        ok, reason = check_transcript_quality(text, 300)
        assert ok is True
        assert reason == ""

    def test_too_short(self):
        ok, reason = check_transcript_quality("很短", 300)
        assert ok is False
        assert "Too short" in reason

    def test_repetitive(self):
        text = ("这句话重复了很多次。" * 20) + "另一句话。"
        ok, reason = check_transcript_quality(text, 60)
        assert ok is False
        assert "Repetitive" in reason

    def test_short_audio_lower_threshold(self):
        """短音频的最低字数要求更低"""
        text = "a" * 60
        ok, _ = check_transcript_quality(text, 30)  # 30 秒
        assert ok is True


class TestExtensions:
    def test_audio_extensions(self):
        assert ".m4a" in AUDIO_EXTENSIONS
        assert ".mp3" in AUDIO_EXTENSIONS
        assert ".wav" in AUDIO_EXTENSIONS

    def test_video_extensions(self):
        assert ".mp4" in VIDEO_EXTENSIONS
        assert ".mov" in VIDEO_EXTENSIONS
        assert ".webm" in VIDEO_EXTENSIONS

    def test_all_includes_both(self):
        assert AUDIO_EXTENSIONS.issubset(ALL_EXTENSIONS)
        assert VIDEO_EXTENSIONS.issubset(ALL_EXTENSIONS)
