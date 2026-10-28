import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { api, telemetry } from '../api/client'
import type { Patient, Session } from '../api/types'
import { useAuth } from '../auth/useAuth'
import { Icon } from '../components/Icon'
import { PatientForm } from '../components/PatientForm'
import { SessionTable } from '../components/SessionList'
import { StartSessionDialog } from '../components/StartSessionDialog'
import {
  Badge,
  EmptyState,
  ErrorBanner,
  Notice,
  PageHeader,
  SectionCard,
  Spinner,
  StatCard,
} from '../components/ui'
import { useDeviceStatus, useDevices, usePatients, useSessions } from '../hooks/useData'
import { useResource } from '../hooks/useResource'
import { formatRelative, initials } from '../lib/format'

function PatientSearch({
  onSelect,
  onRegister,
}: {
  onSelect: (patient: Patient) => void
  onRegister: () => void
}) {
  const [query, setQuery] = useState('')
  const patients = usePatients(query, query.trim().length > 0)
  const results = (patients.data ?? []).slice(0, 6)

  return (
    <div className="search-panel">
      <div className="toolbar">
        <label className="search search--grow">
          <Icon name="search" size={16} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Find a patient by name, phone number or patient ID…"
            aria-label="Search patients for a new recording"
          />
        </label>
        <button type="button" className="button button--ghost" onClick={onRegister}>
          <Icon name="plus" size={15} />
          New patient
        </button>
      </div>

      {query.trim() && (
        <div className="search-results">
          {patients.loading ? (
            <Spinner label="Searching…" />
          ) : patients.error ? (
            <ErrorBanner message={patients.error} onRetry={patients.refresh} />
          ) : results.length === 0 ? (
            <div className="search-empty">
              <span>No patient matches “{query}”.</span>
              <button type="button" className="button button--primary button--sm" onClick={onRegister}>
                Register this patient
              </button>
            </div>
          ) : (
            results.map((patient) => (
              <button
                type="button"
                key={patient.id}
                className="search-result"
                onClick={() => onSelect(patient)}
              >
                <span className="avatar avatar--sm">{initials(patient.full_name)}</span>
                <span className="search-result__identity">
                  <strong>{patient.full_name}</strong>
                  <small>
                    {patient.patient_id} · {patient.phone || 'no phone'} ·{' '}
                    {patient.session_count} session{patient.session_count === 1 ? '' : 's'}
                  </small>
                </span>
                <span className="search-result__cta">
                  Start recording
                  <Icon name="chevron-right" size={14} />
                </span>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  )
}

export function DashboardPage() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const sessions = useSessions()
  const devices = useDevices()
  const status = useDeviceStatus()
  const service = useResource('dashboard-services', async () => {
    const [django, fastapi] = await Promise.allSettled([api.health(), telemetry.health()])
    return {
      django: django.status === 'fulfilled',
      fastapi: fastapi.status === 'fulfilled',
      analysis: fastapi.status === 'fulfilled' ? fastapi.value.analysis : undefined,
    }
  }, { pollMs: 30_000 })

  const [selected, setSelected] = useState<Patient | null>(null)
  const [registering, setRegistering] = useState(false)

  const allSessions = useMemo(() => sessions.data ?? [], [sessions.data])
  const active = allSessions.filter((session) => session.status === 'active')
  const analysed = allSessions.filter(
    (session) => session.analysis_status === 'completed',
  ).length
  const reports = allSessions.reduce((sum, session) => sum + session.report_count, 0)
  const online = (status.data?.devices ?? []).filter((device) => device.online).length

  const ai = service.data?.analysis
  const recent = useMemo(() => allSessions.slice(0, 6), [allSessions])
  const loading = sessions.loading && devices.loading

  function openPatient(patient: Patient) {
    setSelected(patient)
  }

  function started(session: Session) {
    setSelected(null)
    navigate(`/monitor/${session.id}`)
  }

  return (
    <>
      <PageHeader
        eyebrow={`Signed in as ${user?.username ?? 'operator'}`}
        title="ECG dashboard"
        description="Find or register a patient, start a recording, and keep every waveform, analysis and report attached to that patient's permanent ID."
        actions={
          <button type="button" className="button button--primary" onClick={() => setRegistering(true)}>
            <Icon name="plus" size={16} />
            Register patient
          </button>
        }
      />

      {(sessions.error || devices.error || status.error) && (
        <ErrorBanner
          message={sessions.error ?? devices.error ?? status.error ?? ''}
          onRetry={() => {
            sessions.refresh()
            devices.refresh()
            status.refresh()
          }}
        />
      )}

      <div className="stats">
        <StatCard
          icon="pulse"
          label="Active recordings"
          value={active.length}
          hint={`${allSessions.length} in history`}
          tone={active.length > 0 ? 'ok' : 'neutral'}
        />
        <StatCard
          icon="sessions"
          label="Analysed recordings"
          value={analysed}
          hint="DSP completed"
          tone={analysed > 0 ? 'ok' : 'neutral'}
        />
        <StatCard icon="shield" label="Reports generated" value={reports} hint="stored PDFs" />
        <StatCard
          icon="wifi"
          label="Devices online"
          value={online}
          hint={`of ${devices.data?.length ?? 0} registered`}
          tone={online > 0 ? 'ok' : 'warn'}
        />
      </div>

      <div className="dashboard-grid">
        <SectionCard
          title="Start a new recording"
          subtitle="Select an existing patient or register a new one"
        >
          <PatientSearch onSelect={openPatient} onRegister={() => setRegistering(true)} />
          {active.length > 0 && (
            <div className="active-strip">
              <Badge tone="ok" pulse>
                {active.length} recording{active.length === 1 ? '' : 's'} active
              </Badge>
              <Link to={`/monitor/${active[0].id}`} className="button button--ghost button--sm">
                Open {active[0].patient_name}
                <Icon name="chevron-right" size={14} />
              </Link>
            </div>
          )}
        </SectionCard>

        <SectionCard title="System status" subtitle="Backends and analysis capability">
          <div className="kv-list">
            <div>
              <span>Django API</span>
              <strong>{service.data?.django ? 'up' : 'down'}</strong>
            </div>
            <div>
              <span>FastAPI telemetry</span>
              <strong>{service.data?.fastapi ? 'up' : 'down'}</strong>
            </div>
            <div>
              <span>Signal processing</span>
              <strong>{ai ? 'deterministic DSP available' : 'waiting for FastAPI'}</strong>
            </div>
            <div>
              <span>AI classifier</span>
              <strong>{ai?.inference_available ? 'validated model loaded' : 'not configured'}</strong>
            </div>
          </div>
          {ai && !ai.inference_available && (
            <Notice tone="warn" icon="alert">
              <strong>AI analysis is unavailable.</strong> {ai.inference_reason} DSP
              measurements are still produced and reports say this explicitly.
            </Notice>
          )}
          {devices.data?.length === 0 && (
            <Notice tone="info" icon="devices">
              No device is registered yet. Register one in Settings before starting a
              recording.
            </Notice>
          )}
        </SectionCard>
      </div>

      <SectionCard
        title="Recordings"
        subtitle="Newest first. Active sessions open the live monitor; completed ones open analysis and reports."
        actions={
          <button
            type="button"
            className="button button--ghost button--sm"
            onClick={() => sessions.refresh()}
            disabled={sessions.refreshing}
          >
            <Icon name="refresh" size={14} />
            {sessions.refreshing ? 'Refreshing…' : 'Refresh'}
          </button>
        }
        flush
      >
        {loading ? (
          <Spinner label="Loading recordings…" />
        ) : allSessions.length === 0 ? (
          <EmptyState
            icon="pulse"
            title="No ECG recordings yet"
            description="Find a patient above, start a recording, then run the simulator or connect the ESP32. The waveform and report will appear here."
          />
        ) : (
          <SessionTable sessions={recent} />
        )}
      </SectionCard>

      <div className="dashboard-grid dashboard-grid--narrow">
        <SectionCard title="Device heartbeat" subtitle="Last connection reported by FastAPI">
          {status.data?.devices.length ? (
            <div className="kv-list">
              {status.data.devices.slice(0, 5).map((device) => {
                const registered = devices.data?.find((item) => item.id === device.device_id)
                return (
                  <div key={device.device_id}>
                    <span>{registered?.name ?? device.device_id.slice(0, 8)}</span>
                    <strong>
                      {device.revoked
                        ? 'revoked'
                        : device.online
                          ? 'online'
                          : `offline · ${formatRelative(device.last_seen)}`}
                    </strong>
                  </div>
                )
              })}
            </div>
          ) : (
            <p className="muted small">
              No heartbeat yet. A device appears after its first <code>/sensor/connect</code>.
            </p>
          )}
        </SectionCard>

        <SectionCard title="Simulator workflow" subtitle="No physical hardware required">
          <ol className="steps">
            <li>
              <span className="steps__number">1</span>
              <div>
                <strong>Register a device</strong>
                <p>Settings issues a device token once; copy it for the simulator.</p>
              </div>
            </li>
            <li>
              <span className="steps__number">2</span>
              <div>
                <strong>Start a recording</strong>
                <p>Django creates the session and pushes it to FastAPI.</p>
              </div>
            </li>
            <li>
              <span className="steps__number">3</span>
              <div>
                <strong>Run the simulator, then analyse</strong>
                <p>
                  <code>python -m simulator --session-id … --device-token … --ecg</code>
                </p>
              </div>
            </li>
          </ol>
        </SectionCard>
      </div>

      {selected && (
        <StartSessionDialog
          patient={selected}
          devices={devices.data ?? []}
          onClose={() => setSelected(null)}
          onStarted={started}
        />
      )}

      {registering && (
        <PatientForm
          onClose={() => setRegistering(false)}
          onSaved={(patient) => {
            setRegistering(false)
            setSelected(patient)
          }}
        />
      )}
    </>
  )
}
