import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

export default function AppShell({ children }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  function handleLogout() {
    logout()
    navigate('/login')
  }

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">Sparrow</span>
          <span className="brand-sub">Route</span>
        </div>
        <div className="topbar-meta">
          <span className="pill">{user?.role === 'admin' ? 'Admin' : 'Client'}</span>
          <span className="muted">{user?.name}</span>
          <button type="button" className="btn ghost" onClick={handleLogout}>
            Выйти
          </button>
        </div>
      </header>
      <main className="main">{children}</main>
    </div>
  )
}
