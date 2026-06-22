import { useCallback, useEffect, useRef, useState } from 'react'
import {
  DEFAULT_TASKS,
  checkHealth,
  connectWebSocket,
  stopTask,
  taskLabelById,
} from '../api/client'

export function useRobotApp() {
  const [tasks] = useState(DEFAULT_TASKS)
  const [apiOnline, setApiOnline] = useState(false)
  const [robotReady, setRobotReady] = useState(false)
  const [busy, setBusy] = useState(false)
  const [stopping, setStopping] = useState(false)
  const [activeTaskId, setActiveTaskId] = useState('')
  const [status, setStatus] = useState(null)
  const [alert, setAlert] = useState(null)
  const [toast, setToast] = useState(null)
  const wsRef = useRef(null)

  const showSafetyAlert = useCallback((data) => {
    setAlert({
      code: data?.code || '',
      message: data?.message || data?.user_message || '안전 경고가 발생했습니다.',
      task: data?.task || '',
      detail: data?.detail || null,
      timestamp: data?.timestamp || Date.now(),
    })
    setBusy(false)
    setStopping(false)
    setActiveTaskId('')
  }, [])

  const showToast = useCallback((message, level = 'info') => {
    setToast({ message, level, id: Date.now() })
    setTimeout(() => setToast(null), 4000)
  }, [])

  const refreshHealth = useCallback(() => {
    return checkHealth()
      .then((h) => {
        setApiOnline(!!h.api_ok)
        setRobotReady(!!h.robot_ready)
        setBusy(!!h.busy)
        if (h.current_task) setActiveTaskId(h.current_task)
        return h
      })
      .catch(() => {
        setApiOnline(false)
        setRobotReady(false)
        return null
      })
  }, [])

  const handleStop = useCallback(async () => {
    if (stopping) return
    setStopping(true)
    try {
      const result = await stopTask()
      showToast(result.message || '정지 요청을 보냈습니다', 'info')
    } catch (err) {
      showToast(err.message, 'error')
      setStopping(false)
    }
  }, [showToast, stopping])

  useEffect(() => {
    refreshHealth()

    const ws = connectWebSocket((msg) => {
      if (msg.type === 'status') {
        setStatus(msg.data)
        const state = msg.data?.state
        const step = msg.data?.step
        if (msg.data?.task) setActiveTaskId(msg.data.task)

        if (state === 'running') {
          setBusy(true)
          setStopping(false)
        }
        if (step === 'finish' && state === 'done') {
          setBusy(false)
          setStopping(false)
          setActiveTaskId('')
        }
        if (state === 'error' || state === 'stopped') {
          setBusy(false)
          setStopping(false)
          setActiveTaskId('')
        }
        if (state === 'stopping') setStopping(true)

        if (state === 'done' && step !== 'finish') {
          showToast(`${step} 완료`)
        }
        if (state === 'error') showToast(msg.data.message || '오류 발생', 'error')
        if (state === 'stopped') showToast(msg.data.message || '작업이 중단되었습니다', 'info')

        if (
          msg.data?.code === 'EXTERNAL_FORCE' ||
          msg.data?.step === 'safety_abort'
        ) {
          showSafetyAlert(msg.data)
        }
      }
      if (msg.type === 'safety_alert') {
        showSafetyAlert(msg.data)
      }
    })
    wsRef.current = ws

    const healthTimer = setInterval(refreshHealth, 3000)

    return () => {
      clearInterval(healthTimer)
      ws.close()
    }
  }, [refreshHealth, showSafetyAlert, showToast])

  const activeTaskLabel = taskLabelById(tasks, activeTaskId)

  return {
    tasks,
    apiOnline,
    robotReady,
    busy,
    stopping,
    activeTaskId,
    activeTaskLabel,
    status,
    alert,
    toast,
    showToast,
    refreshHealth,
    handleStop,
    clearAlert: () => setAlert(null),
  }
}
