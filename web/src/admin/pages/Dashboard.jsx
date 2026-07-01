import { useEffect, useState } from 'react'
import { fetchAlerts, fetchDashboard, formatTs } from '../../api/adminClient'
import CameraMonitor from '../components/CameraMonitor'
import ControlPanel from '../components/ControlPanel'
import StatusBadge from '../components/StatusBadge'

export default function DashboardPage({ ws }) {
  const [dash, setDash] = useState(null)
  const [recentAlerts, setRecentAlerts] = useState([])

  const refresh = async () => {
    try {
      const [d, alerts] = await Promise.all([
        fetchDashboard(),
        fetchAlerts({ limit: 3 }),
      ])
      setDash(d)
      setRecentAlerts(alerts.alerts || [])
    } catch {
      /* ignore */
    }
  }

  useEffect(() => {
    refresh()
    const timer = setInterval(refresh, 3000)
    return () => clearInterval(timer)
  }, [])

  const robotLabel = ws.robotState?.label || dash?.robot_state_label || '-'
  const maintenance = ws.maintenance || dash?.maintenance

  return (
    <>
      <h1 className="admin-page-title">대시보드</h1>

      {(ws.alert || dash?.last_alert) && (
        <div className="admin-alert-banner">
          {(ws.alert || dash.last_alert).message || (ws.alert || dash.last_alert).code}
        </div>
      )}

      <div className="admin-dashboard-top">
        <div className="admin-dashboard-status">
          <div className="admin-status-grid">
            <div className="admin-card">
              <div className="admin-card-label">API</div>
              <div className="admin-card-value">
                <StatusBadge kind={dash?.api_ok ? 'on' : 'danger'}>
                  {dash?.api_ok ? '정상' : '오프라인'}
                </StatusBadge>
              </div>
            </div>
            <div className="admin-card">
              <div className="admin-card-label">로봇</div>
              <div className="admin-card-value">
                <StatusBadge kind={dash?.robot_ready ? 'on' : 'warn'}>
                  {dash?.robot_ready ? 'Ready' : '대기'}
                </StatusBadge>
              </div>
            </div>
            <div className="admin-card">
              <div className="admin-card-label">로봇 상태</div>
              <div className="admin-card-value">
                <StatusBadge kind={['SAFE_STOP', 'EMERGENCY_STOP', 'SAFE_STOP2'].includes(robotLabel) ? 'danger' : 'info'}>
                  {robotLabel}
                </StatusBadge>
              </div>
            </div>
            <div className="admin-card">
              <div className="admin-card-label">실행 중</div>
              <div className="admin-card-value">
                <StatusBadge kind={dash?.busy ? 'warn' : 'off'}>
                  {dash?.busy ? dash.current_task_label || dash.current_task : '유휴'}
                </StatusBadge>
              </div>
            </div>
            <div className="admin-card">
              <div className="admin-card-label">현재 단계</div>
              <div className="admin-card-value admin-card-value--text">
                {ws.status?.step || dash?.current_step || '-'}
              </div>
            </div>
            <div className="admin-card">
              <div className="admin-card-label">유지보수</div>
              <div className="admin-card-value">
                <StatusBadge kind={maintenance ? 'warn' : 'off'}>
                  {maintenance ? 'ON' : 'OFF'}
                </StatusBadge>
              </div>
            </div>
          </div>
        </div>
        <CameraMonitor className="admin-dashboard-camera" />
      </div>

      <ControlPanel maintenance={maintenance} onChanged={refresh} />

      <div className="admin-panel">
        <h3>실시간 단계 타임라인</h3>
        <div className="admin-timeline">
          {ws.timeline.length === 0 && <div>아직 이벤트 없음</div>}
          {ws.timeline
            .slice()
            .reverse()
            .map((item, idx) => (
              <div key={`${item.timestamp}-${idx}`} className="admin-timeline-item">
                <span style={{ color: '#8fa0b8', minWidth: 140 }}>{formatTs(item.timestamp)}</span>
                <strong>{item.task}</strong>
                <span>{item.step}</span>
                <StatusBadge kind={item.state === 'error' ? 'danger' : item.state === 'running' ? 'info' : 'off'}>
                  {item.state}
                </StatusBadge>
              </div>
            ))}
        </div>
      </div>

      <div className="admin-panel">
        <h3>최근 안전 알람</h3>
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th>시각</th>
                <th>코드</th>
                <th>메시지</th>
              </tr>
            </thead>
            <tbody>
              {recentAlerts.length === 0 && (
                <tr>
                  <td colSpan={3}>알람 없음</td>
                </tr>
              )}
              {recentAlerts.map((a) => (
                <tr key={a.id}>
                  <td>{formatTs(a.ts)}</td>
                  <td>{a.code}</td>
                  <td>{a.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}
