"""사용자별 일일 복약·식사 케어 기록 SQLite."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from cobot1.bridge.care_config import load_care_config
from cobot1.runtime_state import runtime_state_dir

EVENT_MEDICATION_PREPARE = "medication_prepare"
EVENT_MEDICATION_TAKEN = "medication_taken"
EVENT_MEAL = "meal"

EVENT_LABELS = {
    EVENT_MEDICATION_PREPARE: "약 준비",
    EVENT_MEDICATION_TAKEN: "복용 완료",
    EVENT_MEAL: "식사",
}


def _today_local() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _db_path():
    path = runtime_state_dir() / "admin"
    path.mkdir(parents=True, exist_ok=True)
    return path / "care.db"


class CareStore:
    def __init__(self, db_path=None) -> None:
        self._path = db_path or _db_path()
        self._lock = threading.Lock()
        self._init_db()
        self._seed_users()

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
                    CREATE TABLE IF NOT EXISTS care_users (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        active INTEGER NOT NULL DEFAULT 1,
                        created_at REAL NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS care_events (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        event_date TEXT NOT NULL,
                        quantity REAL NOT NULL DEFAULT 1,
                        unit TEXT NOT NULL DEFAULT 'dose',
                        note TEXT,
                        run_id TEXT,
                        source TEXT NOT NULL DEFAULT 'system',
                        ts REAL NOT NULL,
                        detail_json TEXT,
                        FOREIGN KEY (user_id) REFERENCES care_users(id)
                    );
                    CREATE INDEX IF NOT EXISTS idx_care_events_user_date
                        ON care_events(user_id, event_date, ts DESC);
                    CREATE INDEX IF NOT EXISTS idx_care_events_type_date
                        ON care_events(event_type, event_date);
                    """
                )
                conn.commit()
            finally:
                conn.close()

    def _seed_users(self) -> None:
        cfg = load_care_config()
        for user in cfg.get("default_users", []):
            uid = str(user.get("id", "")).strip()
            name = str(user.get("name", "")).strip()
            if uid and name:
                self.ensure_user(uid, name)

    def ensure_user(self, user_id: str, name: str) -> dict[str, Any]:
        uid = user_id.strip()
        now = time.time()
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM care_users WHERE id = ?", (uid,)
                ).fetchone()
                if row:
                    conn.execute(
                        "UPDATE care_users SET name = ?, active = 1 WHERE id = ?",
                        (name.strip(), uid),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO care_users (id, name, active, created_at)
                        VALUES (?, ?, 1, ?)
                        """,
                        (uid, name.strip(), now),
                    )
                conn.commit()
            finally:
                conn.close()
        return self.get_user(uid) or {"id": uid, "name": name, "active": True}

    def list_users(self, *, active_only: bool = True) -> list[dict[str, Any]]:
        query = "SELECT * FROM care_users"
        if active_only:
            query += " WHERE active = 1"
        query += " ORDER BY name ASC"
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(query).fetchall()
                return [self._row_user(row) for row in rows]
            finally:
                conn.close()

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM care_users WHERE id = ?", (user_id,)
                ).fetchone()
                return self._row_user(row) if row else None
            finally:
                conn.close()

    def record_event(
        self,
        *,
        user_id: str,
        event_type: str,
        quantity: float = 1.0,
        unit: str = "dose",
        note: str | None = None,
        run_id: str | None = None,
        source: str = "system",
        event_date: str | None = None,
        detail: dict | None = None,
    ) -> dict[str, Any]:
        if self.get_user(user_id) is None:
            raise ValueError(f"unknown user: {user_id}")
        event_id = str(uuid.uuid4())
        now = time.time()
        day = event_date or _today_local()
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO care_events
                        (id, user_id, event_type, event_date, quantity, unit,
                         note, run_id, source, ts, detail_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id,
                        user_id,
                        event_type,
                        day,
                        float(quantity),
                        unit,
                        note,
                        run_id,
                        source,
                        now,
                        json.dumps(detail or {}, ensure_ascii=False),
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        return self.get_event(event_id) or {}

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM care_events WHERE id = ?", (event_id,)
                ).fetchone()
                return self._row_event(row) if row else None
            finally:
                conn.close()

    def list_events(
        self,
        *,
        user_id: str,
        event_date: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        day = event_date or _today_local()
        query = "SELECT * FROM care_events WHERE user_id = ? AND event_date = ?"
        params: list[Any] = [user_id, day]
        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)
        query += " ORDER BY ts DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(query, params).fetchall()
                return [self._row_event(row) for row in rows]
            finally:
                conn.close()

    def get_daily_summary(
        self,
        user_id: str,
        event_date: str | None = None,
    ) -> dict[str, Any]:
        day = event_date or _today_local()
        user = self.get_user(user_id)
        if user is None:
            raise ValueError(f"unknown user: {user_id}")
        events = self.list_events(user_id=user_id, event_date=day, limit=200)
        targets = load_care_config().get("daily_targets", {})

        prepare_events = [e for e in events if e["event_type"] == EVENT_MEDICATION_PREPARE]
        taken_events = [e for e in events if e["event_type"] == EVENT_MEDICATION_TAKEN]
        meal_events = [e for e in events if e["event_type"] == EVENT_MEAL]

        prepare_count = sum(e["quantity"] for e in prepare_events)
        taken_count = sum(e["quantity"] for e in taken_events)
        meal_count = len(meal_events)
        meal_amount = sum(e["quantity"] for e in meal_events)

        target_prepare = float(targets.get("medication_prepare", 3))
        target_taken = float(targets.get("medication_taken", 3))
        target_meals = float(targets.get("meals", 3))

        return {
            "user": user,
            "date": day,
            "targets": {
                "medication_prepare": target_prepare,
                "medication_taken": target_taken,
                "meals": target_meals,
            },
            "medication_prepare": {
                "count": prepare_count,
                "target": target_prepare,
                "percent": min(100.0, (prepare_count / target_prepare * 100) if target_prepare else 0),
                "events": prepare_events,
            },
            "medication_taken": {
                "count": taken_count,
                "target": target_taken,
                "percent": min(100.0, (taken_count / target_taken * 100) if target_taken else 0),
                "events": taken_events,
            },
            "meals": {
                "count": meal_count,
                "target": target_meals,
                "amount_total": meal_amount,
                "percent": min(100.0, (meal_count / target_meals * 100) if target_meals else 0),
                "events": meal_events,
                "note": "식사량 자동 측정은 추후 연동 예정",
            },
            "events": events,
        }

    def list_daily_overview(self, event_date: str | None = None) -> list[dict[str, Any]]:
        day = event_date or _today_local()
        users = self.list_users()
        return [self.get_daily_summary(user["id"], day) for user in users]

    @staticmethod
    def _row_user(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "active": bool(row["active"]),
            "created_at": row["created_at"],
        }

    @staticmethod
    def _row_event(row: sqlite3.Row) -> dict[str, Any]:
        detail = {}
        if row["detail_json"]:
            try:
                detail = json.loads(row["detail_json"])
            except json.JSONDecodeError:
                detail = {"raw": row["detail_json"]}
        return {
            "id": row["id"],
            "user_id": row["user_id"],
            "event_type": row["event_type"],
            "event_type_label": EVENT_LABELS.get(row["event_type"], row["event_type"]),
            "event_date": row["event_date"],
            "quantity": row["quantity"],
            "unit": row["unit"],
            "note": row["note"],
            "run_id": row["run_id"],
            "source": row["source"],
            "ts": row["ts"],
            "detail": detail,
        }


_store: CareStore | None = None


def get_care_store() -> CareStore:
    global _store
    if _store is None:
        _store = CareStore()
    return _store
