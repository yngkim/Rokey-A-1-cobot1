"""Doosan 순응 제어(task_compliance_ctrl) 헬퍼."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Sequence


@contextmanager
def compliance_session(
    stx: Sequence[float],
    time_sec: float = 0.3,
    node_logger=None,
    ref: int | None = None,
) -> Iterator[None]:
    """순응 제어 활성화 → yield → 해제.

    ref: DR_BASE(0) 권장 — 베이스 Z 수직 접촉 탐색 시 툴 좌표계 뒤틀림 방지.
    """
    from cobot1.motion.dsr_imports import import_dsr_api

    api = import_dsr_api()
    stiffness = [float(v) for v in stx]
    ramp = max(0.0, min(1.0, float(time_sec)))
    coord_ref = api["DR_BASE"] if ref is None else int(ref)

    result = _task_compliance_ctrl(api, stiffness, ramp, coord_ref, node_logger)
    if result != 0 and node_logger is not None:
        node_logger.warn(f"task_compliance_ctrl 실패 (code={result}), 순응 없이 진행")

    try:
        yield
    finally:
        release = api["release_compliance_ctrl"]()
        if release != 0 and node_logger is not None:
            node_logger.warn(f"release_compliance_ctrl 실패 (code={release})")


def _task_compliance_ctrl(
    api: dict,
    stiffness: list[float],
    ramp: float,
    ref: int,
    node_logger,
) -> int:
    """DR_BASE 기준 순응 제어 (서비스 ref 명시)."""
    try:
        import rclpy
        from DSR_ROBOT2 import g_node
        from dsr_msgs2.srv import TaskComplianceCtrl

        from cobot1.robot_config import ROBOT_ID

        client = g_node.create_client(
            TaskComplianceCtrl, f"/{ROBOT_ID}/force/task_compliance_ctrl"
        )
        if not client.wait_for_service(timeout_sec=2.0):
            if node_logger:
                node_logger.warn("task_compliance_ctrl 서비스 대기 실패, 기본 API 사용")
            return api["task_compliance_ctrl"](stiffness, ramp)

        req = TaskComplianceCtrl.Request()
        req.stx = stiffness
        req.ref = int(ref)
        req.time = float(ramp)
        future = client.call_async(req)
        rclpy.spin_until_future_complete(g_node, future, timeout_sec=5.0)
        result = future.result()
        g_node.destroy_client(client)
        if result is None:
            return -1
        return 0 if result.success else -1
    except Exception as exc:
        if node_logger:
            node_logger.warn(
                f"task_compliance_ctrl(ref={ref}) 실패: {exc}, 기본 API 사용"
            )
        return api["task_compliance_ctrl"](stiffness, ramp)
