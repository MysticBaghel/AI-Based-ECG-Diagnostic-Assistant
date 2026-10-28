import { Suspense, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'

import { useAuth } from '@/features/auth/useAuth'
import { Icon } from '@/shared/icons/Icon'
import { Spinner } from '@/shared/ui'
import { Sidebar } from './Sidebar'
import { Topbar } from './Topbar'

export function AppShell() {
  const { user } = useAuth()
  const location = useLocation()
  const [sidebarOpen, setSidebarOpen] = useState(false)

  if (!user) return null

  return (
    <div className="shell">
      <button
        type="button"
        className={`sidebar-scrim${sidebarOpen ? ' sidebar-scrim--visible' : ''}`}
        aria-label="Close navigation"
        onClick={() => setSidebarOpen(false)}
      />

      <Sidebar
        pathname={location.pathname}
        open={sidebarOpen}
        onNavigate={() => setSidebarOpen(false)}
      />

      <div className="shell__main">
        <Topbar
          pathname={location.pathname}
          sidebarOpen={sidebarOpen}
          onToggleSidebar={() => setSidebarOpen((open) => !open)}
        />

        <div className="disclaimer-strip" role="note">
          <Icon name="shield" size={13} />
          <span>Screening aid, not a medical diagnosis</span>
        </div>

        <main className="content">
          <Suspense fallback={<Spinner label="Loading page…" />}>
            <Outlet />
          </Suspense>
        </main>

        <footer className="footer">
          <span>AI-Based ECG Diagnostic Assistant</span>
          <span>
            Patient registry · DSP · optional AI · PDF{' '}
            <span className="footer__muted">not for clinical use</span>
          </span>
        </footer>
      </div>
    </div>
  )
}
