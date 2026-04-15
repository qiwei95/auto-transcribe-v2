"""inputs/icloud.py 单元测试"""

import json
from pathlib import Path

import pytest

from inputs.icloud import (
    is_icloud_placeholder,
    is_mac,
    sync_once,
)


class TestIsIcloudPlaceholder:
    def test_normal_file(self):
        assert is_icloud_placeholder(Path("recording.m4a")) is False

    def test_placeholder_file(self):
        assert is_icloud_placeholder(Path(".recording.m4a.icloud")) is True

    def test_hidden_non_icloud(self):
        assert is_icloud_placeholder(Path(".gitignore")) is False

    def test_dot_icloud_not_hidden(self):
        # 不以 . 开头的不算占位符
        assert is_icloud_placeholder(Path("file.icloud")) is False


class TestSyncOnce:
    def test_nonexistent_icloud_dir(self, tmp_path: Path):
        """iCloud 目录不存在时返回 0"""
        fake_icloud = tmp_path / "nonexistent"
        local_inbox = tmp_path / "inbox"
        assert sync_once(fake_icloud, local_inbox) == 0

    def test_empty_icloud_dir(self, tmp_path: Path):
        """iCloud 目录为空时返回 0"""
        icloud = tmp_path / "icloud"
        icloud.mkdir()
        local_inbox = tmp_path / "inbox"
        assert sync_once(icloud, local_inbox) == 0

    def test_skips_non_audio_files(self, tmp_path: Path):
        """跳过非音视频文件"""
        icloud = tmp_path / "icloud"
        icloud.mkdir()
        (icloud / "notes.txt").write_text("hello")
        (icloud / "photo.jpg").write_bytes(b"\xff\xd8" * 100)

        local_inbox = tmp_path / "inbox"
        assert sync_once(icloud, local_inbox) == 0

    def test_skips_hidden_files(self, tmp_path: Path):
        """跳过隐藏文件"""
        icloud = tmp_path / "icloud"
        icloud.mkdir()
        (icloud / ".DS_Store").write_bytes(b"x" * 100)

        local_inbox = tmp_path / "inbox"
        assert sync_once(icloud, local_inbox) == 0

    def test_skips_existing_files(self, tmp_path: Path):
        """已存在于 inbox 的文件跳过"""
        icloud = tmp_path / "icloud"
        icloud.mkdir()
        (icloud / "meeting.m4a").write_bytes(b"audio" * 100)

        local_inbox = tmp_path / "inbox"
        local_inbox.mkdir()
        (local_inbox / "meeting.m4a").write_bytes(b"existing")

        assert sync_once(icloud, local_inbox) == 0

    def test_syncs_audio_file(self, tmp_path: Path, monkeypatch):
        """正常同步音频文件到 inbox"""
        icloud = tmp_path / "icloud"
        icloud.mkdir()
        audio_data = b"fake_audio_data" * 50
        (icloud / "meeting.m4a").write_bytes(audio_data)

        local_inbox = tmp_path / "inbox"

        # Mock brctl 和 wait_for_download
        monkeypatch.setattr(
            "inputs.icloud.trigger_icloud_download", lambda p: None,
        )
        monkeypatch.setattr(
            "inputs.icloud.wait_for_download", lambda p, s=5: True,
        )

        count = sync_once(icloud, local_inbox, stable_seconds=1)
        assert count == 1
        assert (local_inbox / "meeting.m4a").exists()
        assert (local_inbox / "meeting.m4a").read_bytes() == audio_data
        # .meta sidecar 也应该存在
        meta_path = local_inbox / "meeting.m4a.meta"
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text())
        assert meta["source"] == "icloud"

    def test_skips_on_download_timeout(self, tmp_path: Path, monkeypatch):
        """下载超时时跳过"""
        icloud = tmp_path / "icloud"
        icloud.mkdir()
        (icloud / "big.m4a").write_bytes(b"x" * 100)

        local_inbox = tmp_path / "inbox"

        monkeypatch.setattr(
            "inputs.icloud.trigger_icloud_download", lambda p: None,
        )
        monkeypatch.setattr(
            "inputs.icloud.wait_for_download", lambda p, s=5: False,
        )

        assert sync_once(icloud, local_inbox) == 0
        assert not (local_inbox / "big.m4a").exists()
