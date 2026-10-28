import { useState, type FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'

import { ApiError } from '../api/client'
import { useAuth } from '../auth/useAuth'
import { Icon } from '../components/Icon'

const DEMO_ACCOUNTS = [
  { username: 'doctor1', role: 'Doctor', detail: 'assigned patients + devices' },
  { username: 'patient1', role: 'Patient', detail: 'own sessions, read-only' },
  { username: 'admin', role: 'Admin', detail: 'everything' },
]

export function LoginPage() {
  const { status, user, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const from = (location.state as { from?: string } | null)?.from ?? '/'

  if (status === 'authenticated' && user) {
    return <Navigate to={from} replace />
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await login(username, password)
      navigate(from, { replace: true })
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.status === 401
            ? 'That username and password do not match.'
            : caught.message
          : 'Could not sign in. Is the Django API running?',
      )
    } finally {
      setSubmitting(false)
    }
  }

  function fillDemo(name: string) {
    setUsername(name)
    setPassword('demo12345')
    setError(null)
  }

  return (
    <div className="login">
      <section className="login__intro">
        <div className="brand brand--login">
          <span className="brand__mark">
            <Icon name="pulse" size={24} />
          </span>
          <span className="brand__text">
            <strong>ECG Monitor</strong>
            <small>Diagnostic assistant</small>
          </span>
        </div>

        <div className="login__pitch">
          <p className="eyebrow">AI-Based ECG Diagnostic Assistant</p>
          <h1>
            One patient.
            <br />
            One device.
            <br />
            <span>Every signal in view.</span>
          </h1>
          <p>
            A browser dashboard for the monitoring stack: Django owns identity and
            sessions, FastAPI streams the telemetry, and this page shows live ECG and
            vitals as they arrive.
          </p>
        </div>

        <ul className="login__features">
          <li>
            <Icon name="pulse" size={18} />
            Live ECG waveform and four scalar vitals over one WebSocket
          </li>
          <li>
            <Icon name="sessions" size={18} />
            Start a session, watch it, then revisit the recording
          </li>
          <li>
            <Icon name="shield" size={18} />
            Role-aware: patients see their own data, doctors their assigned patients
          </li>
        </ul>

        <div className="login__disclaimer">
          <Icon name="alert" size={18} />
          <p>
            <strong>Screening aid, not a medical diagnosis.</strong> Nothing shown in this
            application is a clinical finding. The simulator sends synthetic or replayed
            research data.
          </p>
        </div>
      </section>

      <section className="login__panel">
        <div className="login__card">
          <header>
            <h2>Sign in</h2>
            <p>Use a demo account to explore the Phase 4 dashboard.</p>
          </header>

          <form onSubmit={onSubmit} className="form">
            <label className="field">
              <span>Username</span>
              <input
                autoComplete="username"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                placeholder="doctor1"
                required
                autoFocus
              />
            </label>

            <label className="field">
              <span>Password</span>
              <input
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="demo12345"
                required
              />
            </label>

            {error && (
              <div className="banner banner--error" role="alert">
                <Icon name="alert" size={17} />
                <div className="banner__body">{error}</div>
              </div>
            )}

            <button type="submit" className="button button--primary button--block" disabled={submitting}>
              {submitting ? 'Signing in…' : 'Sign in'}
              {!submitting && <Icon name="chevron-right" size={17} />}
            </button>
          </form>

          <div className="login__demo">
            <span className="login__demo-title">Demo accounts · password demo12345</span>
            <div className="login__demo-list">
              {DEMO_ACCOUNTS.map((account) => (
                <button
                  type="button"
                  key={account.username}
                  className="demo-account"
                  onClick={() => fillDemo(account.username)}
                >
                  <span>
                    <strong>{account.username}</strong>
                    <small>{account.role}</small>
                  </span>
                  <span className="demo-account__detail">{account.detail}</span>
                </button>
              ))}
            </div>
            <p className="login__seed">
              No accounts yet? Run <code>python manage.py seed_demo</code> in{' '}
              <code>backend/django</code>.
            </p>
          </div>
        </div>

        <p className="login__footer">
          <Icon name="shield" size={14} /> Screening aid, not a medical diagnosis.
        </p>
      </section>
    </div>
  )
}
