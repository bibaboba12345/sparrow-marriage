import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth/AuthContext'
import LoginPage from './pages/LoginPage'
import AdminDashboard from './pages/AdminDashboard'
import PatientDashboard from './pages/PatientDashboard'
import DoctorDashboard from './pages/DoctorDashboard'
import CoordinatorDashboard from './pages/CoordinatorDashboard'
import ManagerDashboard from './pages/ManagerDashboard'
import AppShell from './components/AppShell'

function homeFor(user) {
  if (!user) return '/login'
  if (user.role === 'admin') return '/admin'
  if (user.role === 'doctor') return '/doctor'
  if (user.role === 'coordinator') return '/coordinator'
  return '/patient'
}

function Protected({ children, roles }) {
  const { user } = useAuth()
  if (!user) return <Navigate to="/login" replace />
  if (roles && !roles.includes(user.role)) {
    return <Navigate to={homeFor(user)} replace />
  }
  return children
}

function Shell({ variant, children }) {
  return <AppShell variant={variant}>{children}</AppShell>
}

export default function App() {
  const { user } = useAuth()

  return (
    <Routes>
      <Route
        path="/login"
        element={user ? <Navigate to={homeFor(user)} replace /> : <LoginPage />}
      />
      <Route
        path="/admin"
        element={
          <Protected roles={['admin']}>
            <Shell variant="admin">
              <AdminDashboard />
            </Shell>
          </Protected>
        }
      />
      <Route
        path="/manager"
        element={
          <Protected roles={['admin']}>
            <Shell variant="admin">
              <ManagerDashboard />
            </Shell>
          </Protected>
        }
      />
      <Route
        path="/patient"
        element={
          <Protected roles={['client', 'admin']}>
            <Shell variant="patient">
              <PatientDashboard />
            </Shell>
          </Protected>
        }
      />
      <Route
        path="/doctor"
        element={
          <Protected roles={['doctor', 'admin']}>
            <Shell variant="doctor">
              <DoctorDashboard />
            </Shell>
          </Protected>
        }
      />
      <Route
        path="/coordinator"
        element={
          <Protected roles={['coordinator', 'admin']}>
            <Shell variant="coordinator">
              <CoordinatorDashboard />
            </Shell>
          </Protected>
        }
      />
      <Route path="/client" element={<Navigate to="/patient" replace />} />
      <Route path="*" element={<Navigate to={homeFor(user)} replace />} />
    </Routes>
  )
}
