import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchRuns, formatDuration, formatTs } from '../../api/adminClient'
import StatusBadge from '../components/StatusBadge'

export default function RunHistoryPage() {
  const [runs, setRuns] = useState([])
  const [taskFilter, setTaskFilter] = useState('')

  const load = () => {
    fetchRuns({ limit: 100, task: taskFilter })
      .then((data) => setRuns(data.runs || []))
      .catch(() => setRuns([]))
  }

  useEffect(() => {
    load()
    const timer = setInterval(load, 5000)
    return () => clearInterval(timer)
  }, [taskFilter])

  return (
    <>
      <h1 className="admin-page-title">동작 이력</h1>
      <div className="admin-toolbar">
        <input
          placeholder="태스크 ID 필터"
          value={taskFilter}
          onChange={(e) => setTaskFilter(e.target.value)}
        />
        <button type="button" className="admin-btn" onClick={load}>
          새로고침
        </button>
      </div>
      <div className="admin-table-wrap">
        <table className="admin-table">
          <thead>
            <tr>
              <th>시작</th>
              <th>태스크</th>
              <th>트리거</th>
              <th>소요</th>
              <th>결과</th>
              <th>상세</th>
            </tr>
          </thead>
          <tbody>
            {runs.length === 0 && (
              <tr>
                <td colSpan={6}>기록 없음</td>
              </tr>
            )}
            {runs.map((run) => (
              <tr key={run.id}>
                <td>{formatTs(run.started_at)}</td>
                <td>{run.task_id}</td>
                <td>{run.trigger}</td>
                <td>{formatDuration(run.duration_sec)}</td>
                <td>
                  {run.success == null ? (
                    <StatusBadge kind="warn">진행중</StatusBadge>
                  ) : run.success ? (
                    <StatusBadge kind="on">성공</StatusBadge>
                  ) : (
                    <StatusBadge kind="danger">실패</StatusBadge>
                  )}
                </td>
                <td>
                  <Link to={`/admin/runs/${run.id}`}>보기</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}
