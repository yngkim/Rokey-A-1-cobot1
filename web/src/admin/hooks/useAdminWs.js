import { useCallback, useEffect, useRef, useState } from 'react'
import { connectAdminWebSocket } from '../../api/adminClient'

const MAX_BUFFER = 500

export function useAdminWs(enabled = true) {
  const [connected, setConnected] = useState(false)
  const [status, setStatus] = useState(null)
  const [alert, setAlert] = useState(null)
  const [robotState, setRobotState] = useState(null)
  const [maintenance, setMaintenance] = useState(false)
  const [timeline, setTimeline] = useState([])
  const [liveLogs, setLiveLogs] = useState([])
  const wsRef = useRef(null)

  const pushLog = useCallback((entry) => {
    setLiveLogs((prev) => [entry, ...prev].slice(0, MAX_BUFFER))
  }, [])

  const pushTimeline = useCallback((entry) => {
    setTimeline((prev) => [...prev, entry].slice(-80))
  }, [])

  useEffect(() => {
    if (!enabled) return undefined

    const ws = connectAdminWebSocket((msg) => {
      if (msg.type === 'ws_open') {
        setConnected(true)
        return
      }
      if (msg.type === 'ws_close') {
        setConnected(false)
        return
      }
      if (msg.type === 'sync') {
        if (msg.data?.last_status) setStatus(msg.data.last_status)
        return
      }
      if (msg.type === 'status') {
        setStatus(msg.data)
        pushTimeline(msg.data)
        pushLog({
          id: `${msg.data.timestamp || Date.now()}-status`,
          type: 'status',
          ts: msg.data.timestamp || Date.now() / 1000,
          text: `[${msg.data.task}] ${msg.data.step} (${msg.data.state}) ${msg.data.message || ''}`.trim(),
          data: msg.data,
        })
        return
      }
      if (msg.type === 'safety_alert') {
        setAlert(msg.data)
        pushLog({
          id: `${msg.data.timestamp || Date.now()}-safety`,
          type: 'safety',
          ts: msg.data.timestamp || Date.now() / 1000,
          text: `[안전] ${msg.data.code || ''} ${msg.data.message || ''}`.trim(),
          data: msg.data,
        })
        return
      }
      if (msg.type === 'robot_state') {
        setRobotState(msg.data)
        return
      }
      if (msg.type === 'maintenance') {
        setMaintenance(Boolean(msg.data?.enabled))
        pushLog({
          id: `${Date.now()}-maintenance`,
          type: 'audit',
          ts: Date.now() / 1000,
          text: `유지보수 모드 ${msg.data?.enabled ? 'ON' : 'OFF'}`,
          data: msg.data,
        })
        return
      }
      if (msg.type === 'audit') {
        pushLog({
          id: `${msg.data.timestamp || Date.now()}-audit`,
          type: 'audit',
          ts: msg.data.timestamp || Date.now() / 1000,
          text: `[${msg.data.actor}] ${msg.data.action}`,
          data: msg.data,
        })
        return
      }
      if (msg.type === 'task_complete') {
        pushLog({
          id: `${Date.now()}-task`,
          type: 'status',
          ts: Date.now() / 1000,
          text: `태스크 완료: ${msg.data.task} success=${msg.data.success}`,
          data: msg.data,
        })
      }
    })

    wsRef.current = ws
    return () => ws.close()
  }, [enabled, pushLog, pushTimeline])

  return {
    connected,
    status,
    alert,
    robotState,
    maintenance,
    timeline,
    liveLogs,
    clearLogs: () => setLiveLogs([]),
    clearTimeline: () => setTimeline([]),
  }
}
