import { useEffect, useState } from 'react'
import { fetchAlerts, fetchSafetyConfig, formatTs } from '../../api/adminClient'
import ControlPanel from '../components/ControlPanel'

export default function SafetyCenterPage({ ws }) {
  const [config, setConfig] = useState(null)
  const [alerts, setAlerts] = useState([])
  const [maintenance, setMaintenance] = useState(false)

  const refresh = async () => {
    try {
      const [cfg, alertData, dashMod] = await Promise.all([
        fetchSafetyConfig(),
        fetchAlerts({ limit: 50 }),
        import('../../api/adminClient').then((m) => m.fetchDashboard()),
      ])
      setConfig(cfg.safety || {})
      setAlerts(alertData.alerts || [])
      setMaintenance(Boolean(dashMod.maintenance || ws.maintenance))
    } catch {
      /* ignore */
    }
  }

  useEffect(() => {
    refresh()
    const timer = setInterval(refresh, 5000)
    return () => clearInterval(timer)
  }, [ws.maintenance])

  return (
    <>
      <h1 className="admin-page-title">안전 관리</h1>

      <div className="admin-panel">
        <h3>현재 안전 설정 (읽기 전용)</h3>
        {config ? (
          <ul style={{ margin: 0, paddingLeft: 18, lineHeight: 1.8 }}>
            <li>활성화: {String(config.enabled)}</li>
            <li>외력 임계 (norm): {config.external_torque_max_norm}</li>
            <li>모니터 주기 (초): {config.monitor_interval_sec}</li>
          </ul>
        ) : (
          <p>설정 불러오는 중…</p>
        )}
      </div>

      <ControlPanel maintenance={maintenance} onChanged={refresh} />

      <div className="admin-panel">
        <h3>안전 알람 이력</h3>
        <div className="admin-table-wrap">
          <table className="admin-table">
            <thead>
              <tr>
                <th>시각</th>
                <th>코드</th>
                <th>레벨</th>
                <th>태스크</th>
                <th>메시지</th>
              </tr>
            </thead>
            <tbody>
              {alerts.length === 0 && (
                <tr>
                  <td colSpan={5}>알람 없음</td>
                </tr>
              )}
              {alerts.map((a) => (
                <tr key={a.id}>
                  <td>{formatTs(a.ts)}</td>
                  <td>{a.code}</td>
                  <td>{a.level}</td>
                  <td>{a.task}</td>
                  <td className="wrap">{a.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  )
}
