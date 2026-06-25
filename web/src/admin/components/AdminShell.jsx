import { NavLink, Outlet } from 'react-router-dom'

export default function AdminShell({ onLogout, wsConnected }) {
  return (
    <div className="admin-shell">
      <aside className="admin-sidebar">
        <div className="admin-brand">Cobot1 관리자</div>
        <nav className="admin-nav">
          <NavLink to="/admin" end>
            대시보드
          </NavLink>
          <NavLink to="/admin/logs">라이브 로그</NavLink>
          <NavLink to="/admin/runs">동작 이력</NavLink>
          <NavLink to="/admin/safety">안전 관리</NavLink>
          <NavLink to="/admin/audit">감사 로그</NavLink>
        </nav>
        <div className="admin-sidebar-footer">
          <span style={{ padding: '8px 12px', fontSize: '0.8rem', color: wsConnected ? '#86efac' : '#f87171' }}>
            WS {wsConnected ? '연결됨' : '끊김'}
          </span>
          <a href="/">케어 UI</a>
          <button type="button" onClick={onLogout}>
            로그아웃
          </button>
        </div>
      </aside>
      <main className="admin-main">
        <Outlet />
      </main>
    </div>
  )
}
