export const DEFAULT_TASKS = [
  { id: 'prepare_medication', label: '약 준비하기', icon: '💊', group: '복약' },
  { id: 'place_on_charger', label: '핸드폰 가져다놓기', icon: '📲', group: '스마트폰' },
  { id: 'pick_from_charger', label: '핸드폰 가져오기', icon: '🔋', group: '스마트폰' },
  { id: 'go_home', label: '기본 위치 복귀', icon: '🏠', group: '제어' },
]

const API_BASE = import.meta.env.VITE_API_BASE || ''

export async function fetchVoiceCatalog() {
  const res = await fetch(`${API_BASE}/api/voice/catalog`)
  if (!res.ok) throw new Error('음성 설정을 불러오지 못했습니다')
  return res.json()
}

export async function sendVoiceCommand(text) {
  const res = await fetch(`${API_BASE}/api/voice/command`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })
  let data = {}
  try {
    data = await res.json()
  } catch {
    data = {}
  }
  if (!res.ok) {
    if (res.status === 405) {
      throw new Error(
        '음성 API에 연결되지 않았습니다. colcon build 후 ros2 run cobot1 care_web_api 를 재시작하세요.',
      )
    }
    const detail = typeof data.detail === 'string' ? data.detail : data.message
    throw new Error(detail || `음성 명령 실패 (HTTP ${res.status})`)
  }
  return data
}

export async function forceIdle() {
  const res = await fetch(`${API_BASE}/api/force_idle`, { method: 'POST' })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || data.message || '잠금 해제 실패')
  return data
}

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

export async function stopTask() {
  const res = await fetch(`${API_BASE}/api/stop`, { method: 'POST' })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || data.message || '정지 실패')
  return data
}

export async function resetRobot() {
  const res = await fetch(`${API_BASE}/api/reset`, { method: 'POST' })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || data.message || '초기화 실패')
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

  ws.onopen = () => onMessage({ type: 'ws_open' })
  ws.onclose = () => onMessage({ type: 'ws_close' })

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

export function taskLabelById(tasks, taskId) {
  const found = tasks.find((t) => t.id === taskId)
  return found ? found.label : taskId
}
