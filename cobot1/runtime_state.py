"""태스크 간 런타임 상태 저장 (open_bottle → close_bottle 등)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Sequence

_CAP_PLACE_POSE_FILE = "cap_place_pose.json"
_DRAWER_PULLED_JOINT_FILE = "drawer_pulled_joint.json"


def runtime_state_dir() -> Path:
    base = os.environ.get("COBOT1_RUNTIME_DIR")
    if base:
        path = Path(base)
    else:
        path = Path.home() / ".cobot1"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_cap_place_pose(pose: Sequence[float]) -> None:
    """open_bottle 이 바닥에 뚜껑을 내려놓은 직후 TCP 포즈 저장."""
    data = {
        "tcp_pose": [float(v) for v in pose[:6]],
        "source": "open_bottle",
    }
    path = runtime_state_dir() / _CAP_PLACE_POSE_FILE
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)


def load_cap_place_pose() -> list[float] | None:
    """저장된 뚜껑 안착 TCP 포즈. 없으면 None."""
    path = runtime_state_dir() / _CAP_PLACE_POSE_FILE
    if not path.is_file():
        return None
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
        pose = data.get("tcp_pose")
        if not isinstance(pose, list) or len(pose) < 6:
            return None
        return [float(v) for v in pose[:6]]
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def save_drawer_pulled_joint(joints: Sequence[float]) -> None:
    """서랍 X축 당김 직후 실제 조인트 각도 저장."""
    data = {
        "joint": [float(v) for v in joints[:6]],
        "source": "pick_place_pill",
    }
    path = runtime_state_dir() / _DRAWER_PULLED_JOINT_FILE
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)


def load_drawer_pulled_joint() -> list[float] | None:
    """저장된 서랍 당김 조인트. 없으면 None."""
    path = runtime_state_dir() / _DRAWER_PULLED_JOINT_FILE
    if not path.is_file():
        return None
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
        joint = data.get("joint")
        if not isinstance(joint, list) or len(joint) < 6:
            return None
        return [float(v) for v in joint[:6]]
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None
