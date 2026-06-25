const API_BASE = import.meta.env.VITE_API_BASE || ''

async function adminFetch(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: 'include',
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
  })
  let data = {}
  try {
    data = await res.json()
  } catch {
    data = {}
  }
  if (!res.ok) {
    const detail = typeof data.detail === 'string' ? data.detail : data.message
    const err = new Error(detail || `요청 실패 (HTTP ${res.status})`)
    err.status = res.status
    throw err
  }
  return data
}

export async function adminLogin(password) {
  return adminFetch('/api/admin/login', {
    method: 'POST',
    body: JSON.stringify({ password }),
  })
}

export async function adminLogout() {
  return adminFetch('/api/admin/logout', { method: 'POST' })
}

export async function adminSession() {
  return adminFetch('/api/admin/session')
}

export async function fetchDashboard() {
  return adminFetch('/api/admin/dashboard')
}

export async function fetchRuns({ limit = 50, offset = 0, task = '' } = {}) {
  const params = new URLSearchParams({ limit, offset })
  if (task) params.set('task', task)
  return adminFetch(`/api/admin/runs?${params}`)
}

export async function fetchRunDetail(runId) {
  return adminFetch(`/api/admin/runs/${runId}`)
}

export async function fetchAlerts({ limit = 50, offset = 0 } = {}) {
  const params = new URLSearchParams({ limit, offset })
  return adminFetch(`/api/admin/alerts?${params}`)
}

export async function fetchAudit({ limit = 50, offset = 0 } = {}) {
  const params = new URLSearchParams({ limit, offset })
  return adminFetch(`/api/admin/audit?${params}`)
}

export async function fetchLogs({ limit = 100, offset = 0, type = '' } = {}) {
  const params = new URLSearchParams({ limit, offset })
  if (type) params.set('type', type)
  return adminFetch(`/api/admin/logs?${params}`)
}

export async function fetchSafetyConfig() {
  return adminFetch('/api/admin/safety/config')
}

export async function setMaintenance(enabled) {
  return adminFetch('/api/admin/maintenance', {
    method: 'POST',
    body: JSON.stringify({ enabled }),
  })
}

export async function adminStop() {
  return adminFetch('/api/admin/stop', { method: 'POST' })
}

export async function adminReset() {
  return adminFetch('/api/admin/reset', { method: 'POST' })
}

export async function adminForceIdle() {
  return adminFetch('/api/admin/force_idle', { method: 'POST' })
}

export function connectAdminWebSocket(onMessage) {
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
  ws.onerror = () => onMessage({ type: 'error' })

  return ws
}

export function formatTs(ts) {
  if (!ts) return '-'
  return new Date(ts * 1000).toLocaleString('ko-KR')
}

export function formatDuration(sec) {
  if (sec == null) return '-'
  if (sec < 60) return `${sec.toFixed(1)}초`
  const m = Math.floor(sec / 60)
  const s = Math.round(sec % 60)
  return `${m}분 ${s}초`
}
