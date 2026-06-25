import { useState } from 'react'

export default function AdminLogin({ onLogin, error }) {
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setSubmitting(true)
    await onLogin(password)
    setSubmitting(false)
  }

  return (
    <div className="admin-login-wrap">
      <form className="admin-login-card" onSubmit={handleSubmit}>
        <h1>관리자 로그인</h1>
        <p>로봇 모니터링·이력·안전 관리 페이지입니다.</p>
        {error && <div className="admin-error">{error}</div>}
        <input
          type="password"
          placeholder="비밀번호"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
        />
        <button type="submit" disabled={submitting || !password}>
          {submitting ? '확인 중…' : '로그인'}
        </button>
      </form>
    </div>
  )
}
