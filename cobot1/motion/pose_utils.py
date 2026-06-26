"""TCP 포즈 보조."""

from __future__ import annotations

from typing import Sequence


def offset_pose_z(pose: Sequence[float], dz_mm: float) -> list[float]:
    """베이스 Z만 dz_mm 만큼 이동한 TCP 포즈 반환."""
    p = [float(v) for v in pose[:6]]
    p[2] += float(dz_mm)
    return p


def offset_joint_tcp_translation(
    joints: Sequence[float],
    *,
    dx_mm: float = 0.0,
    dy_mm: float = 0.0,
    dz_mm: float = 0.0,
    fkin,
    ikin,
    get_solution_space,
) -> list[float]:
    """티칭 조인트의 TCP를 베이스 X/Y/Z만 평행 이동한 동일 솔루션 조인트 반환."""
    j = [float(v) for v in joints]
    dx, dy, dz = float(dx_mm), float(dy_mm), float(dz_mm)
    if not dx and not dy and not dz:
        return j
    tcp_out = fkin(j)
    if isinstance(tcp_out, int) and tcp_out == -1:
        raise RuntimeError("fkin failed for joint TCP offset")
    tcp = [float(v) for v in tcp_out]
    tcp[0] += dx
    tcp[1] += dy
    tcp[2] += dz
    sol = int(get_solution_space(j))
    if sol < 0:
        raise RuntimeError("get_solution_space failed for joint offset")
    result = ikin(tcp, sol)
    if isinstance(result, int) and result == -1:
        raise RuntimeError("ikin failed for joint TCP offset")
    return [float(v) for v in result]


def offset_joint_tcp_z(
    joints: Sequence[float],
    dz_mm: float,
    *,
    fkin,
    ikin,
    get_solution_space,
) -> list[float]:
    """티칭 조인트의 TCP Z만 dz_mm 만큼 올린 동일 솔루션 조인트 반환."""
    return offset_joint_tcp_translation(
        joints,
        dz_mm=dz_mm,
        fkin=fkin,
        ikin=ikin,
        get_solution_space=get_solution_space,
    )
