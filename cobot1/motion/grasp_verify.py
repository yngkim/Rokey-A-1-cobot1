"""그리퍼 파지 후 물체 유무 검사 (RG2 gwdf 너비 기준)."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from ament_index_python.packages import get_package_share_directory

from cobot1.motion.exceptions import ObjectMissingError

if TYPE_CHECKING:
    from cobot1.motion.gripper import (
        DRIVER_ONROBOT_ROS,
        Gripper,
    )
else:
    DRIVER_ONROBOT_ROS = "onrobot_ros"

DEFAULT_GRASP_OBJECTS_REL = "config/grasp_objects.yaml"
_cached_config: dict[str, Any] | None = None


def default_grasp_objects_path() -> str:
    share = get_package_share_directory("cobot1")
    return os.path.join(share, DEFAULT_GRASP_OBJECTS_REL)


def _dev_grasp_objects_path() -> Path | None:
    source = Path(__file__).resolve().parents[2] / "config" / "grasp_objects.yaml"
    return source if source.is_file() else None


def load_grasp_objects(config_path: str | None = None) -> dict[str, Any]:
    global _cached_config
    if config_path is None and _cached_config is not None:
        return _cached_config

    if config_path:
        path = Path(config_path)
    else:
        env = os.environ.get("COBOT1_GRASP_OBJECTS")
        if env:
            path = Path(env)
        else:
            dev = _dev_grasp_objects_path()
            path = dev if dev is not None else Path(default_grasp_objects_path())

    if not path.is_file():
        raise FileNotFoundError(f"그리퍼 검사 설정 파일을 찾을 수 없습니다: {path}")

    with open(path, "r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    if config_path is None:
        _cached_config = data
    return data


DEFAULT_OBJECT_MISSING_SPEECH = "대상 물건이 없습니다. 다시 확인해 주세요."


def user_feedback_message(cfg: dict[str, Any] | None = None) -> str:
    data = cfg or load_grasp_objects()
    verify_cfg = data.get("grasp_verify", {})
    return str(verify_cfg.get("speech", DEFAULT_OBJECT_MISSING_SPEECH))


def _object_entry(data: dict[str, Any], object_id: str) -> dict[str, str]:
    objects = data.get("objects", {})
    entry = objects.get(object_id)
    if not isinstance(entry, dict):
        label = object_id.replace("_", " ")
        return {"label": label}
    label = str(entry.get("label", object_id))
    return {"label": label}


def should_skip_verify(gripper: Gripper, cfg: dict[str, Any] | None = None) -> bool:
    data = cfg or load_grasp_objects()
    verify_cfg = data.get("grasp_verify", {})
    if not verify_cfg.get("enabled", True):
        return True
    if gripper.is_simulated:
        return True
    if gripper.driver == DRIVER_ONROBOT_ROS:
        return True
    return False


def verify_object_grasped(
    gripper: Gripper,
    object_id: str,
    *,
    cfg: dict[str, Any] | None = None,
) -> None:
    """닫힘 직후 호출. 너비 <= max_empty_width_mm 이면 ObjectMissingError."""
    data = cfg or load_grasp_objects()
    entry = _object_entry(data, object_id)
    verify_cfg = data.get("grasp_verify", {})
    max_empty_mm = float(verify_cfg.get("max_empty_width_mm", 11.0))

    time.sleep(0.15)
    width_mm = gripper.read_width_mm()
    if width_mm is not None:
        gripper._log(
            f"[grasp_verify] {object_id}({entry['label']}): "
            f"그리퍼 닫힘 후 gwdf={width_mm:.1f}mm (빈 그리퍼 임계 ≤{max_empty_mm:.1f}mm)"
        )
    elif should_skip_verify(gripper, data):
        gripper._log(
            f"[grasp_verify] {object_id}: 너비 읽기 불가 — 검사 스킵 (driver={gripper.driver})"
        )
        return

    if should_skip_verify(gripper, data):
        if width_mm is not None:
            gripper._log(
                f"[grasp_verify] {object_id}: 검사 스킵 (driver={gripper.driver})"
            )
        return

    if width_mm is None:
        return

    if width_mm <= max_empty_mm:
        gripper._log(
            f"[grasp_verify] {object_id}: 물체 없음 — "
            f"gwdf={width_mm:.1f}mm ≤ {max_empty_mm:.1f}mm, 작업 중지"
        )
        speech = user_feedback_message(data)
        raise ObjectMissingError(
            object_id,
            user_message=speech,
            speech_text=speech,
            object_label=entry["label"],
            width_mm=width_mm,
        )

    gripper._log(
        f"[grasp_verify] {object_id}({entry['label']}): 파지 확인 OK "
        f"(gwdf={width_mm:.1f}mm)"
    )
