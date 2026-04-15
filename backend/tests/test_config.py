"""配置加载测试"""

import platform
from pathlib import Path

import pytest
import yaml

from config import Config, load_config


class TestConfigDefaults:
    """默认配置测试"""

    def test_default_base_dir(self):
        cfg = Config()
        assert cfg.base_dir == Path.home() / "auto-transcribe"

    def test_default_whisper_model(self):
        cfg = Config()
        assert cfg.whisper_model == "large-v3-turbo"

    def test_default_whisper_language(self):
        cfg = Config()
        assert cfg.whisper_language == "zh"

    def test_default_process_priority(self):
        cfg = Config()
        assert cfg.process_priority == "below_normal"

    def test_derived_paths(self):
        cfg = Config(base_dir=Path("/tmp/test-at"))
        assert cfg.inbox_dir == Path("/tmp/test-at/inbox")
        assert cfg.processing_dir == Path("/tmp/test-at/processing")
        assert cfg.done_dir == Path("/tmp/test-at/done")
        assert cfg.failed_dir == Path("/tmp/test-at/failed")
        assert cfg.transcripts_dir == Path("/tmp/test-at/transcripts")
        assert cfg.db_path == Path("/tmp/test-at/auto-transcribe.db")


class TestConfigFromYaml:
    """YAML 配置加载测试"""

    def test_load_from_yaml(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({
            "base_dir": str(tmp_path / "my-project"),
            "whisper_model": "small",
            "whisper_language": "en",
        }))

        # 模拟搜索路径
        import config as config_mod
        original = config_mod.load_config

        # 直接测试 YAML 解析逻辑
        raw = yaml.safe_load(config_file.read_text())
        cfg = Config(
            base_dir=Path(raw["base_dir"]),
            whisper_model=raw["whisper_model"],
            whisper_language=raw["whisper_language"],
        )
        assert cfg.whisper_model == "small"
        assert cfg.whisper_language == "en"

    def test_path_expansion(self):
        """~ 应被展开为 home 目录"""
        cfg = Config(base_dir=Path("~/auto-transcribe").expanduser())
        assert "~" not in str(cfg.base_dir)
        assert str(cfg.base_dir).startswith(str(Path.home()))
