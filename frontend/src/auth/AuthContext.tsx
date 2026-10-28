import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'

import {
  api,
  AUTH_EXPIRED_EVENT,
  clearTokens,
  getAccessToken,
  getRefreshToken,
  storeTokens,
} from '../api/client'
import type { User } from '../api/types'
import { AuthContext, type AuthStatus, type AuthValue } from './auth-context'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>(() =>
    getAccessToken() || getRefreshToken() ? 'loading' : 'anonymous',
  )
  const [user, setUser] = useState<User | null>(null)

  useEffect(() => {
    let cancelled = false

    async function restore() {
      if (!getAccessToken() && !getRefreshToken()) {
        setStatus('anonymous')
        return
      }
      try {
        const current = await api.me()
        if (cancelled) return
        setUser(current)
        setStatus('authenticated')
      } catch {
        if (cancelled) return
        clearTokens()
        setUser(null)
        setStatus('anonymous')
      }
    }

    void restore()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    function onExpired() {
      setUser(null)
      setStatus('anonymous')
    }
    window.addEventListener(AUTH_EXPIRED_EVENT, onExpired)
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, onExpired)
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    const tokens = await api.login(username.trim(), password)
    storeTokens(tokens)
    try {
      const current = await api.me()
      setUser(current)
      setStatus('authenticated')
      return current
    } catch (error) {
      clearTokens()
      setUser(null)
      setStatus('anonymous')
      throw error
    }
  }, [])

  const logout = useCallback(() => {
    clearTokens()
    setUser(null)
    setStatus('anonymous')
  }, [])

  const value = useMemo<AuthValue>(
    () => ({ status, user, login, logout }),
    [status, user, login, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
