"""YAML configuration loading utilities.

Per CONFIGURATION.md, every configurable business threshold lives in a YAML
file under `config/`, never hardcoded in source. This module loads and merges
those files into a single dictionary for validation by `PlatformConfig`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]
CONFIG_DIR: Path = PROJECT_ROOT / "config"

_DOMAIN_CONFIG_FILES: tuple[str, ...] = (
    "risk.yaml",
    "telegram.yaml",
    "mt5.yaml",
    "logging.yaml",
    "monitoring.yaml",
    "database.yaml",
    "agents.yaml",
    "ml.yaml",
    "books.yaml",
    "research.yaml",
    "news.yaml",
    "macro.yaml",
)

_ENVIRONMENT_PROFILE_KEY_MAP: dict[str, str] = {
    "risk.yaml": "risk",
    "telegram.yaml": "telegram",
    "mt5.yaml": "mt5",
    "logging.yaml": "logging",
    "monitoring.yaml": "monitoring",
    "database.yaml": "database",
    "agents.yaml": "agents",
    "ml.yaml": "ml",
    "books.yaml": "books",
    "research.yaml": "research",
    "news.yaml": "news",
    "macro.yaml": "macro",
}


def load_yaml_file(path: Path) -> dict[str, Any]:
    """Load a single YAML file into a dictionary.

    Args:
        path: Absolute path to the YAML file.

    Returns:
        The parsed YAML content, or an empty dict if the file is empty.

    Raises:
        FileNotFoundError: If the file does not exist.
        yaml.YAMLError: If the file contains invalid YAML.
    """
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        content: dict[str, Any] | None = yaml.safe_load(handle)
    return content or {}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge `override` into `base`, returning a new dictionary."""
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_platform_config(environment: str) -> dict[str, Any]:
    """Load and merge the environment profile with every domain config file.

    The environment profile (e.g. `config/demo.yaml`) provides global toggles.
    Each domain file (e.g. `config/risk.yaml`) is nested under its own key
    (e.g. `risk`) so that `PlatformConfig` can validate it as a sub-model.

    Args:
        environment: One of "development", "testing", "demo", "production".

    Returns:
        A single merged configuration dictionary.
    """
    environment_file = CONFIG_DIR / f"{environment}.yaml"
    merged: dict[str, Any] = load_yaml_file(environment_file)

    for filename in _DOMAIN_CONFIG_FILES:
        domain_content = load_yaml_file(CONFIG_DIR / filename)
        key = _ENVIRONMENT_PROFILE_KEY_MAP[filename]
        merged = _deep_merge(merged, {key: domain_content})

    return merged
