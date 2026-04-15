"""inputs/plaud.py 单元测试"""

import json
import time
from pathlib import Path

import pytest

from inputs.plaud import (
    ALLOWED_API_BASES,
    check_token_expiry,
    is_safe_download_url,
    load_pulled_db,
    make_filename,
    pull_once,
    save_pulled_db,
)


class TestIsSafeDownloadUrl:
    def test_s3_url(self):
        assert is_safe_download_url(
            "https://bucket.s3.amazonaws.com/file.mp3?sig=abc"
        ) is True

    def test_plaud_url(self):
        assert is_safe_download_url(
            "https://cdn.plaud.ai/recordings/file.mp3"
        ) is True

    def test_http_rejected(self):
        assert is_safe_download_url(
            "http://bucket.s3.amazonaws.com/file.mp3"
        ) is False

    def test_unknown_host_rejected(self):
        assert is_safe_download_url(
            "https://evil.com/file.mp3"
        ) is False


class TestMakeFilename:
    def test_from_filename(self):
        rec = {"filename": "2026-04-11 10:05:55"}
        name = make_filename(rec)
        assert name == "2026-04-11_10-05-55"

    def test_from_start_time_ms(self):
        # 2026-01-01 00:00:00 UTC in ms
        rec = {"filename": "", "start_time": 1767225600000}
        name = make_filename(rec)
        assert name.startswith("2026-")

    def test_fallback(self):
        rec = {}
        name = make_filename(rec)
        assert name.startswith("plaud_")

    def test_special_chars_cleaned(self):
        rec = {"filename": "会议/讨论 (重要)"}
        name = make_filename(rec)
        # 不应包含 / 或 ( )
        assert "/" not in name
        assert "(" not in name

    def test_max_length(self):
        rec = {"filename": "a" * 200}
        name = make_filename(rec)
        assert len(name) <= 100


class TestCheckTokenExpiry:
    def test_valid_token(self):
        import base64
        # 制造一个 1000 天后过期的 JWT
        payload = json.dumps({"exp": time.time() + 86400 * 1000})
        b64 = base64.b64encode(payload.encode()).decode().rstrip("=")
        token = f"header.{b64}.signature"
        days = check_token_expiry(token)
        assert days is not None
        assert days > 900

    def test_expired_token(self):
        import base64
        payload = json.dumps({"exp": time.time() - 86400})
        b64 = base64.b64encode(payload.encode()).decode().rstrip("=")
        token = f"header.{b64}.signature"
        days = check_token_expiry(token)
        assert days is not None
        assert days < 0

    def test_invalid_token(self):
        assert check_token_expiry("not-a-jwt") is None


class TestPulledDb:
    def test_load_nonexistent(self, tmp_path: Path):
        assert load_pulled_db(tmp_path / "nope.json") == {}

    def test_save_and_load(self, tmp_path: Path):
        db_path = tmp_path / "pulled.json"
        data = {"file1": {"filename": "test.mp3"}}
        save_pulled_db(data, db_path)
        loaded = load_pulled_db(db_path)
        assert loaded == data

    def test_corrupted_db_resets(self, tmp_path: Path):
        db_path = tmp_path / "pulled.json"
        db_path.write_text("{invalid json")
        loaded = load_pulled_db(db_path)
        assert loaded == {}
        # 备份应该存在
        assert db_path.with_suffix(".json.bak").exists()


class TestPullOnce:
    def test_no_new_recordings(self, tmp_path: Path, monkeypatch):
        """没有新录音时返回 0"""
        monkeypatch.setattr(
            "inputs.plaud.fetch_recordings", lambda a, t: [],
        )
        count = pull_once(
            "https://api.plaud.ai", "token",
            tmp_path / "inbox", tmp_path / "pulled.json",
        )
        assert count == 0

    def test_skips_already_pulled(self, tmp_path: Path, monkeypatch):
        """已拉取的录音跳过"""
        monkeypatch.setattr(
            "inputs.plaud.fetch_recordings",
            lambda a, t: [{"id": "abc123", "filename": "test", "duration": 60000}],
        )
        # 预置已拉取记录
        pulled_path = tmp_path / "pulled.json"
        pulled_path.write_text(json.dumps({"abc123": {"filename": "test.mp3"}}))

        count = pull_once(
            "https://api.plaud.ai", "token",
            tmp_path / "inbox", pulled_path,
        )
        assert count == 0

    def test_downloads_new_recording(self, tmp_path: Path, monkeypatch):
        """成功下载新录音"""
        monkeypatch.setattr(
            "inputs.plaud.fetch_recordings",
            lambda a, t: [{"id": "new1", "filename": "2026-04-15 09:00:00", "duration": 120000}],
        )
        monkeypatch.setattr(
            "inputs.plaud.download_mp3",
            lambda a, t, fid: b"fake_mp3_data" * 100,
        )

        inbox = tmp_path / "inbox"
        pulled_path = tmp_path / "pulled.json"

        count = pull_once(
            "https://api.plaud.ai", "token", inbox, pulled_path,
        )
        assert count == 1

        # 文件应该存在
        files = list(inbox.glob("*.mp3"))
        assert len(files) == 1

        # .meta sidecar
        meta_path = Path(str(files[0]) + ".meta")
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text())
        assert meta["source"] == "plaud"

        # pulled 数据库应该更新
        pulled = json.loads(pulled_path.read_text())
        assert "new1" in pulled

    def test_fallback_to_raw(self, tmp_path: Path, monkeypatch):
        """MP3 失败时回退到原始格式"""
        monkeypatch.setattr(
            "inputs.plaud.fetch_recordings",
            lambda a, t: [{"id": "new2", "filename": "fallback", "duration": 60000}],
        )
        monkeypatch.setattr("inputs.plaud.download_mp3", lambda a, t, fid: None)
        monkeypatch.setattr(
            "inputs.plaud.download_raw",
            lambda a, t, fid: b"fake_ogg_data" * 100,
        )

        inbox = tmp_path / "inbox"
        count = pull_once(
            "https://api.plaud.ai", "token", inbox, tmp_path / "pulled.json",
        )
        assert count == 1
        assert len(list(inbox.glob("*.ogg"))) == 1


class TestAllowedApiBases:
    def test_contains_expected(self):
        assert "https://api-apse1.plaud.ai" in ALLOWED_API_BASES
        assert "https://api.plaud.ai" in ALLOWED_API_BASES
