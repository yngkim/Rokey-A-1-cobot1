import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { fetchRunDetail, formatTs } from '../../api/adminClient'
import StatusBadge from '../components/StatusBadge'

export default function RunDetailPage() {
  const { runId } = useParams()
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    fetchRunDetail(runId)
      .then(setData)
      .catch((err) => setError(err.message || '불러오기 실패'))
  }, [runId])

  if (error) return <p>{error}</p>
  if (!data) return <p>로딩 중…</p>

  const { run, events } = data

  return (
    <>
      <p>
        <Link to="/admin/runs">← 동작 이력</Link>
      </p>
      <h1 className="admin-page-title">{run.task_id} 실행 상세</h1>
      <div className="admin-grid">
        <div className="admin-card">
          <div className="admin-card-label">시작</div>
          <div className="admin-card-value" style={{ fontSize: '0.9rem' }}>
            {formatTs(run.started_at)}
          </div>
        </div>
        <div className="admin-card">
          <div className="admin-card-label">트리거</div>
          <div className="admin-card-value">{run.trigger}</div>
        </div>
        <div className="admin-card">
          <div className="admin-card-label">결과</div>
          <div className="admin-card-value">
            {run.success == null ? (
              <StatusBadge kind="warn">진행중</StatusBadge>
            ) : run.success ? (
              <StatusBadge kind="on">성공</StatusBadge>
            ) : (
              <StatusBadge kind="danger">실패</StatusBadge>
            )}
          </div>
        </div>
      </div>

      <div className="admin-panel">
        <h3>단계 타임라인</h3>
        <div className="admin-timeline">
          {events.length === 0 && <div>단계 기록 없음</div>}
          {events.map((ev) => (
            <div key={ev.id} className="admin-timeline-item">
              <span style={{ color: '#8fa0b8', minWidth: 140 }}>{formatTs(ev.ts)}</span>
              <strong>{ev.step}</strong>
              <StatusBadge kind={ev.state === 'error' ? 'danger' : ev.state === 'running' ? 'info' : 'off'}>
                {ev.state}
              </StatusBadge>
              <span style={{ color: '#9aa8bc' }}>{ev.message}</span>
            </div>
          ))}
        </div>
      </div>
    </>
  )
}
