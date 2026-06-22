import { useCallback, useEffect, useRef, useState } from 'react'
import { checkHealth, connectWebSocket, fetchTasks } from '../api/client'

export function useRobotApp() {
  const [tasks, setTasks] = useState([])
  const [connected, setConnected] = useState(false)
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState(null)
  const [alert, setAlert] = useState(null)
  const [toast, setToast] = useState(null)
  const wsRef = useRef(null)

  const showToast = useCallback((message, level = 'info') => {
    setToast({ message, level, id: Date.now() })
    setTimeout(() => setToast(null), 4000)
  }, [])

  useEffect(() => {
    fetchTasks()
      .then((data) => setTasks(data.tasks || []))
      .catch((err) => showToast(err.message, 'error'))

    checkHealth()
      .then(() => setConnected(true))
      .catch(() => setConnected(false))

    const ws = connectWebSocket((msg) => {
      if (msg.type === 'status') {
        setStatus(msg.data)
        if (msg.data?.state === 'done') showToast(`${msg.data.step} 완료`)
        if (msg.data?.state === 'error') showToast(msg.data.message || '오류 발생', 'error')
      }
      if (msg.type === 'safety_alert') {
        setAlert(msg.data)
        showToast(msg.data?.message || '안전 경고', 'error')
      }
    })
    wsRef.current = ws

    const healthTimer = setInterval(() => {
      checkHealth()
        .then((h) => {
          setConnected(true)
          setBusy(!!h.busy)
        })
        .catch(() => setConnected(false))
    }, 5000)

    return () => {
      clearInterval(healthTimer)
      ws.close()
    }
  }, [showToast])

  return {
    tasks,
    connected,
    busy,
    status,
    alert,
    toast,
    showToast,
    clearAlert: () => setAlert(null),
  }
}
