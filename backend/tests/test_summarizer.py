"""Summarizer 解析逻辑测试 (不调用 Claude CLI)"""

import pytest

from summarizer import (
    VALID_SCENES,
    _parse_output,
    select_prompt,
)


class TestSelectPrompt:
    def test_ad_always_returns_ad(self):
        assert select_prompt("youtube", 60, is_ad=True) == "ad"
        assert select_prompt("tiktok", 600, is_ad=True) == "ad"

    def test_short_video(self):
        assert select_prompt("youtube", 120, is_ad=False) == "video-short"
        assert select_prompt("tiktok", 299, is_ad=False) == "video-short"

    def test_long_video(self):
        assert select_prompt("youtube", 300, is_ad=False) == "video-long"
        assert select_prompt("youtube", 3600, is_ad=False) == "video-long"


class TestParseOutput:
    def test_parse_scene_and_title(self):
        output = (
            "===SCENE=== meeting\n"
            "===TITLE=== 周一团队例会纪要\n"
            "# 会议纪要\n"
            "## 讨论点\n"
            "- 产品进度"
        )
        result = _parse_output(output, "memo", need_classify=True)
        assert result.scene == "meeting"
        assert result.title == "周一团队例会纪要"
        assert "# 会议纪要" in result.summary

    def test_parse_without_scene(self):
        output = (
            "===TITLE=== 产品想法备忘\n"
            "一些想法..."
        )
        result = _parse_output(output, "memo", need_classify=False)
        assert result.scene == "memo"
        assert result.title == "产品想法备忘"

    def test_title_cleaning(self):
        """标题清洗：去掉引号、冒号"""
        output = '===TITLE=== 「关于：用户留存」的思考\n内容...'
        result = _parse_output(output, "memo", need_classify=False)
        assert "「" not in result.title
        assert "」" not in result.title
        assert "：" not in result.title

    def test_title_max_length(self):
        """标题最多 50 字"""
        long_title = "这是一个非常非常非常长的标题" * 10
        output = f"===TITLE=== {long_title}\n内容..."
        result = _parse_output(output, "memo", need_classify=False)
        assert len(result.title) <= 50

    def test_skip_meta_lines(self):
        """跳过 ===META=== 等标记行"""
        output = (
            "===TITLE=== 测试\n"
            "===META===\n"
            "content_type: meeting\n"
            "intent: summarize\n"
            "===SUMMARY===\n"
            "这是正文"
        )
        result = _parse_output(output, "memo", need_classify=False)
        assert "content_type" not in result.summary
        assert "这是正文" in result.summary

    def test_empty_output(self):
        result = _parse_output("", "memo", need_classify=False)
        assert result.scene == "memo"
        assert result.title == ""
        assert result.summary == ""

    def test_all_scenes_valid(self):
        for scene in VALID_SCENES:
            output = f"===SCENE=== {scene}\n===TITLE=== test\ncontent"
            result = _parse_output(output, "memo", need_classify=True)
            assert result.scene == scene
