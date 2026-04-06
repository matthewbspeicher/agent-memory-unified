"""Tests for centralized YAML config loading."""

import yaml
from utils.config_loader import ConfigLoader


class TestConfigLoader:
    def test_resolve_finds_file(self, tmp_path):
        f = tmp_path / "test.yaml"
        f.write_text("key: value")
        loader = ConfigLoader(app_root=tmp_path, docker_root=tmp_path)
        assert loader.resolve("test.yaml") == str(f)

    def test_resolve_returns_none_for_missing(self, tmp_path):
        loader = ConfigLoader(app_root=tmp_path, docker_root=tmp_path)
        assert loader.resolve("nonexistent.yaml") is None

    def test_load_yaml_caches(self, tmp_path):
        f = tmp_path / "test.yaml"
        f.write_text(yaml.dump({"agents": [{"name": "rsi"}]}))
        loader = ConfigLoader(app_root=tmp_path, docker_root=tmp_path)
        result1 = loader.load_yaml("test.yaml")
        result2 = loader.load_yaml("test.yaml")
        assert result1 is result2  # same object = cached
        assert result1 == {"agents": [{"name": "rsi"}]}
