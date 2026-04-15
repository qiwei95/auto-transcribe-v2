"""inputs/telegram.py 单元测试"""

import json
from pathlib import Path

import pytest

from inputs.telegram import (
    URL_PATTERN,
    classify_url,
    clean_url,
    detect_ad_url,
    is_safe_url,
    sanitize_filename,
    write_capture,
    write_meta_sidecar,
)


class TestSanitizeFilename:
    def test_normal_text(self):
        assert sanitize_filename("Hello World") == "hello-world"

    def test_chinese(self):
        result = sanitize_filename("会议记录讨论")
        assert "会议记录讨论" in result

    def test_special_chars(self):
        result = sanitize_filename("test@#$%file")
        assert "@" not in result
        assert "#" not in result

    def test_max_length(self):
        result = sanitize_filename("a" * 100)
        assert len(result) <= 50

    def test_empty(self):
        assert sanitize_filename("") == "untitled"
        assert sanitize_filename("@#$") == "untitled"


class TestCleanUrl:
    def test_removes_utm(self):
        url = "https://example.com/page?utm_source=twitter&utm_medium=social&id=123"
        cleaned = clean_url(url)
        assert "utm_source" not in cleaned
        assert "utm_medium" not in cleaned
        assert "id=123" in cleaned

    def test_removes_fbclid(self):
        url = "https://example.com/?fbclid=abc123"
        cleaned = clean_url(url)
        assert "fbclid" not in cleaned

    def test_preserves_non_tracking(self):
        url = "https://example.com/page?v=abc&list=xyz"
        cleaned = clean_url(url)
        assert "v=abc" in cleaned
        assert "list=xyz" in cleaned

    def test_no_params(self):
        url = "https://example.com/page"
        assert clean_url(url) == url


class TestClassifyUrl:
    def test_youtube(self):
        assert classify_url("https://www.youtube.com/watch?v=abc") == ("youtube", "audio")
        assert classify_url("https://youtu.be/abc") == ("youtube", "audio")

    def test_bilibili(self):
        assert classify_url("https://www.bilibili.com/video/BV123")[0] == "bilibili"

    def test_tiktok(self):
        assert classify_url("https://www.tiktok.com/@user/video/123") == ("tiktok", "audio")

    def test_douyin_video(self):
        assert classify_url("https://www.douyin.com/video/123") == ("douyin", "audio")

    def test_douyin_note(self):
        assert classify_url("https://www.douyin.com/note/123") == ("douyin", "text")

    def test_instagram_reel(self):
        assert classify_url("https://www.instagram.com/reel/abc") == ("instagram", "audio")

    def test_instagram_post(self):
        assert classify_url("https://www.instagram.com/p/abc") == ("instagram", "text")

    def test_threads(self):
        assert classify_url("https://www.threads.net/@user/post/abc") == ("threads", "text")

    def test_xiaohongshu(self):
        assert classify_url("https://www.xiaohongshu.com/explore/abc")[0] == "xiaohongshu"

    def test_twitter(self):
        assert classify_url("https://x.com/user/status/123") == ("twitter", "audio")
        assert classify_url("https://twitter.com/user/status/123") == ("twitter", "audio")

    def test_facebook_video(self):
        assert classify_url("https://www.facebook.com/watch?v=123") == ("facebook", "audio")
        assert classify_url("https://www.facebook.com/reel/123") == ("facebook", "audio")

    def test_facebook_post(self):
        assert classify_url("https://www.facebook.com/user/posts/123") == ("facebook", "text")

    def test_generic(self):
        assert classify_url("https://blog.example.com/article") == ("generic", "text")


class TestIsSafeUrl:
    def test_https_allowed(self):
        safe, _ = is_safe_url("https://example.com")
        assert safe is True

    def test_http_allowed(self):
        safe, _ = is_safe_url("http://example.com")
        assert safe is True

    def test_ftp_blocked(self):
        safe, _ = is_safe_url("ftp://example.com")
        assert safe is False

    def test_localhost_blocked(self):
        safe, _ = is_safe_url("http://127.0.0.1/admin")
        assert safe is False

    def test_private_ip_blocked(self):
        safe, _ = is_safe_url("http://192.168.1.1/config")
        assert safe is False

    def test_no_hostname(self):
        safe, _ = is_safe_url("https://")
        assert safe is False


class TestDetectAdUrl:
    def test_ad_params(self):
        assert detect_ad_url("https://example.com?ad_id=123") is True
        assert detect_ad_url("https://example.com?campaign_id=abc") is True

    def test_paid_utm(self):
        assert detect_ad_url("https://example.com?utm_medium=cpc") is True
        assert detect_ad_url("https://example.com?utm_medium=paid") is True

    def test_organic(self):
        assert detect_ad_url("https://example.com?utm_medium=social") is False
        assert detect_ad_url("https://example.com?v=abc") is False


class TestUrlPattern:
    def test_finds_urls(self):
        text = "check this https://example.com and http://test.org/page"
        urls = URL_PATTERN.findall(text)
        assert len(urls) == 2

    def test_no_urls(self):
        assert URL_PATTERN.findall("no urls here") == []

    def test_ignores_schemes(self):
        assert URL_PATTERN.findall("file:///etc/passwd") == []
        assert URL_PATTERN.findall("javascript:alert(1)") == []


class TestWriteMetaSidecar:
    def test_basic(self, tmp_path: Path):
        audio = tmp_path / "test.mp3"
        audio.write_bytes(b"audio")
        write_meta_sidecar(audio, "https://example.com", "youtube", "zh")
        meta_path = Path(str(audio) + ".meta")
        assert meta_path.exists()
        data = json.loads(meta_path.read_text())
        assert data["url"] == "https://example.com"
        assert data["platform"] == "youtube"
        assert data["language"] == "zh"

    def test_with_ad_and_chat(self, tmp_path: Path):
        audio = tmp_path / "ad.mp3"
        audio.write_bytes(b"audio")
        write_meta_sidecar(audio, "https://x.com/t", "twitter", "en", chat_id=123, is_ad=True)
        data = json.loads(Path(str(audio) + ".meta").read_text())
        assert data["is_ad"] is True
        assert data["chat_id"] == 123


class TestWriteCapture:
    def test_creates_note(self, tmp_path: Path):
        captures = tmp_path / "captures"
        metadata = {
            "title": "Test Post",
            "platform": "threads",
            "url": "https://threads.net/post",
            "author": "testuser",
        }
        path = write_capture("Post content here", metadata, captures)
        assert path.exists()
        content = path.read_text()
        assert "platform: threads" in content
        assert "Post content here" in content
        assert "author: testuser" in content

    def test_dedup_filename(self, tmp_path: Path):
        """同名文件自动加编号"""
        captures = tmp_path / "captures"
        metadata = {"title": "Same Title", "platform": "twitter", "url": "", "author": ""}

        path1 = write_capture("content 1", metadata, captures)
        path2 = write_capture("content 2", metadata, captures)
        assert path1 != path2
        assert path1.exists()
        assert path2.exists()
