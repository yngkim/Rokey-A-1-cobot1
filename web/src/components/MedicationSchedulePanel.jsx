import { useEffect, useState } from 'react'
import { createMedicationSchedule, updateMedicationSchedule } from '../api/client'

const HOURS = Array.from({ length: 24 }, (_, i) => i)
const MINUTES = Array.from({ length: 60 }, (_, i) => i)
const AFTER_MEAL_OPTIONS = [15, 20, 30, 40, 45, 60, 90]

function defaultForm(userId) {
  return {
    user_id: userId || '',
    enabled: true,
    mode: 'clock',
    clock_hour: 8,
    clock_minute: 0,
    after_meal_minutes: 30,
  }
}

export default function MedicationSchedulePanel({
  userId,
  disabled,
  onToast,
  compact = false,
  page = false,
  editingItem = null,
  onSaved,
  onCancelEdit,
}) {
  const [form, setForm] = useState(defaultForm(userId))
  const [saving, setSaving] = useState(false)
  const isEditing = !!editingItem?.id

  useEffect(() => {
    if (editingItem) {
      setForm({
        user_id: userId,
        enabled: !!editingItem.enabled,
        mode: editingItem.mode || 'clock',
        clock_hour: editingItem.clock_hour ?? 8,
        clock_minute: editingItem.clock_minute ?? 0,
        after_meal_minutes: editingItem.after_meal_minutes ?? 30,
      })
    } else {
      setForm(defaultForm(userId))
    }
  }, [editingItem, userId])

  const handleSave = async () => {
    if (!userId || saving) return
    setSaving(true)
    try {
      const payload = {
        user_id: userId,
        enabled: form.enabled,
        mode: form.mode,
        clock_hour: Number(form.clock_hour),
        clock_minute: Number(form.clock_minute),
        after_meal_minutes: Number(form.after_meal_minutes),
      }
      if (isEditing) {
        await updateMedicationSchedule(editingItem.id, payload)
        onToast?.('약 시간을 수정했습니다', 'info')
      } else {
        await createMedicationSchedule(payload)
        onToast?.('약 시간을 저장했습니다', 'info')
        setForm(defaultForm(userId))
      }
      onSaved?.()
    } catch (err) {
      onToast?.(err.message, 'error')
    } finally {
      setSaving(false)
    }
  }

  if (!userId) return null

  return (
    <section
      className={[
        'med-schedule',
        compact ? 'med-schedule-compact' : '',
        page ? 'med-schedule-page' : '',
      ]
        .filter(Boolean)
        .join(' ')}
    >
      {!page && (
        <div className="med-schedule-header">
          <h2 className="med-schedule-title">💊 약 복용 시간</h2>
          <label className="med-schedule-toggle">
            <input
              type="checkbox"
              checked={!!form.enabled}
              onChange={(e) => setForm((prev) => ({ ...prev, enabled: e.target.checked }))}
              disabled={disabled}
            />
            <span>자동 약 준비 {form.enabled ? '켜짐' : '꺼짐'}</span>
          </label>
        </div>
      )}

      {page && (
        <>
          <h2 className="med-schedule-form-title">
            {isEditing ? '약 시간 수정' : '새 약 시간 추가'}
          </h2>
          <label className="med-schedule-toggle med-schedule-toggle-page">
            <input
              type="checkbox"
              checked={!!form.enabled}
              onChange={(e) => setForm((prev) => ({ ...prev, enabled: e.target.checked }))}
              disabled={disabled}
            />
            <span>자동 약 준비 {form.enabled ? '켜짐' : '꺼짐'}</span>
          </label>
        </>
      )}

      <div className="med-schedule-mode" role="radiogroup" aria-label="약 시간 설정 방식">
        <label className="med-schedule-radio">
          <input
            type="radio"
            name="med-mode"
            value="clock"
            checked={form.mode === 'clock'}
            onChange={() => setForm((prev) => ({ ...prev, mode: 'clock' }))}
            disabled={disabled}
          />
          <span>시간 설정</span>
        </label>
        <label className="med-schedule-radio">
          <input
            type="radio"
            name="med-mode"
            value="after_meal"
            checked={form.mode === 'after_meal'}
            onChange={() => setForm((prev) => ({ ...prev, mode: 'after_meal' }))}
            disabled={disabled}
          />
          <span>식후 시간 설정</span>
        </label>
      </div>

      {form.mode === 'clock' ? (
        <div className="med-schedule-fields">
          <span className="med-schedule-label">매일</span>
          <select
            className="med-schedule-select"
            value={form.clock_hour}
            onChange={(e) => setForm((prev) => ({ ...prev, clock_hour: Number(e.target.value) }))}
            disabled={disabled}
            aria-label="시"
          >
            {HOURS.map((h) => (
              <option key={h} value={h}>
                {h}시
              </option>
            ))}
          </select>
          <select
            className="med-schedule-select"
            value={form.clock_minute}
            onChange={(e) => setForm((prev) => ({ ...prev, clock_minute: Number(e.target.value) }))}
            disabled={disabled}
            aria-label="분"
          >
            {MINUTES.map((m) => (
              <option key={m} value={m}>
                {String(m).padStart(2, '0')}분
              </option>
            ))}
          </select>
          <span className="med-schedule-label">에 약 준비</span>
        </div>
      ) : (
        <div className="med-schedule-fields">
          <span className="med-schedule-label">식사 후</span>
          <select
            className="med-schedule-select"
            value={form.after_meal_minutes}
            onChange={(e) =>
              setForm((prev) => ({ ...prev, after_meal_minutes: Number(e.target.value) }))
            }
            disabled={disabled}
            aria-label="식후 분"
          >
            {AFTER_MEAL_OPTIONS.map((m) => (
              <option key={m} value={m}>
                {m}분
              </option>
            ))}
          </select>
          <span className="med-schedule-label">뒤 약 준비</span>
        </div>
      )}

      <div className="med-schedule-form-actions">
        {isEditing && (
          <button
            type="button"
            className="med-schedule-cancel"
            onClick={() => onCancelEdit?.()}
            disabled={disabled || saving}
          >
            취소
          </button>
        )}
        <button
          type="button"
          className="med-schedule-save"
          onClick={handleSave}
          disabled={disabled || saving}
        >
          {saving ? '저장 중…' : isEditing ? '수정 저장' : '약 시간 저장'}
        </button>
      </div>
    </section>
  )
}
