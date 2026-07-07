"""Unit tests for `src.core.config.yaml_loader`."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.core.config.yaml_loader import (
    CONFIG_DIR,
    load_platform_config,
    load_yaml_file,
)

pytestmark = pytest.mark.unit


def test_load_yaml_file_reads_existing_file(tmp_path: Path) -> None:
    config_file = tmp_path / "sample.yaml"
    config_file.write_text("key: value\nnested:\n  inner: 1\n", encoding="utf-8")

    result = load_yaml_file(config_file)

    assert result == {"key": "value", "nested": {"inner": 1}}


def test_load_yaml_file_returns_empty_dict_for_empty_file(tmp_path: Path) -> None:
    config_file = tmp_path / "empty.yaml"
    config_file.write_text("", encoding="utf-8")

    assert load_yaml_file(config_file) == {}


def test_load_yaml_file_raises_for_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_yaml_file(tmp_path / "does_not_exist.yaml")


def test_load_yaml_file_raises_for_invalid_yaml(tmp_path: Path) -> None:
    config_file = tmp_path / "broken.yaml"
    config_file.write_text("key: [unclosed", encoding="utf-8")

    with pytest.raises(yaml.YAMLError):
        load_yaml_file(config_file)


@pytest.mark.parametrize("environment", ["development", "testing", "demo", "production"])
def test_load_platform_config_merges_environment_and_domain_files(environment: str) -> None:
    merged = load_platform_config(environment)

    assert merged["environment"] == environment
    # Domain files are nested under their own key.
    assert "confidence" in merged["risk"]
    assert "postgres" in merged["database"]
    assert "prometheus" in merged["monitoring"]


def test_load_platform_config_unknown_environment_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_platform_config("nonexistent")


def test_config_dir_points_at_real_directory() -> None:
    assert CONFIG_DIR.is_dir()
    assert (CONFIG_DIR / "risk.yaml").is_file()
