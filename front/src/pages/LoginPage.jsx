import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { STUB_USERS } from '../mocks/users'

export default function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [loginName, setLoginName] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')

  function handleSubmit(e) {
    e.preventDefault()
    const result = login(loginName, password)
    if (!result.ok) {
      setError(result.error)
      return
    }
    const role = STUB_USERS.find((u) => u.login === loginName.trim())?.role
    navigate(role === 'admin' ? '/admin' : '/client')
  }

  return (
    <div className="login-page">
      <div className="login-panel">
        <p className="eyebrow">MedTech · stub auth</p>
        <h1 className="login-brand">
          Sparrow <em>Route</em>
        </h1>
        <p className="lede">Вход по логину и паролю. Бэкенд не проверяет — всё на заглушках.</p>

        <form className="login-form" onSubmit={handleSubmit}>
          <label className="field">
            <span>Логин</span>
            <input
              autoComplete="username"
              value={loginName}
              onChange={(e) => setLoginName(e.target.value)}
              placeholder="client или admin"
            />
          </label>
          <label className="field">
            <span>Пароль</span>
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
            />
          </label>
          {error && <p className="error">{error}</p>}
          <button type="submit" className="btn primary wide">
            Войти
          </button>
        </form>

        <div className="stub-box">
          <strong>Тестовые учётки</strong>
          <ul>
            {STUB_USERS.map((u) => (
              <li key={u.login}>
                <code>{u.login}</code> / <code>{u.password}</code> → {u.role}
                {u.role === 'client' ? (
                  <>
                    {' '}
                    · id <code>{u.id}</code>
                  </>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}
