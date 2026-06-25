"""TCP 포즈 보조."""

from __future__ import annotations

from typing import Sequence


def offset_pose_z(pose: Sequence[float], dz_mm: float) -> list[float]:
    """베이스 Z만 dz_mm 만큼 이동한 TCP 포즈 반환."""
    p = [float(v) for v in pose[:6]]
    p[2] += float(dz_mm)
    return p
