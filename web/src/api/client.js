const API_BASE = import.meta.env.VITE_API_BASE || ''

export async function fetchTasks() {
  const res = await fetch(`${API_BASE}/api/tasks`)
  if (!res.ok) throw new Error('작업 목록을 불러오지 못했습니다')
  return res.json()
}

export async function runTask(taskId) {
  const res = await fetch(`${API_BASE}/api/tasks/${taskId}`, { method: 'POST' })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || data.message || '실행 실패')
  return data
}

export async function checkHealth() {
  const res = await fetch(`${API_BASE}/api/health`)
  if (!res.ok) throw new Error('서버 연결 실패')
  return res.json()
}

export function connectWebSocket(onMessage) {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const host = import.meta.env.VITE_WS_HOST || window.location.host
  const ws = new WebSocket(`${proto}://${host}/ws`)

  ws.onmessage = (event) => {
    try {
      onMessage(JSON.parse(event.data))
    } catch {
      onMessage({ type: 'raw', data: event.data })
    }
  }

  ws.onerror = () => onMessage({ type: 'error', data: { message: 'WebSocket 오류' } })

  return ws
}
