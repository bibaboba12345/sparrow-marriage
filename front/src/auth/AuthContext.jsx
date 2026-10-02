import { createContext, useContext, useState } from 'react'
import { STUB_USERS } from '../mocks/users'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try {
      const raw = localStorage.getItem('sparrow_user')
      if (!raw) return null
      const session = JSON.parse(raw)
      // старые сессии без id — подтянуть из stub-списка
      if (!session.id && session.login) {
        const found = STUB_USERS.find((u) => u.login === session.login)
        if (found) {
          session.id = found.id
          session.name = found.name
          localStorage.setItem('sparrow_user', JSON.stringify(session))
        }
      }
      return session
    } catch {
      return null
    }
  })

  function login(loginName, password) {
    // STUB: hardcoded users, no backend
    const found = STUB_USERS.find(
      (u) => u.login === loginName.trim() && u.password === password,
    )
    if (!found) {
      return { ok: false, error: 'Неверный логин или пароль (stub)' }
    }
    const session = {
      login: found.login,
      role: found.role,
      name: found.name,
      id: found.id,
    }
    localStorage.setItem('sparrow_user', JSON.stringify(session))
    setUser(session)
    return { ok: true }
  }

  function logout() {
    localStorage.removeItem('sparrow_user')
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth outside AuthProvider')
  return ctx
}
