import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'

import {
  defaultTelemetryBase,
  setTelemetryBase,
  telemetryBase,
} from '@/shared/api/config'
import { healthApi } from '@/shared/api/health'
import { Icon } from '@/shared/icons/Icon'
import {
  ErrorBanner,
  Notice,
  PageHeader,
  SectionCard,
  StatCard,
} from '@/shared/ui'
import { useResource } from '@/shared/api/useResource'

export function SettingsPage() {
  const health = useResource(
    'settings-health',
    async () => {
      const [django, fastapi] = await Promise.allSettled([healthApi.django(), healthApi.telemetry()])
      return {
        django: django.status === 'fulfilled' ? django.value : null,
        fastapi: fastapi.status === 'fulfilled' ? fastapi.value : null,
      }
    },
    { pollMs: 30_000 },
  )

  const [baseUrl, setBaseUrl] = useState(telemetryBase())
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  function saveBaseUrl(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    try {
      if (!baseUrl.trim()) throw new Error('Enter a telemetry base URL or reset to default.')
      setTelemetryBase(baseUrl)
      setError(null)
      setSaved(true)
      window.setTimeout(() => window.location.reload(), 250)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not save the setting.')
    }
  }

  function resetBaseUrl() {
    setTelemetryBase(null)
    setBaseUrl(defaultTelemetryBase())
    setSaved(true)
    window.setTimeout(() => window.location.reload(), 250)
  }

  const analysis = health.data?.fastapi?.analysis

  return (
    <>
      <PageHeader
        title="Settings"
        description="Backend connections, analysis capability and application limitations"
      />

      {error && <ErrorBanner message={error} />}

      <div className="stats stats--four">
        <StatCard
          icon="dashboard"
          label="Django API"
          value={health.data?.django?.status ?? 'down'}
          hint="identity & business data"
          tone={health.data?.django ? 'ok' : 'bad'}
        />
        <StatCard
          icon="activity"
          label="FastAPI"
          value={health.data?.fastapi?.status ?? 'down'}
          hint="telemetry & DSP"
          tone={health.data?.fastapi ? 'ok' : 'bad'}
        />
        <StatCard
          icon="spark"
          label="AI model"
          value={analysis?.inference_available ? 'ready' : 'not configured'}
          hint={analysis?.model_name ?? 'add a validated model'}
          tone={analysis?.inference_available ? 'ok' : 'warn'}
        />
        <StatCard
          icon="shield"
          label="Role"
          value="Operator"
          hint="clinic-wide patient access"
        />
      </div>

      <div className="dashboard-grid dashboard-grid--narrow">
        <SectionCard title="API connections" subtitle="The browser talks to Django and FastAPI">
          <form className="form" onSubmit={saveBaseUrl}>
            <label className="field">
              <span>Telemetry API base URL</span>
              <input
                value={baseUrl}
                onChange={(event) => {
                  setBaseUrl(event.target.value)
                  setSaved(false)
                }}
                placeholder="/telemetry"
              />
              <small>
                Default: <code>{defaultTelemetryBase()}</code>. In development this is the
                Vite proxy. Saving reloads the application.
              </small>
            </label>
            <div className="button-row">
              <button type="submit" className="button button--primary button--sm">
                Save & reload
              </button>
              <button type="button" className="button button--ghost button--sm" onClick={resetBaseUrl}>
                Reset to default
              </button>
              {saved && <span className="muted small">Saved. Reloading…</span>}
            </div>
          </form>
          <div className="kv-list">
            <div>
              <span>Django API</span>
              <strong className="mono">{import.meta.env.VITE_API_BASE_URL ?? '/api'}</strong>
            </div>
            <div>
              <span>FastAPI telemetry</span>
              <strong className="mono">{telemetryBase()}</strong>
            </div>
            <div>
              <span>Model status</span>
              <strong>
                {analysis?.inference_reason ||
                  (analysis?.inference_available ? 'validated model loaded' : 'not checked')}
              </strong>
            </div>
          </div>
          <Notice tone="warn" icon="alert">
            <strong>No model is bundled.</strong> DSP measurements are always available. AI
            classification is shown only when a validated model file is configured on FastAPI;
            otherwise the UI and every report state that it is unavailable.
          </Notice>
        </SectionCard>

        <SectionCard title="Devices and simulator" subtitle="Recordings use one ingestion contract">
          <p className="small muted">
            Register an ESP32 + AD8232 or a simulator device, then copy its token. The live
            monitor shows the session id to use.
          </p>
          <div className="button-row">
            <Link to="/devices" className="button button--primary button--sm">
              <Icon name="devices" size={14} />
              Manage devices
            </Link>
            <Link to="/patients" className="button button--ghost button--sm">
              <Icon name="users" size={14} />
              Patients
            </Link>
          </div>
          <pre className="code-block">
            <code>{`python -m simulator --session-id <SESSION_ID> \\
  --device-token <DEVICE_TOKEN> --ecg --duration 60`}</code>
          </pre>
          <p className="small muted">
            The simulator sends the same payloads as the ESP32. It is synthetic or replayed
            research data, not proof of diagnostic accuracy.
          </p>
        </SectionCard>
      </div>

      <SectionCard title="Limitations of this installation" subtitle="Read before relying on any output">
        <ul className="finding-list">
          <li>Screening aid, not a standalone medical diagnosis.</li>
          <li>AI classification is experimental and unavailable unless a validated model is configured.</li>
          <li>Simulator ECG is synthetic or replayed research data; a successful simulator run does not prove diagnostic accuracy.</li>
          <li>All authenticated operators share the clinic's patient registry. Multi-clinic tenancy is not implemented.</li>
          <li>Django Admin remains available for technical account administration, but is not the operator interface.</li>
        </ul>
      </SectionCard>
    </>
  )
}
