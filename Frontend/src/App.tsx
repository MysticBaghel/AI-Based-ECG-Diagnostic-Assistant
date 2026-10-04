import { useEffect, useState } from 'react'
import './App.css'

type HealthState = 'checking' | 'online' | 'offline'

type HealthPayload = {
  status?: string
  service?: string
}

const LABELS: Record<HealthState, string> = {
  checking: 'Checking…',
  online: 'Backend online',
  offline: 'Backend offline',
}

function App() {
  const [count, setCount] = useState(0)
  const [health, setHealth] = useState<HealthState>('checking')
  const [detail, setDetail] = useState('Contacting /api/health …')

  useEffect(() => {
    const controller = new AbortController()

    async function checkHealth() {
      try {
        const response = await fetch('/api/health', { signal: controller.signal })
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`)
        }
        const data = (await response.json()) as HealthPayload
        setHealth('online')
        setDetail(data.service ? `${data.service}: ${data.status ?? 'ok'}` : 'ok')
      } catch (error) {
        if (controller.signal.aborted) return
        setHealth('offline')
        setDetail(error instanceof Error ? error.message : 'Request failed')
      }
    }

    void checkHealth()
    return () => controller.abort()
  }, [])

  return (
    <main className="app">
      <header className="app__header">
        <h1>Major Project</h1>
        <p className="app__subtitle">
          React + TypeScript (Vite) talking to a Django + FastAPI backend.
        </p>
      </header>

      <section className={`card card--${health}`}>
        <h2>{LABELS[health]}</h2>
        <p className="card__detail">{detail}</p>
        <p className="card__hint">
          Start the backend on <code>http://127.0.0.1:8000</code>; Vite proxies{' '}
          <code>/api</code> there during development.
        </p>
      </section>

      <section className="card">
        <h2>React is working</h2>
        <button type="button" onClick={() => setCount((value) => value + 1)}>
          count is {count}
        </button>
      </section>
    </main>
  )
}

export default App
