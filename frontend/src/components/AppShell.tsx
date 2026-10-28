import { useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'

import { api, telemetry } from '../api/client'
import type { Role } from '../api/types'
import { useAuth } from '../auth/useAuth'
import { useResource } from '../hooks/useResource'
import { useNow } from '../hooks/useNow'
import { formatDate, formatTime, initials } from '../lib/format'
import { Icon, type IconName } from './Icon'

interface NavItem {
  to: string
  label: (role: Role) => string
  icon: IconName
  roles: Role[]
  end?: boolean
}

interface NavGroup {
  title: string
  items: NavItem[]
}

const NAV: NavGroup[] = [
  {
    title: 'Monitor',
    items: [
      {
        to: '/',
        label: () => 'Dashboard',
        icon: 'dashboard',
        roles: ['patient', 'doctor', 'admin'],
        end: true,
      },
      {
        to: '/live',
        label: () => 'Live monitor',
        icon: 'pulse',
        roles: ['patient', 'doctor', 'admin'],
      },
      {
        to: '/sessions',
        label: () => 'Sessions',
        icon: 'sessions',
        roles: ['patient', 'doctor', 'admin'],
      },
    ],
  },
  {
    title: 'Manage',
    items: [
      {
        to: '/patients',
        label: (role) => (role === 'patient' ? 'My profile' : 'Patients'),
        icon: 'users',
        roles: ['patient', 'doctor', 'admin'],
      },
      {
        to: '/devices',
        label: () => 'Devices',
        icon: 'devices',
        roles: ['doctor', 'admin'],
      },
    ],
  },
]

function pageTitle(pathname: string): string {
  if (pathname.startsWith('/live/')) return 'Live monitor'
  if (pathname.startsWith('/live')) return 'Live monitor'
  if (pathname.startsWith('/sessions/')) return 'Session recording'
  if (pathname.startsWith('/sessions')) return 'Sessions'
  if (pathname.startsWith('/patients')) return 'Patients'
  if (pathname.startsWith('/devices')) return 'Devices'
  return 'Dashboard'
}

function SidebarLink({ item, onNavigate }: { item: NavItem; onNavigate: () => void }) {
  const { user } = useAuth()
  if (!user || !item.roles.includes(user.role)) return null

  return (
    <NavLink
      to={item.to}
      end={item.end}
      onClick={onNavigate}
      className={({ isActive }) => `nav-link${isActive ? ' nav-link--active' : ''}`}
    >
      <Icon name={item.icon} size={18} />
      <span>{item.label(user.role)}</span>
    </NavLink>
  )
}

function SystemHealth() {
  const health = useResource(
    'system-health',
    async () => {
      const [django, fastapi] = await Promise.allSettled([api.health(), telemetry.health()])
      return {
        django: django.status === 'fulfilled',
        fastapi: fastapi.status === 'fulfilled',
      }
    },
    { pollMs: 30_000 },
  )

  const djangoOk = health.data?.django ?? false
  const fastapiOk = health.data?.fastapi ?? false

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
            <strong>ECG Monitor</strong>
            <small>Diagnostic assistant</small>
          </span>
        </div>

        <nav className="nav" aria-label="Main navigation">
          {NAV.map((group) => {
            const visible = group.items.some((item) => item.roles.includes(user.role))
            if (!visible) return null
            return (
              <div className="nav__group" key={group.title}>
                <span className="nav__title">{group.title}</span>
                {group.items.map((item) => (
                  <SidebarLink
                    key={item.to}
                    item={item}
                    onNavigate={() => setSidebarOpen(false)}
                  />
                ))}
              </div>
            )
          })}
        </nav>

        <div className="sidebar__footer">
          <SystemHealth />
          <div className="side-user">
            <span className={`avatar avatar--${user.role}`}>{initials(user.username)}</span>
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
            <span className={`role-chip role-chip--${user.role}`}>{user.role}</span>
          </div>
        </header>

        <div className="disclaimer-strip" role="note">
          <Icon name="shield" size={14} />
          <span>
            <strong>Screening aid, not a medical diagnosis.</strong> Data shown here is
            synthetic or replayed research data unless a real device is connected.
          </span>
        </div>

        <main className="content">
          <Outlet />
        </main>

        <footer className="footer">
          <span>AI-Based ECG Diagnostic Assistant</span>
          <span>
            Phase 4 dashboard · <span className="footer__muted">not for clinical use</span>
          </span>
        </footer>
      </div>
    </div>
  )
}
