import { useCallback, useEffect, useState } from 'react'
import { adminLogin, adminLogout, adminSession } from '../../api/adminClient'

export function useAdminSession() {
  const [authenticated, setAuthenticated] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    try {
      const data = await adminSession()
      setAuthenticated(Boolean(data.authenticated))
      setError('')
    } catch {
      setAuthenticated(false)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const login = useCallback(async (password) => {
    setError('')
    try {
      await adminLogin(password)
      setAuthenticated(true)
      return true
    } catch (err) {
      setError(err.message || '로그인 실패')
      setAuthenticated(false)
      return false
    }
  }, [])

  const logout = useCallback(async () => {
    try {
      await adminLogout()
    } finally {
      setAuthenticated(false)
    }
  }, [])

  return { authenticated, loading, error, login, logout, refresh }
}
