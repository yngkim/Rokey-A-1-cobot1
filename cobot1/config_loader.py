"""시나리오 YAML 로드 및 런타임 오버라이드."""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import yaml
from ament_index_python.packages import get_package_share_directory


DEFAULT_CONFIG_REL = "config/scenarios.yaml"


def default_config_path() -> str:
    share = get_package_share_directory("cobot1")
    return os.path.join(share, DEFAULT_CONFIG_REL)


def _deep_merge(base: dict, override: dict) -> dict:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_scenarios(
    config_path: str | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    path = config_path or os.environ.get("COBOT1_CONFIG", default_config_path())
    if not Path(path).is_file():
        raise FileNotFoundError(f"시나리오 설정 파일을 찾을 수 없습니다: {path}")

    with open(path, "r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    if overrides:
        data = _deep_merge(data, overrides)
    return data
