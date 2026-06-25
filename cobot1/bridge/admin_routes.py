"""관리자 REST API 라우트 등록."""

from typing import Any

from cobot1.bridge.admin_auth import (
    create_session,
    revoke_session,
    validate_session,
    verify_password,
)
from cobot1.bridge.event_store import get_event_store
from cobot1.config_loader import load_scenarios
from cobot1.robot_config import ROBOT_ID

SESSION_COOKIE = "cobot1_admin_session"


def register_admin_routes(app, bridge_holder: dict) -> None:
    from fastapi import Depends, HTTPException, Request, Response
    from pydantic import BaseModel

    class LoginRequest(BaseModel):
        password: str

    class MaintenanceRequest(BaseModel):
        enabled: bool

    def _bridge():
        bridge = bridge_holder.get("bridge")
        if bridge is None:
            raise HTTPException(status_code=503, detail="ROS bridge 초기화 중")
        return bridge

    def _session_token(request: Request) -> str | None:
        return request.cookies.get(SESSION_COOKIE)

    def require_admin(request: Request) -> str:
        token = _session_token(request)
        if not validate_session(token):
            raise HTTPException(status_code=401, detail="관리자 로그인이 필요합니다")
        return token

    def _health_payload(bridge) -> dict[str, Any]:
        robot_ready = bridge.refresh_robot_ready()
        if bridge._voice_command_id:
            label = bridge._voice_labels.get(
                bridge._voice_command_id,
                bridge._voice_command_id,
            )
        else:
            from cobot1.bridge.api_server import TASK_CATALOG

            label = next(
                (t["label"] for t in TASK_CATALOG if t["id"] == bridge._current_task_id),
                bridge._current_task_id,
            )
        return {
            "ok": True,
            "api_ok": True,
            "robot_ready": robot_ready,
            "busy": bridge._busy,
            "maintenance": bridge._maintenance_mode,
            "current_task": bridge._current_task_id,
            "current_task_label": label,
            "current_step": bridge._last_status.get("step", ""),
            "robot_namespace": ROBOT_ID,
            "robot_state": bridge._robot_state,
            "robot_state_label": bridge._robot_state_label,
            "last_status": bridge._last_status,
            "last_alert": bridge._last_alert,
        }

    @app.post("/api/admin/login")
    def admin_login(body: LoginRequest, response: Response):
        if not verify_password(body.password):
            raise HTTPException(status_code=401, detail="비밀번호가 올바르지 않습니다")
        token = create_session()
        response.set_cookie(
            key=SESSION_COOKIE,
            value=token,
            httponly=True,
            samesite="lax",
            max_age=8 * 3600,
        )
        get_event_store().audit("admin_login", actor="admin")
        bridge = bridge_holder.get("bridge")
        if bridge is not None:
            bridge._broadcast_audit("admin_login", "admin", {})
        return {"ok": True, "message": "로그인되었습니다"}

    @app.post("/api/admin/logout")
    def admin_logout(request: Request, response: Response):
        token = _session_token(request)
        revoke_session(token)
        response.delete_cookie(SESSION_COOKIE)
        return {"ok": True}

    @app.get("/api/admin/session")
    def admin_session(request: Request):
        return {"authenticated": validate_session(_session_token(request))}

    @app.get("/api/admin/dashboard")
    def admin_dashboard(_: str = Depends(require_admin)):
        return _health_payload(_bridge())

    @app.get("/api/admin/runs")
    def admin_runs(
        limit: int = 50,
        offset: int = 0,
        task: str | None = None,
        _: str = Depends(require_admin),
    ):
        runs = get_event_store().list_runs(limit=limit, offset=offset, task=task or None)
        return {"runs": runs, "limit": limit, "offset": offset}

    @app.get("/api/admin/runs/{run_id}")
    def admin_run_detail(run_id: str, _: str = Depends(require_admin)):
        run = get_event_store().get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="실행 기록을 찾을 수 없습니다")
        events = get_event_store().list_run_events(run_id)
        return {"run": run, "events": events}

    @app.get("/api/admin/runs/{run_id}/events")
    def admin_run_events(run_id: str, _: str = Depends(require_admin)):
        if get_event_store().get_run(run_id) is None:
            raise HTTPException(status_code=404, detail="실행 기록을 찾을 수 없습니다")
        return {"events": get_event_store().list_run_events(run_id)}

    @app.get("/api/admin/alerts")
    def admin_alerts(
        limit: int = 50,
        offset: int = 0,
        _: str = Depends(require_admin),
    ):
        return {
            "alerts": get_event_store().list_alerts(limit=limit, offset=offset),
            "limit": limit,
            "offset": offset,
        }

    @app.get("/api/admin/audit")
    def admin_audit(
        limit: int = 50,
        offset: int = 0,
        _: str = Depends(require_admin),
    ):
        return {
            "entries": get_event_store().list_audit(limit=limit, offset=offset),
            "limit": limit,
            "offset": offset,
        }

    @app.get("/api/admin/logs")
    def admin_logs(
        limit: int = 100,
        offset: int = 0,
        type: str | None = None,
        _: str = Depends(require_admin),
    ):
        return {
            "logs": get_event_store().list_logs(limit=limit, offset=offset, log_type=type),
            "limit": limit,
            "offset": offset,
        }

    @app.get("/api/admin/safety/config")
    def admin_safety_config(_: str = Depends(require_admin)):
        scenarios = load_scenarios()
        return {"safety": scenarios.get("safety", {})}

    @app.post("/api/admin/maintenance")
    def admin_maintenance(
        body: MaintenanceRequest,
        _: str = Depends(require_admin),
    ):
        bridge = _bridge()
        bridge.set_maintenance(body.enabled, actor="admin")
        return {
            "ok": True,
            "maintenance": bridge._maintenance_mode,
            "message": "유지보수 모드가 활성화되었습니다" if body.enabled else "유지보수 모드가 해제되었습니다",
        }

    @app.post("/api/admin/stop")
    def admin_stop(_: str = Depends(require_admin)):
        return _bridge().stop_task(actor="admin")

    @app.post("/api/admin/reset")
    def admin_reset(_: str = Depends(require_admin)):
        return _bridge().reset_and_home(actor="admin")

    @app.post("/api/admin/force_idle")
    def admin_force_idle(_: str = Depends(require_admin)):
        return _bridge().force_idle(actor="admin")
