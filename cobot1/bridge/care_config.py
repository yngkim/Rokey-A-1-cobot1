"""케어 모니터링 설정 로드."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from ament_index_python.packages import get_package_share_directory


def _care_yaml_path() -> Path:
    share = get_package_share_directory("cobot1")
    return Path(share) / "config" / "care.yaml"


@lru_cache(maxsize=1)
def load_care_config() -> dict[str, Any]:
    path = _care_yaml_path()
    if not path.is_file():
        return {
            "default_users": [{"id": "patient_01", "name": "기본 사용자"}],
            "daily_targets": {
                "medication_prepare": 3,
                "medication_taken": 3,
                "meals": 3,
            },
        }
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not data.get("default_users"):
        data["default_users"] = [{"id": "patient_01", "name": "기본 사용자"}]
    targets = data.setdefault("daily_targets", {})
    targets.setdefault("medication_prepare", 3)
    targets.setdefault("medication_taken", 3)
    targets.setdefault("meals", 3)
    return data
