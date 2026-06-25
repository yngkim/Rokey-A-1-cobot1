import { useEffect, useState } from 'react'
import { fetchLogs } from '../../api/adminClient'
import LogStream from '../components/LogStream'

export default function LiveLogsPage({ ws }) {
  const [filter, setFilter] = useState('all')
  const [paused, setPaused] = useState(false)
  const [historical, setHistorical] = useState([])

  useEffect(() => {
    fetchLogs({ limit: 100 })
      .then((data) => {
        const rows = (data.logs || []).map((row, idx) => ({
          id: `db-${idx}-${row.ts}`,
          type: row.type,
          ts: row.ts,
          text:
            row.type === 'audit'
              ? `[${row.actor}] ${row.action}`
              : row.type === 'safety'
                ? `[안전] ${row.code} ${row.message}`
                : `[${row.task}] ${row.step} (${row.state}) ${row.message || ''}`.trim(),
        }))
        setHistorical(rows)
      })
      .catch(() => {})
  }, [])

  const merged = [...ws.liveLogs, ...historical.filter((h) => !ws.liveLogs.some((l) => l.id === h.id))]

  return (
    <>
      <h1 className="admin-page-title">라이브 로그</h1>
      <div className="admin-toolbar">
        <select value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="all">전체</option>
          <option value="status">상태</option>
          <option value="safety">안전</option>
          <option value="audit">시스템</option>
        </select>
        <button type="button" className="admin-btn" onClick={() => setPaused((v) => !v)}>
          {paused ? '자동 스크롤 재개' : '일시정지'}
        </button>
        <button type="button" className="admin-btn" onClick={ws.clearLogs}>
          라이브 버퍼 비우기
        </button>
      </div>
      <LogStream logs={merged} paused={paused} filter={filter} />
    </>
  )
}
