import { useState, type FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'

import { ApiError } from '@/shared/api/http'
import { isPersistent, setPersistent } from '@/shared/api/tokenStore'
import { useAuth } from '@/features/auth/useAuth'
import { Icon } from '@/shared/icons/Icon'

const FEATURES = [
  { icon: 'heart' as const, label: 'Live ECG Monitoring' },
  { icon: 'spark' as const, label: 'AI Analysis' },
  { icon: 'sessions' as const, label: 'Patient History' },
  { icon: 'file-text' as const, label: 'Downloadable Reports' },
]

export function LoginPage() {
  const { status, user, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [remember, setRemember] = useState(isPersistent)
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const from = (location.state as { from?: string } | null)?.from ?? '/'

  if (status === 'authenticated' && user) {
    return <Navigate to={from} replace />
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setNotice(null)
    setSubmitting(true)
    setPersistent(remember)
    try {
      await login(username.trim(), password)
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

  return (
    <div className="login">
      <section className="login__intro">
        <div className="login__brand">
          <span className="login__brand-mark">
            <Icon name="pulse" size={26} />
          </span>
          <span>PulseTrace ECG</span>
        </div>

        <div className="login__pitch">
          <h1>
            AI-Based
            <br />
            ECG Diagnostic
            <br />
            Assistant
          </h1>
          <p>
            Record, analyse and get AI-powered insights from ECG signals.
            <br />
            Simple. Fast. Reliable.
          </p>
        </div>

        <ul className="login__features">
          {FEATURES.map((feature) => (
            <li key={feature.label}>
              <span className="login__feature-icon">
                <Icon name={feature.icon} size={18} />
              </span>
              {feature.label}
            </li>
          ))}
        </ul>

        <svg className="login__ecg" viewBox="0 0 900 220" preserveAspectRatio="none" aria-hidden="true">
          <defs>
            <pattern id="login-grid" width="34" height="34" patternUnits="userSpaceOnUse">
              <path d="M34 0H0V34" fill="none" stroke="rgba(45,212,191,0.10)" strokeWidth="1" />
            </pattern>
            <linearGradient id="login-line" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0" stopColor="rgba(45,212,191,0)" />
              <stop offset="0.25" stopColor="rgba(45,212,191,0.55)" />
              <stop offset="0.7" stopColor="#2dd4bf" />
              <stop offset="1" stopColor="rgba(45,212,191,0.15)" />
            </linearGradient>
          </defs>
          <rect width="900" height="220" fill="url(#login-grid)" />
          <path
            d="M0 140h250l18-30 20 66 24-104 22 92 20-40h60l18-22 18 44 16-22h120l20-18 20 44 18-28h96l16-38 20 76 20-48 22 10h60"
            fill="none"
            stroke="url(#login-line)"
            strokeWidth="2.4"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </section>

      <section className="login__panel">
        <div className="login__card">
          <header>
            <h2>Sign in</h2>
            <p>Access your ECG dashboard</p>
          </header>

          <form onSubmit={onSubmit} className="login__form">
            <label className="login-field">
              <span>Username</span>
              <div className="login-field__control">
                <Icon name="mail" size={17} />
                <input
                  autoComplete="username"
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  placeholder="operator"
                  required
                  autoFocus
                />
              </div>
            </label>

            <label className="login-field">
              <span>Password</span>
              <div className="login-field__control">
                <Icon name="lock" size={17} />
                <input
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="••••••••"
                  required
                />
                <button
                  type="button"
                  className="login-field__toggle"
                  onClick={() => setShowPassword((value) => !value)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  <Icon name={showPassword ? 'eye-off' : 'eye'} size={17} />
                </button>
              </div>
            </label>

            <div className="login__row">
              <label className="login__remember">
                <input
                  type="checkbox"
                  checked={remember}
                  onChange={(event) => setRemember(event.target.checked)}
                />
                Remember me
              </label>
              <button
                type="button"
                className="login__link"
                onClick={() =>
                  setNotice(
                    'Password resets are handled by your clinic administrator in Django Admin.',
                  )
                }
              >
                Forgot password?
              </button>
            </div>

            {error && (
              <div className="login__message login__message--error" role="alert">
                <Icon name="alert" size={16} />
                <span>{error}</span>
              </div>
            )}
            {notice && (
              <div className="login__message" role="status">
                <Icon name="shield" size={16} />
                <span>{notice}</span>
              </div>
            )}

            <button type="submit" className="login__submit" disabled={submitting}>
              {submitting ? 'Signing in…' : 'Sign in'}
              {!submitting && <Icon name="arrow-right" size={17} />}
            </button>
          </form>

          <div className="login__demo">
            <span>Demo access</span>
            <code>operator / demo12345</code>
            <span className="login__seed">
              Seed data: <code>python manage.py seed_demo</code>
            </span>
          </div>
        </div>

        <p className="login__footer">
          <Icon name="shield" size={14} /> Screening aid, not a medical diagnosis.
        </p>
      </section>
    </div>
  )
}
