import type { ReactNode } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'

import type { Role } from '../api/types'
import { Icon } from '../components/Icon'
import { useAuth } from './useAuth'

export function RequireAuth() {
  const { status } = useAuth()
  const location = useLocation()

  if (status === 'loading') {
    return (
      <div className="splash">
        <span className="splash__mark">
          <Icon name="pulse" size={28} />
        </span>
        <span className="spinner__ring" />
        <p>Restoring your session…</p>
      </div>
    )
  }

  if (status !== 'authenticated') {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }

  return <Outlet />
}

/** Page-level role gate. Hiding a nav link is not authorisation; this is. */
export function RoleGate({ allow, children }: { allow: Role[]; children: ReactNode }) {
  const { user } = useAuth()
  if (!user) return null
  if (!allow.includes(user.role)) return <Navigate to="/" replace />
  return <>{children}</>
}
