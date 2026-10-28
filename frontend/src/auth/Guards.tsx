import type { ReactNode } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'

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

/** Kept as a named component for pages that need an inline condition. */
export function AuthenticatedOnly({ children }: { children: ReactNode }) {
  const { status } = useAuth()
  if (status !== 'authenticated') return <Navigate to="/login" replace />
  return <>{children}</>
}
