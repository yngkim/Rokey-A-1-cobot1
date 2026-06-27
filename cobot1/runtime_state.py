"""태스크 간 런타임 상태 저장 (open_bottle → close_bottle 등)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Sequence

_CAP_PLACE_POSE_FILE = "cap_place_pose.json"
_DRAWER_PULLED_JOINT_FILE = "drawer_pulled_joint.json"
_PHONE_LOCATION_FILE = "phone_location.json"
_TRAY_WEIGHT_SESSION_FILE = "tray_weight_session.json"
_TRAY_TARE_FILE = "tray_tare.json"
_TRAY_LOCATION_FILE = "tray_location.json"

PHONE_ON_CHARGER = "on_charger"
PHONE_WITH_USER = "with_user"
_VALID_PHONE_LOCATIONS = {PHONE_ON_CHARGER, PHONE_WITH_USER}

TRAY_ON_STATION = "on_station"
TRAY_WITH_USER = "with_user"
_VALID_TRAY_LOCATIONS = {TRAY_ON_STATION, TRAY_WITH_USER}


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


def get_phone_location() -> str:
    """핸드폰 위치: on_charger(거치대) | with_user(사용자 보유)."""
    path = runtime_state_dir() / _PHONE_LOCATION_FILE
    if not path.is_file():
        return PHONE_ON_CHARGER
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
        location = str(data.get("location", PHONE_ON_CHARGER))
        if location in _VALID_PHONE_LOCATIONS:
            return location
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        pass
    return PHONE_ON_CHARGER


def set_phone_location(location: str) -> None:
    if location not in _VALID_PHONE_LOCATIONS:
        raise ValueError(f"invalid phone location: {location}")
    path = runtime_state_dir() / _PHONE_LOCATION_FILE
    with open(path, "w", encoding="utf-8") as file:
        json.dump({"location": location}, file, indent=2)


def can_pick_from_charger() -> bool:
    return get_phone_location() == PHONE_ON_CHARGER


def can_place_on_charger() -> bool:
    return get_phone_location() == PHONE_WITH_USER


def can_serve_tray() -> bool:
    return get_tray_location() == TRAY_ON_STATION


def can_return_tray() -> bool:
    return get_tray_location() == TRAY_ON_STATION


def _read_json_file(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def _write_json_file(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)


def clear_tray_weight_session() -> None:
    path = runtime_state_dir() / _TRAY_WEIGHT_SESSION_FILE
    if path.is_file():
        path.unlink()


def get_tray_weight_session() -> dict | None:
    path = runtime_state_dir() / _TRAY_WEIGHT_SESSION_FILE
    return _read_json_file(path)


def save_tray_weight_phase(
    phase: str,
    fz_n: float,
    *,
    source: str = "measure_tray_weight",
) -> dict:
    """식전/식후 Fz 저장. after 시 intake_pct 계산."""
    now = time.time()
    if phase == "before":
        data: dict = {
            "before_fz": float(fz_n),
            "source": source,
            "updated_at": now,
        }
    elif phase == "after":
        data = get_tray_weight_session() or {}
        data["after_fz"] = float(fz_n)
        data["updated_at"] = now
        before = data.get("before_fz")
        if before is not None:
            intake = compute_tray_intake_from_session(
                before_fz=float(before),
                after_fz=float(fz_n),
            )
            if intake is not None:
                data["intake_pct"] = intake
    else:
        raise ValueError(f"invalid tray weight phase: {phase}")

    path = runtime_state_dir() / _TRAY_WEIGHT_SESSION_FILE
    _write_json_file(path, data)
    return data


def save_tray_tare(fz_n: float, *, source: str = "calibrate_tray_tare") -> dict:
    """빈 트레이+식판 공차 Fz 영구 저장."""
    data = {
        "tare_fz": float(fz_n),
        "source": source,
        "updated_at": time.time(),
    }
    path = runtime_state_dir() / _TRAY_TARE_FILE
    _write_json_file(path, data)
    return data


def get_tray_tare() -> float | None:
    """저장된 공차 Fz. 없으면 None."""
    path = runtime_state_dir() / _TRAY_TARE_FILE
    data = _read_json_file(path)
    if not data:
        return None
    raw = data.get("tare_fz")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def clear_tray_tare() -> None:
    path = runtime_state_dir() / _TRAY_TARE_FILE
    if path.is_file():
        path.unlink()


def net_food_load(fz_n: float, tare_fz: float) -> float:
    """Fz에서 공차를 뺀 순(음식) 부하."""
    return max(0.0, abs(float(fz_n)) - abs(float(tare_fz)))


def compute_net_intake_pct(
    before_fz: float,
    after_fz: float,
    *,
    tare_fz: float | None = None,
    min_load_n: float = 2.0,
) -> float | None:
    """공차 보정 후 순 음식 무게 기준 섭취율(%)."""
    if tare_fz is None:
        tare_fz = get_tray_tare()
    if tare_fz is None:
        return None

    net_before = net_food_load(before_fz, tare_fz)
    net_after = net_food_load(after_fz, tare_fz)
    if net_before < float(min_load_n):
        return None
    pct = (net_before - net_after) / net_before * 100.0
    return max(0.0, min(100.0, pct))


def compute_tray_intake_from_session(
    *,
    before_fz: float | None = None,
    after_fz: float | None = None,
    min_load_n: float = 2.0,
) -> float | None:
    """저장된 세션 또는 인자로 섭취율(%) 계산."""
    session = get_tray_weight_session() or {}
    if before_fz is None:
        raw = session.get("before_fz")
        before_fz = float(raw) if raw is not None else None
    if after_fz is None:
        raw = session.get("after_fz")
        after_fz = float(raw) if raw is not None else None

    cached = session.get("intake_pct")
    if (
        cached is not None
        and before_fz is None
        and after_fz is None
    ):
        return float(cached)

    if before_fz is None or after_fz is None:
        return None

    return compute_net_intake_pct(
        float(before_fz),
        float(after_fz),
        min_load_n=min_load_n,
    )


def get_tray_location() -> str:
    path = runtime_state_dir() / _TRAY_LOCATION_FILE
    data = _read_json_file(path)
    if not data:
        return TRAY_ON_STATION
    location = str(data.get("location", TRAY_ON_STATION))
    if location in _VALID_TRAY_LOCATIONS:
        return location
    return TRAY_ON_STATION


def set_tray_location(location: str) -> None:
    if location not in _VALID_TRAY_LOCATIONS:
        raise ValueError(f"invalid tray location: {location}")
    path = runtime_state_dir() / _TRAY_LOCATION_FILE
    _write_json_file({"location": location})
