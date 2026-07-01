"""복약 자동 실행 스케줄 — 사용자별 여러 항목."""

from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from datetime import datetime
from typing import Any, Callable

DEFAULT_ITEM: dict[str, Any] = {
    "enabled": True,
    "mode": "clock",
    "clock_hour": 8,
    "clock_minute": 0,
    "after_meal_minutes": 30,
}

VALID_MODES = frozenset({"clock", "after_meal"})


def _today_local() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _now_hm() -> tuple[int, int]:
    now = datetime.now()
    return now.hour, now.minute


class MedicationScheduleStore:
    def __init__(self, db_path) -> None:
        self._path = db_path
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
                    CREATE TABLE IF NOT EXISTS medication_schedule_items (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        enabled INTEGER NOT NULL DEFAULT 1,
                        mode TEXT NOT NULL DEFAULT 'clock',
                        clock_hour INTEGER NOT NULL DEFAULT 8,
                        clock_minute INTEGER NOT NULL DEFAULT 0,
                        after_meal_minutes INTEGER NOT NULL DEFAULT 30,
                        pending_after_meal_due REAL,
                        last_clock_fire_key TEXT,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_med_schedule_items_user
                        ON medication_schedule_items(user_id, updated_at DESC);

                    CREATE TABLE IF NOT EXISTS medication_schedules (
                        user_id TEXT PRIMARY KEY,
                        enabled INTEGER NOT NULL DEFAULT 0,
                        mode TEXT NOT NULL DEFAULT 'clock',
                        clock_hour INTEGER NOT NULL DEFAULT 8,
                        clock_minute INTEGER NOT NULL DEFAULT 0,
                        after_meal_minutes INTEGER NOT NULL DEFAULT 30,
                        pending_after_meal_due REAL,
                        last_clock_fire_key TEXT,
                        updated_at REAL NOT NULL
                    );
                    """
                )
                self._migrate_legacy(conn)
                conn.commit()
            finally:
                conn.close()

    def _migrate_legacy(self, conn: sqlite3.Connection) -> None:
        try:
            rows = conn.execute("SELECT * FROM medication_schedules").fetchall()
        except sqlite3.OperationalError:
            return
        for row in rows:
            uid = row["user_id"]
            exists = conn.execute(
                "SELECT 1 FROM medication_schedule_items WHERE user_id = ? LIMIT 1",
                (uid,),
            ).fetchone()
            if exists:
                continue
            if not row["enabled"] and not row["updated_at"]:
                continue
            now = time.time()
            conn.execute(
                """
                INSERT INTO medication_schedule_items (
                    id, user_id, enabled, mode, clock_hour, clock_minute,
                    after_meal_minutes, pending_after_meal_due,
                    last_clock_fire_key, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    uid,
                    int(row["enabled"]),
                    row["mode"],
                    int(row["clock_hour"]),
                    int(row["clock_minute"]),
                    int(row["after_meal_minutes"]),
                    row["pending_after_meal_due"],
                    row["last_clock_fire_key"],
                    now,
                    float(row["updated_at"] or now),
                ),
            )

    def list_by_user(self, user_id: str) -> list[dict[str, Any]]:
        uid = user_id.strip()
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    """
                    SELECT * FROM medication_schedule_items
                    WHERE user_id = ?
                    ORDER BY mode, clock_hour, clock_minute, created_at
                    """,
                    (uid,),
                ).fetchall()
            finally:
                conn.close()
        return [self._with_summary(self._row_to_dict(row)) for row in rows]

    def get_item(self, schedule_id: str) -> dict[str, Any] | None:
        sid = schedule_id.strip()
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT * FROM medication_schedule_items WHERE id = ?",
                    (sid,),
                ).fetchone()
            finally:
                conn.close()
        if row is None:
            return None
        return self._with_summary(self._row_to_dict(row))

    def _validate_data(self, data: dict[str, Any]) -> dict[str, Any]:
        mode = str(data.get("mode", "clock"))
        if mode not in VALID_MODES:
            raise ValueError("mode는 clock 또는 after_meal 이어야 합니다")
        hour = int(data.get("clock_hour", 8))
        minute = int(data.get("clock_minute", 0))
        after_min = int(data.get("after_meal_minutes", 30))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("시간이 올바르지 않습니다")
        if not (1 <= after_min <= 180):
            raise ValueError("식후 시간은 1~180분 사이여야 합니다")
        return {
            "enabled": bool(data.get("enabled", True)),
            "mode": mode,
            "clock_hour": hour,
            "clock_minute": minute,
            "after_meal_minutes": after_min,
        }

    def create(self, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
        uid = user_id.strip()
        payload = self._validate_data(data)
        now = time.time()
        sid = str(uuid.uuid4())
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO medication_schedule_items (
                        id, user_id, enabled, mode, clock_hour, clock_minute,
                        after_meal_minutes, pending_after_meal_due,
                        last_clock_fire_key, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)
                    """,
                    (
                        sid,
                        uid,
                        1 if payload["enabled"] else 0,
                        payload["mode"],
                        payload["clock_hour"],
                        payload["clock_minute"],
                        payload["after_meal_minutes"],
                        now,
                        now,
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        item = self.get_item(sid)
        assert item is not None
        return item

    def update(self, schedule_id: str, data: dict[str, Any]) -> dict[str, Any]:
        existing = self.get_item(schedule_id)
        if existing is None:
            raise ValueError("저장된 약 시간을 찾을 수 없습니다")
        payload = self._validate_data({**existing, **data})
        now = time.time()
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    UPDATE medication_schedule_items SET
                        enabled = ?, mode = ?, clock_hour = ?, clock_minute = ?,
                        after_meal_minutes = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        1 if payload["enabled"] else 0,
                        payload["mode"],
                        payload["clock_hour"],
                        payload["clock_minute"],
                        payload["after_meal_minutes"],
                        now,
                        schedule_id,
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        item = self.get_item(schedule_id)
        assert item is not None
        return item

    def delete(self, schedule_id: str) -> bool:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "DELETE FROM medication_schedule_items WHERE id = ?",
                    (schedule_id.strip(),),
                )
                conn.commit()
                return cur.rowcount > 0
            finally:
                conn.close()

    def schedule_after_meal(self, user_id: str, meal_ts: float | None = None) -> None:
        uid = user_id.strip()
        base = float(meal_ts if meal_ts is not None else time.time())
        now = time.time()
        items = [
            item
            for item in self.list_by_user(uid)
            if item.get("enabled") and item.get("mode") == "after_meal"
        ]
        if not items:
            return
        with self._lock:
            conn = self._connect()
            try:
                for item in items:
                    minutes = int(item.get("after_meal_minutes", 30))
                    due = base + minutes * 60.0
                    conn.execute(
                        """
                        UPDATE medication_schedule_items
                        SET pending_after_meal_due = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (due, now, item["id"]),
                    )
                conn.commit()
            finally:
                conn.close()

    def clear_pending_after_meal(self, schedule_id: str) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    UPDATE medication_schedule_items
                    SET pending_after_meal_due = NULL, updated_at = ?
                    WHERE id = ?
                    """,
                    (time.time(), schedule_id),
                )
                conn.commit()
            finally:
                conn.close()

    def mark_clock_fired(self, schedule_id: str, fire_key: str) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    UPDATE medication_schedule_items
                    SET last_clock_fire_key = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (fire_key, time.time(), schedule_id),
                )
                conn.commit()
            finally:
                conn.close()

    def list_enabled(self) -> list[dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT * FROM medication_schedule_items WHERE enabled = 1"
                ).fetchall()
            finally:
                conn.close()
        return [self._row_to_dict(row) for row in rows]

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        pending = row["pending_after_meal_due"]
        return {
            "id": row["id"],
            "user_id": row["user_id"],
            "enabled": bool(row["enabled"]),
            "mode": row["mode"],
            "clock_hour": int(row["clock_hour"]),
            "clock_minute": int(row["clock_minute"]),
            "after_meal_minutes": int(row["after_meal_minutes"]),
            "pending_after_meal_due": float(pending) if pending is not None else None,
            "last_clock_fire_key": row["last_clock_fire_key"],
            "created_at": float(row["created_at"]),
            "updated_at": float(row["updated_at"]),
        }

    @staticmethod
    def describe(item: dict[str, Any]) -> str:
        if item.get("mode") == "after_meal":
            mins = item.get("after_meal_minutes", 30)
            pending = item.get("pending_after_meal_due")
            if pending:
                due = datetime.fromtimestamp(pending).strftime("%H:%M")
                return f"식후 {mins}분 (예정 {due})"
            return f"식후 {mins}분"
        h = item.get("clock_hour", 8)
        m = item.get("clock_minute", 0)
        return f"매일 {h:02d}:{m:02d}"

    @staticmethod
    def mode_label(mode: str) -> str:
        return "시간 설정" if mode == "clock" else "식후 시간"

    def _with_summary(self, item: dict[str, Any]) -> dict[str, Any]:
        item = dict(item)
        item["summary"] = self.describe(item)
        item["mode_label"] = self.mode_label(item.get("mode", "clock"))
        return item


class MedicationScheduleRunner:
    def __init__(
        self,
        store: MedicationScheduleStore,
        *,
        start_task: Callable[[str, str | None], dict[str, Any]],
        is_blocked: Callable[[], bool],
        get_active_user_id: Callable[[], str],
        on_trigger: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._store = store
        self._start_task = start_task
        self._is_blocked = is_blocked
        self._get_active_user_id = get_active_user_id
        self._on_trigger = on_trigger

    def on_meal_event(self, user_id: str, meal_ts: float | None = None) -> None:
        self._store.schedule_after_meal(user_id, meal_ts=meal_ts)

    def tick(self) -> None:
        now = time.time()
        hour, minute = _now_hm()
        fire_key = f"{_today_local()}|{hour:02d}:{minute:02d}"

        for item in self._store.list_enabled():
            if item["mode"] == "clock":
                if item["clock_hour"] != hour or item["clock_minute"] != minute:
                    continue
                if item.get("last_clock_fire_key") == fire_key:
                    continue
                self._try_fire(item, "clock", fire_key=fire_key)
            elif item["mode"] == "after_meal":
                due = item.get("pending_after_meal_due")
                if due is None or now < float(due):
                    continue
                self._try_fire(item, "after_meal")

    def _try_fire(
        self,
        item: dict[str, Any],
        reason: str,
        fire_key: str | None = None,
    ) -> None:
        if self._is_blocked():
            return

        user_id = item["user_id"]
        result = self._start_task("prepare_medication", user_id)
        payload = {
            "user_id": user_id,
            "schedule_id": item["id"],
            "reason": reason,
            "success": bool(result.get("success")),
            "message": result.get("message", ""),
            "code": result.get("code", ""),
        }
        if self._on_trigger:
            self._on_trigger(payload)

        if not result.get("success"):
            return

        if reason == "clock" and fire_key:
            self._store.mark_clock_fired(item["id"], fire_key)
        elif reason == "after_meal":
            self._store.clear_pending_after_meal(item["id"])


_store: MedicationScheduleStore | None = None


def get_medication_schedule_store(db_path=None) -> MedicationScheduleStore:
    global _store
    if _store is None:
        from cobot1.bridge.care_store import _db_path

        _store = MedicationScheduleStore(db_path or _db_path())
    return _store
