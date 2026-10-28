import { useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'

import { api, telemetry } from '../api/client'
import { useAuth } from '../auth/useAuth'
import { useResource } from '../hooks/useResource'
import { useNow } from '../hooks/useNow'
import { formatDate, formatTime, initials } from '../lib/format'
import { Icon, type IconName } from './Icon'

interface NavItem {
  to: string
  label: string
  icon: IconName
  end?: boolean
}

const NAV: NavItem[] = [
  { to: '/', label: 'Dashboard', icon: 'dashboard', end: true },
  { to: '/patients', label: 'Patients', icon: 'users' },
  { to: '/settings', label: 'Settings', icon: 'settings' },
]

function pageTitle(pathname: string): string {
  if (pathname.startsWith('/monitor/')) return 'ECG monitor'
  if (pathname.startsWith('/sessions/')) return 'Analysis & report'
  if (pathname.startsWith('/patients/')) return 'Patient profile'
  if (pathname.startsWith('/patients')) return 'Patients'
  if (pathname.startsWith('/settings')) return 'Settings'
  return 'Dashboard'
}

function SystemHealth() {
  const health = useResource(
    'system-health',
    async () => {
      const [django, fastapi] = await Promise.allSettled([api.health(), telemetry.health()])
      return {
        django: django.status === 'fulfilled',
        fastapi: fastapi.status === 'fulfilled',
        analysis: fastapi.status === 'fulfilled' ? fastapi.value.analysis : undefined,
      }
    },
    { pollMs: 30_000 },
  )

  const djangoOk = health.data?.django ?? false
  const fastapiOk = health.data?.fastapi ?? false
  const ai = health.data?.analysis

  return (
    <div className="system-health">
      <span className="system-health__title">Services</span>
      <div className="system-health__row">
        <span className={`status-dot ${djangoOk ? 'status-dot--ok' : 'status-dot--bad'}`} />
        <span>Django API</span>
        <span className="system-health__state">{djangoOk ? 'up' : 'down'}</span>
      </div>
      <div className="system-health__row">
        <span className={`status-dot ${fastapiOk ? 'status-dot--ok' : 'status-dot--bad'}`} />
        <span>FastAPI telemetry</span>
        <span className="system-health__state">{fastapiOk ? 'up' : 'down'}</span>
      </div>
      <div className="system-health__row">
        <span className={`status-dot ${ai?.inference_available ? 'status-dot--ok' : 'status-dot--warn'}`} />
        <span>AI model</span>
        <span className="system-health__state">
          {ai?.inference_available ? 'ready' : 'not configured'}
        </span>
      </div>
    </div>
  )
}

export function AppShell() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const now = useNow(30_000)
  const [sidebarOpen, setSidebarOpen] = useState(false)

  if (!user) return null

  function signOut() {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="shell">
      <button
        type="button"
        className={`sidebar-scrim${sidebarOpen ? ' sidebar-scrim--visible' : ''}`}
        aria-label="Close navigation"
        onClick={() => setSidebarOpen(false)}
      />

      <aside className={`sidebar${sidebarOpen ? ' sidebar--open' : ''}`}>
        <div className="brand">
          <span className="brand__mark">
            <Icon name="pulse" size={22} />
          </span>
          <span className="brand__text">
            <strong>ECG Assistant</strong>
            <small>Patient · recording · report</small>
          </span>
        </div>

        <nav className="nav" aria-label="Main navigation">
          <div className="nav__group">
            <span className="nav__title">Workflow</span>
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                onClick={() => setSidebarOpen(false)}
                className={({ isActive }) => `nav-link${isActive ? ' nav-link--active' : ''}`}
              >
                <Icon name={item.icon} size={18} />
                <span>{item.label}</span>
              </NavLink>
            ))}
          </div>
        </nav>

        <div className="sidebar__footer">
          <SystemHealth />
          <div className="side-user">
            <span className="avatar">{initials(user.username)}</span>
            <span className="side-user__text">
              <strong>{user.username}</strong>
              <small>{user.role}</small>
            </span>
            <button
              type="button"
              className="icon-button"
              onClick={signOut}
              aria-label="Sign out"
              title="Sign out"
            >
              <Icon name="logout" size={17} />
            </button>
          </div>
        </div>
      </aside>

      <div className="shell__main">
        <header className="topbar">
          <button
            type="button"
            className="icon-button topbar__menu"
            onClick={() => setSidebarOpen((open) => !open)}
            aria-label="Toggle navigation"
          >
            <Icon name={sidebarOpen ? 'close' : 'menu'} size={20} />
          </button>

          <div className="topbar__title">
            <span className="topbar__crumb">{pageTitle(location.pathname)}</span>
          </div>

          <div className="topbar__right">
            <span className="topbar__clock">
              <Icon name="clock" size={15} />
              {formatDate(now.toISOString())} · {formatTime(now.toISOString())}
            </span>
            <span className="role-chip role-chip--operator">{user.role}</span>
          </div>
        </header>

        <div className="disclaimer-strip" role="note">
          <Icon name="shield" size={14} />
          <span>
            <strong>Screening aid, not a medical diagnosis.</strong> AI findings are
            experimental and unavailable without a validated model. Simulator ECG is
            synthetic or replayed research data.
          </span>
        </div>

        <main className="content">
          <Outlet />
        </main>

        <footer className="footer">
          <span>AI-Based ECG Diagnostic Assistant</span>
          <span>
            Patient registry · DSP · optional AI · PDF <span className="footer__muted">not for clinical use</span>
          </span>
        </footer>
      </div>
    </div>
  )
}
