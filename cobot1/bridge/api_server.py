"""ROS2 태스크 ↔ 웹앱 HTTP/WebSocket 브릿지 (care_server 없이 직접 실행)."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from typing import Any

import rclpy
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import String

from cobot1.bridge.task_session import WebTaskSession
from cobot1.robot_config import ROBOT_ID
from cobot1.task_runner import TASK_REGISTRY, _ensure_registry

TASK_CATALOG: list[dict[str, str]] = [
    {"id": "open_bottle", "label": "페트병 뚜껑 열기", "icon": "🍼", "group": "음료"},
    {"id": "pour_water", "label": "물 따르기", "icon": "💧", "group": "음료"},
    {"id": "pick_place_pill", "label": "알약 서랍에서 꺼내기", "icon": "💊", "group": "복약"},
    {"id": "place_on_charger", "label": "충전기에 놓기", "icon": "📲", "group": "스마트폰"},
    {"id": "pick_from_charger", "label": "충전기에서 가져오기", "icon": "🔋", "group": "스마트폰"},
    {"id": "go_home", "label": "기본 위치 복귀", "icon": "🏠", "group": "제어"},
]

TASK_IDS = {task["id"] for task in TASK_CATALOG}


class RosBridge(Node):
    def __init__(self, loop: asyncio.AbstractEventLoop):
        super().__init__("care_web_bridge", namespace=ROBOT_ID)
        self._loop = loop
        self._ws_clients: set[Any] = set()
        self._busy = False
        self._robot_ready = False
        self._current_task_id = ""
        self._task_lock = threading.Lock()
        self._task_session = WebTaskSession()
        self._last_status: dict[str, Any] = {}
        self._last_alert: dict[str, Any] | None = None

        self.create_subscription(String, "cobot1/status", self._on_status, 10)
        self.create_subscription(String, "cobot1/safety_alert", self._on_alert, 10)

        from dsr_msgs2.srv import SetRobotMode

        self._robot_mode_client = self.create_client(
            SetRobotMode, "system/set_robot_mode"
        )
        self.refresh_robot_ready()
        self.get_logger().info(
            "care_web_bridge 준비 (namespace=%s, robot_ready=%s)"
            % (ROBOT_ID, self._robot_ready)
        )

    def refresh_robot_ready(self) -> bool:
        self._robot_ready = self._robot_mode_client.wait_for_service(timeout_sec=0.5)
        return self._robot_ready

    def _is_terminal_status(self, payload: dict[str, Any]) -> bool:
        state = payload.get("state", "")
        step = payload.get("step", "")
        if step == "finish" and state == "done":
            return True
        if state in ("error", "stopped"):
            return True
        if step == "safe_abort" and state in ("error", "recovered", "critical"):
            return True
        return False

    def _on_status(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError:
            payload = {"message": msg.data}
        self._last_status = payload
        state = payload.get("state", "")
        if payload.get("task"):
            with self._task_lock:
                self._current_task_id = payload["task"]
        with self._task_lock:
            if self._is_terminal_status(payload):
                self._busy = False
                self._current_task_id = ""
            elif state == "running":
                self._busy = True
        self._broadcast({"type": "status", "data": payload})

    def _on_alert(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError:
            payload = {"message": msg.data}
        self._last_alert = payload
        self._broadcast({"type": "safety_alert", "data": payload})

    def _broadcast(self, message: dict) -> None:
        if not self._ws_clients:
            return
        text = json.dumps(message, ensure_ascii=False)

        def _send():
            dead = set()
            for ws in self._ws_clients:
                try:
                    asyncio.run_coroutine_threadsafe(ws.send_text(text), self._loop)
                except Exception:
                    dead.add(ws)
            self._ws_clients -= dead

        self._loop.call_soon_threadsafe(_send)

    def register_ws(self, ws) -> None:
        self._ws_clients.add(ws)
        with self._task_lock:
            sync = {
                "busy": self._busy,
                "current_task": self._current_task_id,
                "last_status": self._last_status,
            }
        asyncio.run_coroutine_threadsafe(
            ws.send_text(
                json.dumps({"type": "sync", "data": sync}, ensure_ascii=False)
            ),
            self._loop,
        )
        if self._last_alert:
            asyncio.run_coroutine_threadsafe(
                ws.send_text(
                    json.dumps({"type": "safety_alert", "data": self._last_alert}, ensure_ascii=False)
                ),
                self._loop,
            )

    def unregister_ws(self, ws) -> None:
        self._ws_clients.discard(ws)

    def _execute_task(self, task_id: str) -> bool:
        return self._task_session.run(task_id)

    def shutdown_session(self) -> None:
        self._task_session.cleanup()

    def stop_task(self) -> dict[str, Any]:
        with self._task_lock:
            if not self._busy:
                return {
                    "success": False,
                    "message": "실행 중인 작업이 없습니다.",
                    "code": "NOT_RUNNING",
                }
        stopped = self._task_session.request_stop()
        return {
            "success": stopped,
            "message": "정지 요청을 보냈습니다. 로봇이 안전하게 멈춥니다.",
            "code": "STOPPING",
        }

    def start_task(self, task_id: str) -> dict[str, Any]:
        if task_id not in TASK_IDS:
            return {
                "success": False,
                "message": f"알 수 없는 작업: {task_id}",
                "code": "NOT_FOUND",
            }

        with self._task_lock:
            if self._busy and task_id == "go_home":
                self._task_session.request_stop()
                time.sleep(1.0)
                self._busy = False
                self._current_task_id = ""
            elif self._busy:
                return {
                    "success": False,
                    "message": "다른 작업이 실행 중입니다. 완료 후 다시 시도해 주세요.",
                    "code": "BUSY",
                }
            if not self.refresh_robot_ready():
                return {
                    "success": False,
                    "message": (
                        "로봇 제어 서비스에 연결되지 않았습니다. "
                        "bringup을 실행하고 SERVO ON 상태인지 확인하세요."
                    ),
                    "code": "NO_ROBOT",
                }
            _ensure_registry()
            if task_id not in TASK_REGISTRY:
                return {
                    "success": False,
                    "message": f"등록되지 않은 작업: {task_id}",
                    "code": "NOT_FOUND",
                }
            self._busy = True
            self._current_task_id = task_id

        label = next((t["label"] for t in TASK_CATALOG if t["id"] == task_id), task_id)

        def _worker():
            success = False
            try:
                success = self._execute_task(task_id)
            except Exception as exc:
                self.get_logger().error(f"태스크 {task_id} 실패: {exc}")
            finally:
                with self._task_lock:
                    self._busy = False
                    self._current_task_id = ""
                self._broadcast(
                    {
                        "type": "task_complete",
                        "data": {"task": task_id, "success": success},
                    }
                )

        threading.Thread(
            target=_worker,
            name=f"cobot1_web_{task_id}",
            daemon=True,
        ).start()

        return {
            "success": True,
            "message": f"{label} 실행을 시작했습니다 (ros2 run cobot1 {task_id})",
            "code": "STARTED",
        }


_ros_node: RosBridge | None = None
_ros_executor: MultiThreadedExecutor | None = None
_ros_thread: threading.Thread | None = None


def start_ros(loop: asyncio.AbstractEventLoop) -> RosBridge:
    global _ros_node, _ros_executor, _ros_thread
    if _ros_node is not None:
        return _ros_node

    if not rclpy.ok():
        rclpy.init()
    _ros_node = RosBridge(loop)
    _ros_executor = MultiThreadedExecutor()
    _ros_executor.add_node(_ros_node)

    def _spin():
        _ros_executor.spin()

    _ros_thread = threading.Thread(target=_spin, name="ros_spin", daemon=True)
    _ros_thread.start()
    return _ros_node


def get_ros_node() -> RosBridge:
    if _ros_node is None:
        raise RuntimeError("ROS bridge not started")
    return _ros_node


def _web_dist_dir():
    """설치(share) 또는 개발(소스) 경로에서 web/dist 를 찾습니다."""
    from pathlib import Path

    try:
        from ament_index_python.packages import get_package_share_directory

        share = Path(get_package_share_directory("cobot1"))
        installed = share / "web" / "dist"
        if installed.is_dir():
            return installed
    except Exception:
        pass

    source = Path(__file__).resolve().parents[3] / "web" / "dist"
    if source.is_dir():
        return source
    return Path()


def create_app():
    try:
        from contextlib import asynccontextmanager

        from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.staticfiles import StaticFiles
    except ImportError as exc:
        raise ImportError(
            "FastAPI가 필요합니다: pip install fastapi uvicorn[standard]"
        ) from exc

    from pathlib import Path

    bridge_holder: dict[str, RosBridge] = {}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        loop = asyncio.get_running_loop()
        bridge_holder["bridge"] = start_ros(loop)
        yield
        bridge = bridge_holder.get("bridge")
        if bridge is not None:
            bridge.shutdown_session()
        if _ros_executor is not None:
            _ros_executor.shutdown()
        if rclpy.ok():
            rclpy.shutdown()

    app = FastAPI(title="Cobot1 Care API", version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health():
        bridge = bridge_holder.get("bridge")
        if bridge is None:
            return {
                "ok": False,
                "api_ok": False,
                "robot_ready": False,
                "busy": False,
                "robot_namespace": ROBOT_ID,
            }
        robot_ready = bridge.refresh_robot_ready()
        label = next(
            (t["label"] for t in TASK_CATALOG if t["id"] == bridge._current_task_id),
            bridge._current_task_id,
        )
        return {
            "ok": True,
            "api_ok": True,
            "robot_ready": robot_ready,
            "busy": bridge._busy,
            "current_task": bridge._current_task_id,
            "current_task_label": label,
            "current_step": bridge._last_status.get("step", ""),
            "robot_namespace": ROBOT_ID,
        }

    @app.get("/api/tasks")
    def list_tasks():
        return {"tasks": TASK_CATALOG}

    @app.post("/api/tasks/{task_id}")
    def run_task(task_id: str):
        bridge = bridge_holder.get("bridge")
        if bridge is None:
            raise HTTPException(status_code=503, detail="ROS bridge 초기화 중")
        result = bridge.start_task(task_id)
        if result.get("code") == "NOT_FOUND":
            raise HTTPException(status_code=404, detail=result["message"])
        return result

    @app.post("/api/stop")
    def stop_task():
        bridge = bridge_holder.get("bridge")
        if bridge is None:
            raise HTTPException(status_code=503, detail="ROS bridge 초기화 중")
        return bridge.stop_task()

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        bridge = bridge_holder.get("bridge")
        if bridge is None:
            await ws.close(code=1013)
            return
        await ws.accept()
        bridge.register_ws(ws)
        try:
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            bridge.unregister_ws(ws)

    dist = _web_dist_dir()
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="static")

    return app


def main():
    import uvicorn

    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")


if __name__ == "__main__":
    main()
