import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

const ROLE_PILL = {
  admin: 'Admin',
  doctor: 'Врач',
  coordinator: 'Координатор',
  client: 'Пациент',
}

export default function AppShell({ children, variant = 'admin' }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  function handleLogout() {
    logout()
    navigate('/login')
  }

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand" role="button" tabIndex={0} onClick={() => navigate(homeFor(user))} onKeyDown={() => {}}>
          <span className="brand-mark">Sparrow</span>
          <span className="brand-sub">Route</span>
        </div>
        <nav className="topbar-nav">
          {user?.role === 'admin' ? (
            <>
              <button type="button" className="btn ghost tiny" onClick={() => navigate('/admin')}>
                Протоколы
              </button>
              <button type="button" className="btn ghost tiny" onClick={() => navigate('/manager')}>
                Воронка
              </button>
              <button type="button" className="btn ghost tiny" onClick={() => navigate('/patient')}>
                Пациент
              </button>
              <button type="button" className="btn ghost tiny" onClick={() => navigate('/doctor')}>
                Врач
              </button>
              <button type="button" className="btn ghost tiny" onClick={() => navigate('/coordinator')}>
                Координатор
              </button>
            </>
          ) : null}
        </nav>
        <div className="topbar-meta">
          <span className="pill">{ROLE_PILL[user?.role] || variant}</span>
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

function homeFor(user) {
  if (!user) return '/login'
  if (user.role === 'admin') return '/admin'
  if (user.role === 'doctor') return '/doctor'
  if (user.role === 'coordinator') return '/coordinator'
  return '/patient'
}
