import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth/AuthContext'
import LoginPage from './pages/LoginPage'
import ClientDashboard from './pages/ClientDashboard'
import AdminDashboard from './pages/AdminDashboard'
import AppShell from './components/AppShell'

function Protected({ role, children }) {
  const { user } = useAuth()
  if (!user) return <Navigate to="/login" replace />
  if (role && user.role !== role) {
    return <Navigate to={user.role === 'admin' ? '/admin' : '/client'} replace />
  }
  return children
}

export default function App() {
  const { user } = useAuth()

  return (
    <Routes>
      <Route
        path="/login"
        element={user ? <Navigate to={user.role === 'admin' ? '/admin' : '/client'} replace /> : <LoginPage />}
      />
      <Route
        path="/client"
        element={
          <Protected role="client">
            <AppShell>
              <ClientDashboard />
            </AppShell>
          </Protected>
        }
      />
      <Route
        path="/admin"
        element={
          <Protected role="admin">
            <AppShell>
              <AdminDashboard />
            </AppShell>
          </Protected>
        }
      />
      <Route path="*" element={<Navigate to={user ? (user.role === 'admin' ? '/admin' : '/client') : '/login'} replace />} />
    </Routes>
  )
}
