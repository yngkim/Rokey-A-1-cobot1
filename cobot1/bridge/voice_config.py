"""음성 명령 YAML 로드."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from ament_index_python.packages import get_package_share_directory

DEFAULT_VOICE_REL = "config/voice_commands.yaml"


def default_voice_config_path() -> str:
    share = get_package_share_directory("cobot1")
    return os.path.join(share, DEFAULT_VOICE_REL)


def _dev_voice_config_path() -> Path | None:
    source = Path(__file__).resolve().parents[2] / "config" / "voice_commands.yaml"
    return source if source.is_file() else None


def load_voice_config(config_path: str | None = None) -> dict[str, Any]:
    if config_path:
        path = Path(config_path)
    else:
        env = os.environ.get("COBOT1_VOICE_CONFIG")
        if env:
            path = Path(env)
        else:
            dev = _dev_voice_config_path()
            if dev is not None:
                path = dev
            else:
                path = Path(default_voice_config_path())

    if not path.is_file():
        raise FileNotFoundError(f"음성 명령 설정 파일을 찾을 수 없습니다: {path}")

    with open(path, "r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}
