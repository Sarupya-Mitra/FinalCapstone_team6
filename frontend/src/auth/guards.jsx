import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { ROLE_HOME, useAuth } from './AuthContext'
import { Loading } from '../components/ui'

// Requires a signed-in user, optionally with a given role.
export function RequireAuth({ role }) {
  const { user, loading } = useAuth()
  const location = useLocation()

  if (loading) return <Loading label="Restoring session…" />
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  if (role && user.role !== role) return <Navigate to={ROLE_HOME[user.role] || '/login'} replace />
  return <Outlet />
}

// Sends "/" to the right dashboard for the current role.
export function HomeRedirect() {
  const { user, loading } = useAuth()
  if (loading) return <Loading label="Restoring session…" />
  return <Navigate to={user ? ROLE_HOME[user.role] : '/login'} replace />
}
