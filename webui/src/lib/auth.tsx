import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { fetchUserInfo } from './api'
import { getToken, setToken } from './http'
import type { UserInfo } from './types'

interface AuthState {
  user: UserInfo | null
  ready: boolean
  signIn: (token: string, user: UserInfo) => void
  signOut: () => void
  refresh: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserInfo | null>(null)
  const [ready, setReady] = useState(false)

  const refresh = useCallback(async () => {
    if (!getToken()) {
      setUser(null)
      setReady(true)
      return
    }
    try {
      setUser(await fetchUserInfo())
    } catch {
      setToken('')
      setUser(null)
    } finally {
      setReady(true)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const value = useMemo<AuthState>(
    () => ({
      user,
      ready,
      signIn: (token, info) => {
        setToken(token)
        setUser(info)
      },
      signOut: () => {
        setToken('')
        setUser(null)
        location.hash = '#/login'
      },
      refresh,
    }),
    [user, ready, refresh],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth 必须在 AuthProvider 内使用')
  return context
}
