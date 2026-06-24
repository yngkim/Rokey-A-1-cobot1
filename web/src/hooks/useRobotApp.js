
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  DEFAULT_TASKS,
  checkHealth,
  connectWebSocket,
  fetchTasks,
  resetRobot,
  stopTask,
  taskLabelById,
} from '../api/client'

function isTerminalStatus(data) {
  const state = data?.state
  const step = data?.step
  if (step === 'finish' && state === 'done') return true
  if (state === 'error' || state === 'stopped') return true
  if (step === 'safe_abort' && ['error', 'recovered', 'critical'].includes(state)) {
    return true
  }
  return false
}

export function useRobotApp() {
  const [tasks, setTasks] = useState(DEFAULT_TASKS)
  const [apiOnline, setApiOnline] = useState(false)
  const [robotReady, setRobotReady] = useState(false)
  const [busy, setBusy] = useState(false)
  const [stopping, setStopping] = useState(false)
  const [resetting, setResetting] = useState(false)
  const [activeTaskId, setActiveTaskId] = useState('')
  const [status, setStatus] = useState(null)
  const [alert, setAlert] = useState(null)
  const [toast, setToast] = useState(null)
  const wsRef = useRef(null)

  const clearBusy = useCallback(() => {
    setBusy(false)
    setStopping(false)
    setResetting(false)
    setActiveTaskId('')
  }, [])

  const showSafetyAlert = useCallback((data) => {
    setAlert({
      code: data?.code || '',
      message: data?.message || data?.user_message || '안전 경고가 발생했습니다.',
      task: data?.task || '',
      detail: data?.detail || null,
      timestamp: data?.timestamp || Date.now(),
    })
    clearBusy()
  }, [clearBusy])

  const showToast = useCallback((message, level = 'info') => {
    setToast({ message, level, id: Date.now() })
    setTimeout(() => setToast(null), 4000)
  }, [])

  const applySync = useCallback((data) => {
    if (!data) return
    setBusy(!!data.busy)
    setActiveTaskId(data.current_task || '')
    if (data.last_status) setStatus(data.last_status)
    if (!data.busy) setStopping(false)
  }, [])

  const refreshHealth = useCallback(() => {
    return checkHealth()
      .then((h) => {
        setApiOnline(!!h.api_ok)
        setRobotReady(!!h.robot_ready)
        setBusy(!!h.busy)
        setActiveTaskId(h.current_task || '')
        if (!h.busy) setStopping(false)
        return h
      })
      .catch(() => {
        setApiOnline(false)
        setRobotReady(false)
        return null
      })
  }, [])

  useEffect(() => {
    fetchTasks()
      .then((data) => {
        if (Array.isArray(data?.tasks) && data.tasks.length > 0) {
          setTasks(data.tasks)
        }
      })
      .catch(() => {})
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

  const handleReset = useCallback(async () => {
    if (resetting) return
    setResetting(true)
    try {
      const result = await resetRobot()
      showToast(result.message || 'SAFE_STOP 해제 후 홈 복귀 중...', 'info')
      setBusy(true)
      setActiveTaskId('go_home')
    } catch (err) {
      showToast(err.message || '초기화 실패', 'error')
      setResetting(false)
    }
  }, [resetting, showToast])

  useEffect(() => {
    refreshHealth()

    const ws = connectWebSocket((msg) => {
      if (msg.type === 'sync') {
        applySync(msg.data)
        return
      }

      if (msg.type === 'task_complete') {
        clearBusy()
        if (msg.data?.success) {
          showToast('작업이 완료되었습니다')
        }
        return
      }

      if (msg.type === 'status') {
        setStatus(msg.data)
        const state = msg.data?.state
        const step = msg.data?.step
        if (msg.data?.task) setActiveTaskId(msg.data.task)

        if (state === 'running') {
          setBusy(true)
          setStopping(false)
        }

        if (isTerminalStatus(msg.data)) {
          clearBusy()
          if (step === 'finish' && state === 'done') {
            showToast('작업이 완료되었습니다')
          }
          if (state === 'error') {
            showToast(msg.data.message || '오류 발생', 'error')
          }
          if (state === 'stopped') {
            showToast(msg.data.message || '작업이 중단되었습니다', 'info')
          }
          return
        }

        if (state === 'stopping') setStopping(true)

        if (state === 'done' && step !== 'finish') {
          showToast(`${step} 완료`)
        }

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

    const healthTimer = setInterval(refreshHealth, 2000)

    return () => {
      clearInterval(healthTimer)
      ws.close()
    }
  }, [applySync, clearBusy, refreshHealth, showSafetyAlert, showToast])

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
    handleReset,
    resetting,
    clearAlert: () => setAlert(null),
    markTaskStarted: (taskId) => {
      setBusy(true)
      setActiveTaskId(taskId)
      setStopping(false)
    },
  }
}
