import { useCallback, useEffect, useState } from 'react'
import {
  createCareEvent,
  createCareUser,
  fetchCareDaily,
  fetchCareOverview,
  fetchCareUsers,
  formatTs,
} from '../../api/adminClient'
import StatusBadge from '../components/StatusBadge'

function todayStr() {
  return new Date().toISOString().slice(0, 10)
}

function ProgressCard({ title, count, target, percent, unit, note }) {
  const kind = percent >= 100 ? 'on' : percent >= 50 ? 'warn' : 'danger'
  return (
    <div className="admin-card admin-care-card">
      <div className="admin-card-label">{title}</div>
      <div className="admin-care-metric">
        <span className="admin-care-count">
          {count}
          <small> / {target}{unit}</small>
        </span>
        <StatusBadge kind={kind}>{Math.round(percent)}%</StatusBadge>
      </div>
      {note && <p className="admin-care-note">{note}</p>}
    </div>
  )
}

export default function UserCarePage() {
  const [date, setDate] = useState(todayStr())
  const [users, setUsers] = useState([])
  const [selectedUserId, setSelectedUserId] = useState('')
  const [summary, setSummary] = useState(null)
  const [overview, setOverview] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [newUserId, setNewUserId] = useState('')
  const [newUserName, setNewUserName] = useState('')
  const [eventType, setEventType] = useState('medication_taken')
  const [eventQty, setEventQty] = useState('1')
  const [eventNote, setEventNote] = useState('')

  const loadUsers = useCallback(async () => {
    const data = await fetchCareUsers()
    const list = data.users || []
    setUsers(list)
    if (!selectedUserId && list.length > 0) {
      setSelectedUserId(list[0].id)
    }
  }, [selectedUserId])

  const refresh = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      await loadUsers()
      const ov = await fetchCareOverview(date)
      setOverview(ov.users || [])
      if (selectedUserId) {
        const daily = await fetchCareDaily(selectedUserId, date)
        setSummary(daily)
      } else {
        setSummary(null)
      }
    } catch (err) {
      setError(err.message || '데이터를 불러오지 못했습니다')
    } finally {
      setLoading(false)
    }
  }, [date, loadUsers, selectedUserId])

  useEffect(() => {
    refresh()
  }, [refresh])

  const handleAddUser = async (e) => {
    e.preventDefault()
    if (!newUserId.trim() || !newUserName.trim()) return
    try {
      await createCareUser(newUserId.trim(), newUserName.trim())
      setNewUserId('')
      setNewUserName('')
      await refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  const handleAddEvent = async (e) => {
    e.preventDefault()
    if (!selectedUserId) return
    try {
      await createCareEvent({
        user_id: selectedUserId,
        event_type: eventType,
        quantity: parseFloat(eventQty) || 1,
        unit: eventType === 'meal' ? 'serving' : 'dose',
        note: eventNote.trim() || null,
        date,
      })
      setEventNote('')
      await refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <>
      <h1 className="admin-page-title">사용자 케어 모니터링</h1>
      <p className="admin-page-desc">
        일별 약 준비·복용·식사 기록을 확인합니다. 로봇 약 준비 완료는 자동 기록됩니다.
      </p>

      {error && <div className="admin-alert-banner">{error}</div>}

      <div className="admin-toolbar">
        <label>
          날짜
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        <label>
          사용자
          <select value={selectedUserId} onChange={(e) => setSelectedUserId(e.target.value)}>
            {users.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name} ({u.id})
              </option>
            ))}
          </select>
        </label>
        <button type="button" className="admin-btn" onClick={refresh} disabled={loading}>
          {loading ? '새로고침…' : '새로고침'}
        </button>
      </div>

      {summary && (
        <div className="admin-grid admin-care-grid">
          <ProgressCard
            title="약 준비 (로봇)"
            count={summary.medication_prepare.count}
            target={summary.medication_prepare.target}
            percent={summary.medication_prepare.percent}
            unit="회"
          />
          <ProgressCard
            title="복용 완료"
            count={summary.medication_taken.count}
            target={summary.medication_taken.target}
            percent={summary.medication_taken.percent}
            unit="회"
          />
          <ProgressCard
            title="식사"
            count={summary.meals.count}
            target={summary.meals.target}
            percent={summary.meals.percent}
            unit="회"
            note={summary.meals.note}
          />
        </div>
      )}

      <section className="admin-section">
        <h2>전체 사용자 요약 ({date})</h2>
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th>사용자</th>
                <th>약 준비</th>
                <th>복용</th>
                <th>식사</th>
              </tr>
            </thead>
            <tbody>
              {overview.map((row) => (
                <tr key={row.user.id}>
                  <td>{row.user.name}</td>
                  <td>
                    {row.medication_prepare.count}/{row.medication_prepare.target}
                  </td>
                  <td>
                    {row.medication_taken.count}/{row.medication_taken.target}
                  </td>
                  <td>
                    {row.meals.count}/{row.meals.target}
                  </td>
                </tr>
              ))}
              {overview.length === 0 && (
                <tr>
                  <td colSpan={4}>등록된 사용자가 없습니다</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {summary && (
        <section className="admin-section">
          <h2>상세 이벤트 — {summary.user.name}</h2>
          <div className="admin-table-wrap">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>시간</th>
                  <th>유형</th>
                  <th>수량</th>
                  <th>출처</th>
                  <th>메모</th>
                </tr>
              </thead>
              <tbody>
                {(summary.events || []).map((ev) => (
                  <tr key={ev.id}>
                    <td>{formatTs(ev.ts)}</td>
                    <td>{ev.event_type_label}</td>
                    <td>
                      {ev.quantity} {ev.unit}
                    </td>
                    <td>{ev.source}</td>
                    <td>{ev.note || '-'}</td>
                  </tr>
                ))}
                {(summary.events || []).length === 0 && (
                  <tr>
                    <td colSpan={5}>기록이 없습니다</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <div className="admin-grid admin-care-forms">
        <section className="admin-card">
          <h2 className="admin-card-title">기록 추가 (관리자)</h2>
          <form onSubmit={handleAddEvent} className="admin-form">
            <label>
              유형
              <select value={eventType} onChange={(e) => setEventType(e.target.value)}>
                <option value="medication_taken">복용 완료</option>
                <option value="meal">식사</option>
                <option value="medication_prepare">약 준비</option>
              </select>
            </label>
            <label>
              수량
              <input
                type="number"
                min="0.1"
                step="0.1"
                value={eventQty}
                onChange={(e) => setEventQty(e.target.value)}
              />
            </label>
            <label>
              메모
              <input
                type="text"
                value={eventNote}
                onChange={(e) => setEventNote(e.target.value)}
                placeholder="선택 입력"
              />
            </label>
            <button type="submit" className="admin-btn primary">
              기록 저장
            </button>
          </form>
        </section>

        <section className="admin-card">
          <h2 className="admin-card-title">사용자 등록</h2>
          <form onSubmit={handleAddUser} className="admin-form">
            <label>
              ID
              <input
                type="text"
                value={newUserId}
                onChange={(e) => setNewUserId(e.target.value)}
                placeholder="patient_03"
              />
            </label>
            <label>
              이름
              <input
                type="text"
                value={newUserName}
                onChange={(e) => setNewUserName(e.target.value)}
                placeholder="홍길동"
              />
            </label>
            <button type="submit" className="admin-btn primary">
              사용자 추가
            </button>
          </form>
        </section>
      </div>
    </>
  )
}
