"""관리자용 이벤트·이력 SQLite 저장."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from cobot1.runtime_state import runtime_state_dir


def _db_path() -> Path:
    path = runtime_state_dir() / "admin"
    path.mkdir(parents=True, exist_ok=True)
    return path / "events.db"


class EventStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self._path = db_path or _db_path()
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS task_runs (
                        id TEXT PRIMARY KEY,
                        task_id TEXT NOT NULL,
                        trigger TEXT NOT NULL DEFAULT 'web',
                        voice_command_id TEXT,
                        started_at REAL NOT NULL,
                        ended_at REAL,
                        success INTEGER,
                        code TEXT
                    );
                    CREATE INDEX IF NOT EXISTS idx_task_runs_started
                        ON task_runs(started_at DESC);
                    CREATE INDEX IF NOT EXISTS idx_task_runs_task
                        ON task_runs(task_id);

                    CREATE TABLE IF NOT EXISTS status_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        run_id TEXT,
                        task TEXT,
                        step TEXT,
                        state TEXT,
                        message TEXT,
                        payload_json TEXT,
                        ts REAL NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_status_events_run
                        ON status_events(run_id, ts);
                    CREATE INDEX IF NOT EXISTS idx_status_events_ts
                        ON status_events(ts DESC);

                    CREATE TABLE IF NOT EXISTS safety_alerts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        code TEXT,
                        level TEXT,
                        message TEXT,
                        task TEXT,
                        detail_json TEXT,
                        ts REAL NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_safety_alerts_ts
                        ON safety_alerts(ts DESC);

                    CREATE TABLE IF NOT EXISTS audit_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        action TEXT NOT NULL,
                        actor TEXT NOT NULL DEFAULT 'system',
                        detail_json TEXT,
                        ts REAL NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_audit_log_ts
                        ON audit_log(ts DESC);
                    """
                )
                conn.commit()
            finally:
                conn.close()

    def start_run(
        self,
        task_id: str,
        trigger: str = "web",
        voice_command_id: str | None = None,
    ) -> str:
        run_id = str(uuid.uuid4())
        now = time.time()
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO task_runs
                        (id, task_id, trigger, voice_command_id, started_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (run_id, task_id, trigger, voice_command_id, now),
                )
                conn.commit()
            finally:
                conn.close()
        return run_id

    def finish_run(
        self,
        run_id: str,
        *,
        success: bool | None,
        code: str | None = None,
    ) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    UPDATE task_runs
                    SET ended_at = ?, success = ?, code = ?
                    WHERE id = ?
                    """,
                    (time.time(), int(success) if success is not None else None, code, run_id),
                )
                conn.commit()
            finally:
                conn.close()

    def record_status(
        self,
        payload: dict[str, Any],
        run_id: str | None = None,
    ) -> None:
        ts = float(payload.get("timestamp") or time.time())
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO status_events
                        (run_id, task, step, state, message, payload_json, ts)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        payload.get("task", ""),
                        payload.get("step", ""),
                        payload.get("state", ""),
                        payload.get("message", ""),
                        json.dumps(payload, ensure_ascii=False),
                        ts,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def record_alert(self, payload: dict[str, Any]) -> None:
        ts = float(payload.get("timestamp") or time.time())
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO safety_alerts
                        (code, level, message, task, detail_json, ts)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payload.get("code", ""),
                        payload.get("level", ""),
                        payload.get("message", ""),
                        payload.get("task", ""),
                        json.dumps(payload, ensure_ascii=False),
                        ts,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def audit(self, action: str, actor: str = "system", detail: dict | None = None) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO audit_log (action, actor, detail_json, ts)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        action,
                        actor,
                        json.dumps(detail or {}, ensure_ascii=False),
                        time.time(),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    def list_runs(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        task: str | None = None,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM task_runs"
        params: list[Any] = []
        if task:
            query += " WHERE task_id = ?"
            params.append(task)
        query += " ORDER BY started_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(query, params).fetchall()
                return [self._row_run(row) for row in rows]
            finally:
                conn.close()

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM task_runs WHERE id = ?", (run_id,)
                ).fetchone()
                return self._row_run(row) if row else None
            finally:
                conn.close()

    def list_run_events(self, run_id: str) -> list[dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    """
                    SELECT * FROM status_events
                    WHERE run_id = ?
                    ORDER BY ts ASC
                    """,
                    (run_id,),
                ).fetchall()
                return [self._row_status(row) for row in rows]
            finally:
                conn.close()

    def list_alerts(self, *, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    """
                    SELECT * FROM safety_alerts
                    ORDER BY ts DESC LIMIT ? OFFSET ?
                    """,
                    (limit, offset),
                ).fetchall()
                return [self._row_alert(row) for row in rows]
            finally:
                conn.close()

    def list_audit(self, *, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    """
                    SELECT * FROM audit_log
                    ORDER BY ts DESC LIMIT ? OFFSET ?
                    """,
                    (limit, offset),
                ).fetchall()
                return [self._row_audit(row) for row in rows]
            finally:
                conn.close()

    def list_logs(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        log_type: str | None = None,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        if log_type in (None, "", "status"):
            with self._lock:
                conn = self._connect()
                try:
                    rows = conn.execute(
                        """
                        SELECT 'status' AS log_type, task, step, state, message,
                               payload_json, ts, run_id
                        FROM status_events
                        ORDER BY ts DESC LIMIT ?
                        """,
                        (limit + offset,),
                    ).fetchall()
                    for row in rows:
                        items.append(
                            {
                                "type": "status",
                                "ts": row["ts"],
                                "task": row["task"],
                                "step": row["step"],
                                "state": row["state"],
                                "message": row["message"],
                                "run_id": row["run_id"],
                                "payload": self._json_load(row["payload_json"]),
                            }
                        )
                finally:
                    conn.close()
        if log_type in (None, "", "safety"):
            with self._lock:
                conn = self._connect()
                try:
                    rows = conn.execute(
                        """
                        SELECT code, level, message, task, detail_json, ts
                        FROM safety_alerts
                        ORDER BY ts DESC LIMIT ?
                        """,
                        (limit + offset,),
                    ).fetchall()
                    for row in rows:
                        items.append(
                            {
                                "type": "safety",
                                "ts": row["ts"],
                                "code": row["code"],
                                "level": row["level"],
                                "message": row["message"],
                                "task": row["task"],
                                "payload": self._json_load(row["detail_json"]),
                            }
                        )
                finally:
                    conn.close()
        if log_type in (None, "", "audit"):
            with self._lock:
                conn = self._connect()
                try:
                    rows = conn.execute(
                        """
                        SELECT action, actor, detail_json, ts
                        FROM audit_log
                        ORDER BY ts DESC LIMIT ?
                        """,
                        (limit + offset,),
                    ).fetchall()
                    for row in rows:
                        items.append(
                            {
                                "type": "audit",
                                "ts": row["ts"],
                                "action": row["action"],
                                "actor": row["actor"],
                                "payload": self._json_load(row["detail_json"]),
                            }
                        )
                finally:
                    conn.close()
        items.sort(key=lambda x: x["ts"], reverse=True)
        return items[offset : offset + limit]

    @staticmethod
    def _json_load(text: str | None) -> dict[str, Any]:
        if not text:
            return {}
        try:
            data = json.loads(text)
            return data if isinstance(data, dict) else {"value": data}
        except json.JSONDecodeError:
            return {"raw": text}

    @staticmethod
    def _row_run(row: sqlite3.Row) -> dict[str, Any]:
        started = row["started_at"]
        ended = row["ended_at"]
        duration = (ended - started) if ended else None
        return {
            "id": row["id"],
            "task_id": row["task_id"],
            "trigger": row["trigger"],
            "voice_command_id": row["voice_command_id"],
            "started_at": started,
            "ended_at": ended,
            "duration_sec": duration,
            "success": bool(row["success"]) if row["success"] is not None else None,
            "code": row["code"],
        }

    @staticmethod
    def _row_status(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "run_id": row["run_id"],
            "task": row["task"],
            "step": row["step"],
            "state": row["state"],
            "message": row["message"],
            "ts": row["ts"],
            "payload": EventStore._json_load(row["payload_json"]),
        }

    @staticmethod
    def _row_alert(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "code": row["code"],
            "level": row["level"],
            "message": row["message"],
            "task": row["task"],
            "ts": row["ts"],
            "detail": EventStore._json_load(row["detail_json"]),
        }

    @staticmethod
    def _row_audit(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "action": row["action"],
            "actor": row["actor"],
            "ts": row["ts"],
            "detail": EventStore._json_load(row["detail_json"]),
        }


_store: EventStore | None = None


def get_event_store() -> EventStore:
    global _store
    if _store is None:
        _store = EventStore()
    return _store
