import { useEffect } from 'react'
import { Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import AdminLogin from './AdminLogin'
import AdminShell from './components/AdminShell'
import { useAdminSession } from './hooks/useAdminSession'
import { useAdminWs } from './hooks/useAdminWs'
import AuditLogPage from './pages/AuditLog'
import DashboardPage from './pages/Dashboard'
import LiveLogsPage from './pages/LiveLogs'
import RunDetailPage from './pages/RunDetail'
import RunHistoryPage from './pages/RunHistory'
import SafetyCenterPage from './pages/SafetyCenter'
import UserCarePage from './pages/UserCare'
import './admin.css'

function AdminRoutes({ session, ws }) {
  const navigate = useNavigate()

  const handleLogout = async () => {
    await session.logout()
    navigate('/admin/login')
  }

  return (
    <Routes>
      <Route element={<AdminShell onLogout={handleLogout} wsConnected={ws.connected} />}>
        <Route index element={<DashboardPage ws={ws} />} />
        <Route path="logs" element={<LiveLogsPage ws={ws} />} />
        <Route path="runs" element={<RunHistoryPage />} />
        <Route path="runs/:runId" element={<RunDetailPage />} />
        <Route path="safety" element={<SafetyCenterPage ws={ws} />} />
        <Route path="care" element={<UserCarePage />} />
        <Route path="audit" element={<AuditLogPage />} />
      </Route>
    </Routes>
  )
}

export default function AdminApp() {
  const session = useAdminSession()
  const ws = useAdminWs(session.authenticated)

  useEffect(() => {
    document.body.classList.add('admin-mode')
    document.documentElement.classList.add('admin-mode')
    const prevTitle = document.title
    document.title = 'Cobot1 관리자'
    return () => {
      document.body.classList.remove('admin-mode')
      document.documentElement.classList.remove('admin-mode')
      document.title = prevTitle
    }
  }, [])

  if (session.loading) {
    return (
      <div className="admin-root admin-login-wrap">
        <p>로딩 중…</p>
      </div>
    )
  }

  return (
    <div className="admin-root">
      <Routes>
        <Route
          path="login"
          element={
            session.authenticated ? (
              <Navigate to="/admin" replace />
            ) : (
              <AdminLogin onLogin={session.login} error={session.error} />
            )
          }
        />
        <Route
          path="/*"
          element={
            session.authenticated ? (
              <AdminRoutes session={session} ws={ws} />
            ) : (
              <Navigate to="/admin/login" replace />
            )
          }
        />
      </Routes>
    </div>
  )
}
