import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  deleteMedicationSchedule,
  fetchMedicationSchedules,
} from '../api/client'
import MedicationScheduleList from '../components/MedicationScheduleList'
import MedicationSchedulePanel from '../components/MedicationSchedulePanel'

export default function MedicationSchedulePage({
  userId,
  userName,
  busy,
  isTablet,
  onToast,
}) {
  const [schedules, setSchedules] = useState([])
  const [loading, setLoading] = useState(false)
  const [editingItem, setEditingItem] = useState(null)

  const loadSchedules = useCallback(async () => {
    if (!userId) return
    setLoading(true)
    try {
      const data = await fetchMedicationSchedules(userId)
      setSchedules(data.schedules || [])
    } catch (err) {
      onToast?.(err.message, 'error')
    } finally {
      setLoading(false)
    }
  }, [onToast, userId])

  useEffect(() => {
    setEditingItem(null)
    loadSchedules()
  }, [loadSchedules])

  const handleSaved = () => {
    setEditingItem(null)
    loadSchedules()
  }

  const handleEdit = (item) => {
    setEditingItem(item)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const handleDelete = async (item) => {
    if (busy) return
    const ok = window.confirm(`"${item.summary}" 약 시간을 삭제할까요?`)
    if (!ok) return
    try {
      await deleteMedicationSchedule(item.id)
      if (editingItem?.id === item.id) {
        setEditingItem(null)
      }
      onToast?.('약 시간을 삭제했습니다', 'info')
      loadSchedules()
    } catch (err) {
      onToast?.(err.message, 'error')
    }
  }

  return (
    <main className={`app-main app-main-settings ${isTablet ? 'app-main-tablet' : ''}`}>
      <div className="settings-page">
        <Link to="/" className="settings-back">
          ← 메인 화면
        </Link>
        <h1 className="settings-title">약 복용 시간</h1>
        <p className="settings-desc">
          {userName ? `${userName}님의 ` : ''}
          자동 약 준비 시간을 설정합니다.
        </p>
        {userId ? (
          <>
            <MedicationSchedulePanel
              userId={userId}
              disabled={busy}
              page
              editingItem={editingItem}
              onSaved={handleSaved}
              onCancelEdit={() => setEditingItem(null)}
              onToast={onToast}
            />
            <MedicationScheduleList
              schedules={schedules}
              loading={loading}
              disabled={busy}
              editingId={editingItem?.id}
              onEdit={handleEdit}
              onDelete={handleDelete}
            />
          </>
        ) : (
          <p className="settings-empty">사용자를 먼저 선택해 주세요.</p>
        )}
      </div>
    </main>
  )
}
