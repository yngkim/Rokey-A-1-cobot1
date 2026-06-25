import { useEffect, useState } from 'react'
import { fetchAudit, formatTs } from '../../api/adminClient'

export default function AuditLogPage() {
  const [entries, setEntries] = useState([])

  const load = () => {
    fetchAudit({ limit: 100 })
      .then((data) => setEntries(data.entries || []))
      .catch(() => setEntries([]))
  }

  useEffect(() => {
    load()
    const timer = setInterval(load, 5000)
    return () => clearInterval(timer)
  }, [])

  return (
    <>
      <h1 className="admin-page-title">감사 로그</h1>
      <div className="admin-toolbar">
        <button type="button" className="admin-btn" onClick={load}>
          새로고침
        </button>
      </div>
      <div className="admin-table-wrap">
        <table className="admin-table">
          <thead>
            <tr>
              <th>시각</th>
              <th>행위자</th>
              <th>동작</th>
              <th>상세</th>
            </tr>
          </thead>
          <tbody>
            {entries.length === 0 && (
              <tr>
                <td colSpan={4}>기록 없음</td>
              </tr>
            )}
            {entries.map((e) => (
              <tr key={e.id}>
                <td>{formatTs(e.ts)}</td>
                <td>{e.actor}</td>
                <td>{e.action}</td>
                <td className="wrap">{JSON.stringify(e.detail)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}
