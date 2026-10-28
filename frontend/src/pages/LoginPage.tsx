import { useState, type FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'

import { ApiError } from '../api/client'
import { useAuth } from '../auth/useAuth'
import { Icon } from '../components/Icon'

const DEMO_ACCOUNTS = [
  { username: 'operator', role: 'Operator', detail: 'register patients & record ECG' },
  { username: 'admin', role: 'Administrator', detail: 'operator access + Django Admin' },
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
            <strong>ECG Assistant</strong>
            <small>AI-based diagnostic assistant</small>
          </span>
        </div>

        <div className="login__pitch">
          <p className="eyebrow">Single-lead ECG workflow</p>
          <h1>
            Register a patient.
            <br />
            Record the signal.
            <br />
            <span>Review it later.</span>
          </h1>
          <p>
            A focused screening tool for clinic operators: a permanent patient registry,
            live ESP32 + AD8232 or simulator recordings, deterministic signal processing,
            optional AI classification, and a downloadable PDF report.
          </p>
        </div>

        <ul className="login__features">
          <li>
            <Icon name="users" size={18} />
            One permanent patient ID, searchable by name, phone or ID
          </li>
          <li>
            <Icon name="pulse" size={18} />
            Live ECG waveform over a WebSocket, with signal quality and heart rate
          </li>
          <li>
            <Icon name="sessions" size={18} />
            Every recording and report stays attached to the patient's history
          </li>
        </ul>

        <div className="login__disclaimer">
          <Icon name="alert" size={18} />
          <p>
            <strong>Screening aid, not a medical diagnosis.</strong> AI classification is
            unavailable unless a validated model is configured. Simulator data is synthetic
            or replayed research data and does not prove diagnostic accuracy.
          </p>
        </div>
      </section>

      <section className="login__panel">
        <div className="login__card">
          <header>
            <h2>Operator sign in</h2>
            <p>Sign in to the clinic's ECG workspace.</p>
          </header>

          <form onSubmit={onSubmit} className="form">
            <label className="field">
              <span>Username</span>
              <input
                autoComplete="username"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                placeholder="operator"
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
