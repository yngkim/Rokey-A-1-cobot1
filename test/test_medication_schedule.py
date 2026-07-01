"""약 스케줄 저장·식후 타이머 테스트."""

import time

from cobot1.bridge.medication_schedule import (
    MedicationScheduleRunner,
    MedicationScheduleStore,
)


def test_clock_schedule_create_and_describe(tmp_path):
    db = tmp_path / "care.db"
    store = MedicationScheduleStore(db)
    saved = store.create(
        "patient_01",
        {
            "enabled": True,
            "mode": "clock",
            "clock_hour": 9,
            "clock_minute": 30,
            "after_meal_minutes": 30,
        },
    )
    assert saved["enabled"] is True
    assert saved["clock_hour"] == 9
    assert saved["id"]
    assert "09:30" in MedicationScheduleStore.describe(saved)


def test_list_update_delete(tmp_path):
    db = tmp_path / "care.db"
    store = MedicationScheduleStore(db)
    created = store.create(
        "patient_01",
        {"enabled": True, "mode": "clock", "clock_hour": 8, "clock_minute": 0},
    )
    items = store.list_by_user("patient_01")
    assert len(items) == 1
    assert items[0]["id"] == created["id"]

    updated = store.update(created["id"], {"clock_hour": 10})
    assert updated["clock_hour"] == 10

    assert store.delete(created["id"]) is True
    assert store.list_by_user("patient_01") == []


def test_after_meal_pending_and_fire(tmp_path):
    db = tmp_path / "care.db"
    store = MedicationScheduleStore(db)
    store.create(
        "patient_01",
        {"enabled": True, "mode": "after_meal", "after_meal_minutes": 5},
    )
    meal_ts = time.time() - 600
    store.schedule_after_meal("patient_01", meal_ts=meal_ts)
    items = store.list_by_user("patient_01")
    assert items[0]["pending_after_meal_due"] is not None

    fired = []

    def start_task(task_id, user_id):
        fired.append((task_id, user_id))
        return {"success": True, "code": "STARTED", "message": "ok"}

    runner = MedicationScheduleRunner(
        store,
        start_task=start_task,
        is_blocked=lambda: False,
        get_active_user_id=lambda: "patient_01",
    )
    runner.tick()
    assert fired == [("prepare_medication", "patient_01")]
    items = store.list_by_user("patient_01")
    assert items[0]["pending_after_meal_due"] is None
