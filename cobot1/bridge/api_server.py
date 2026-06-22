"""ROS2 care_server ↔ 웹앱 HTTP/WebSocket 브릿지."""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

import rclpy
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import String
from std_srvs.srv import Trigger

from cobot1.robot_config import ROBOT_ID

TASK_CATALOG: list[dict[str, str]] = [
    {"id": "open_bottle", "label": "페트병 뚜껑 열기", "icon": "🍼", "group": "음료"},
    {"id": "insert_straw", "label": "빨대 꽂기", "icon": "🥤", "group": "음료"},
    {"id": "pour_water", "label": "물 따르기", "icon": "💧", "group": "음료"},
    {"id": "pick_place_pill", "label": "알약 옮기기", "icon": "💊", "group": "복약"},
    {"id": "pull_place_tissue", "label": "휴지 건네기", "icon": "🧻", "group": "생활"},
    {"id": "turn_off_switch", "label": "스위치 끄기", "icon": "🔌", "group": "생활"},
    {"id": "go_home", "label": "홈 위치", "icon": "🏠", "group": "제어"},
]


class RosBridge(Node):
    def __init__(self, loop: asyncio.AbstractEventLoop):
        super().__init__("care_web_bridge", namespace=ROBOT_ID)
        self._loop = loop
        self._ws_clients: set[Any] = set()
        self._busy = False
        self._last_status: dict[str, Any] = {}
        self._last_alert: dict[str, Any] | None = None

        self.create_subscription(String, "cobot1/status", self._on_status, 10)
        self.create_subscription(String, "cobot1/safety_alert", self._on_alert, 10)

        self._trigger_clients: dict[str, Any] = {}
        for task in TASK_CATALOG:
            name = task["id"]
            self._trigger_clients[name] = self.create_client(Trigger, f"cobot1/{name}")

        self.get_logger().info("care_web_bridge 준비 완료 (namespace=%s)" % ROBOT_ID)

    def _on_status(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError:
            payload = {"message": msg.data}
        self._last_status = payload
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
        if self._last_status:
            asyncio.run_coroutine_threadsafe(
                ws.send_text(
                    json.dumps({"type": "status", "data": self._last_status}, ensure_ascii=False)
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

    def call_task(self, task_id: str, timeout_sec: float = 300.0) -> dict[str, Any]:
        if self._busy:
            return {
                "success": False,
                "message": "다른 작업이 실행 중입니다. 완료 후 다시 시도해 주세요.",
                "code": "BUSY",
            }

        client = self._trigger_clients.get(task_id)
        if client is None:
            return {"success": False, "message": f"알 수 없는 작업: {task_id}", "code": "NOT_FOUND"}

        if not client.wait_for_service(timeout_sec=2.0):
            return {
                "success": False,
                "message": "care_server에 연결되지 않았습니다. ros2 run cobot1 care_server 를 실행하세요.",
                "code": "NO_SERVER",
            }

        self._busy = True
        try:
            future = client.call_async(Trigger.Request())
            rclpy.spin_until_future_complete(self, future, timeout_sec=timeout_sec)
            if not future.done():
                return {"success": False, "message": "작업 시간 초과", "code": "TIMEOUT"}
            result = future.result()
            if result is None:
                return {"success": False, "message": "서비스 응답 없음", "code": "NO_RESPONSE"}
            return {
                "success": bool(result.success),
                "message": result.message or ("완료" if result.success else "실패"),
                "code": "OK" if result.success else "TASK_FAILED",
            }
        except Exception as exc:
            return {"success": False, "message": str(exc), "code": "ERROR"}
        finally:
            self._busy = False


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
        return {
            "ok": bridge is not None,
            "robot_namespace": ROBOT_ID,
            "busy": bridge._busy if bridge else False,
        }

    @app.get("/api/tasks")
    def list_tasks():
        return {"tasks": TASK_CATALOG}

    @app.post("/api/tasks/{task_id}")
    def run_task(task_id: str):
        bridge = bridge_holder.get("bridge")
        if bridge is None:
            raise HTTPException(status_code=503, detail="ROS bridge 초기화 중")
        result = bridge.call_task(task_id)
        if result.get("code") == "NOT_FOUND":
            raise HTTPException(status_code=404, detail=result["message"])
        return result

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

    dist = Path(__file__).resolve().parents[2] / "web" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="static")

    return app


def main():
    import uvicorn

    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")


if __name__ == "__main__":
    main()
