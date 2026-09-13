import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'

export default function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { token, mustChangePassword } = useAuth()
  const location = useLocation()
  if (!token) return <Navigate to="/login" state={{ from: location }} replace />
  if (mustChangePassword && location.pathname !== '/change-password') return <Navigate to="/change-password" replace />
  return <>{children}</>
}
