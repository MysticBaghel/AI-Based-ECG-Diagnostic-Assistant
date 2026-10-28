import { useEffect, useMemo, useRef, useState } from 'react'

import { ApiError } from '@/shared/api/http'
import { devicesApi } from '@/features/devices/api'
import { patientsApi } from '@/features/patients/api'
import { sessionsApi } from '@/features/sessions/api'
import {
  replayCsv,
  simulationScenarios,
  startScenario,
  type ScenarioInfo,
} from '@/features/simulator/api'
import { Icon } from '@/shared/icons/Icon'
import type { Device, Session } from '@/shared/types'
import { ErrorBanner, Modal, Notice } from '@/shared/ui'

const MAX_BYTES = 20 * 1024 * 1024
const MIN_RATE_HZ = 100
const MAX_RATE_HZ = 2000
const DURATIONS = [
  { value: 30, label: '30 seconds' },
  { value: 60, label: '1 minute' },
  { value: 120, label: '2 minutes' },
  { value: 300, label: '5 minutes' },
]

/** Used until `/simulator/scenarios` answers, so the dialog is never empty. */
const FALLBACK_SCENARIOS: ScenarioInfo[] = [
  {
    key: 'normal_sinus',
    label: 'Normal sinus rhythm',
    description: 'Regular 72 bpm with a visible P wave.',
    heart_rate_bpm: 72,
  },
  {
    key: 'sinus_bradycardia',
    label: 'Sinus bradycardia',
    description: 'Slow but regular, around 46 bpm.',
    heart_rate_bpm: 46,
  },
  {
    key: 'sinus_tachycardia',
    label: 'Sinus tachycardia',
    description: 'Fast and regular, around 128 bpm.',
    heart_rate_bpm: 128,
  },
  {
    key: 'atrial_fibrillation',
    label: 'Atrial fibrillation',
    description: 'Irregular RR intervals with no P wave.',
    heart_rate_bpm: 96,
  },
  {
    key: 'frequent_pvc',
    label: 'Frequent PVCs',
    description: 'Every third beat is a wide ectopic complex.',
    heart_rate_bpm: 74,
  },
]

type Mode = 'scenario' | 'csv'

function defaultName(): string {
  return `Simulated patient ${new Date().toLocaleString(undefined, {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })}`
}

/**
 * One dialog for the whole demo pipeline: demo patient -> recording -> stream.
 *
 * The stream can be a built-in scenario (no file, so the graph is one click
 * away) or an uploaded CSV. The server does the streaming, so the graph keeps
 * filling after this dialog closes and the monitor page takes over.
 */
export function SimulateCsvDialog({
  devices,
  activeDeviceIds,
  onClose,
  onStarted,
}: {
  devices: Device[]
  activeDeviceIds: Set<string>
  onClose: () => void
  onStarted: (session: Session) => void
}) {
  const [mode, setMode] = useState<Mode>('scenario')
  const [scenarios, setScenarios] = useState<ScenarioInfo[]>(FALLBACK_SCENARIOS)
  const [scenarioKey, setScenarioKey] = useState('normal_sinus')
  const [scenarioSeconds, setScenarioSeconds] = useState(60)
  const [fullName, setFullName] = useState(defaultName)
  const [file, setFile] = useState<File | null>(null)
  const [rateHz, setRateHz] = useState(200)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [created, setCreated] = useState<Session | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  useEffect(() => {
    let alive = true
    simulationScenarios()
      .then((list) => {
        if (alive && list.length > 0) setScenarios(list)
      })
      .catch(() => {
        // The fallback list is enough to start; the server is the authority.
      })
    return () => {
      alive = false
    }
  }, [])

  const simulatorDevices = useMemo(
    () => devices.filter((device) => /simulat/i.test(device.name)),
    [devices],
  )
  const selectedScenario = scenarios.find((item) => item.key === scenarioKey) ?? scenarios[0]

  function chooseFile(next: File | null) {
    setError(null)
    if (next && next.size > MAX_BYTES) {
      setError(`That file is ${(next.size / (1024 * 1024)).toFixed(1)} MB; the limit is 20 MB.`)
      setFile(null)
      return
    }
    setFile(next)
  }

  async function submit() {
    if (mode === 'csv' && !file) return
    if (mode === 'csv' && (rateHz < MIN_RATE_HZ || rateHz > MAX_RATE_HZ)) {
      setError(`The sample rate must be between ${MIN_RATE_HZ} and ${MAX_RATE_HZ} Hz.`)
      return
    }
    setBusy(true)
    setError(null)

    let session = created
    try {
      if (session === null) {
        const patient = await patientsApi.create({
          full_name: fullName.trim(),
          notes: 'Demo record created by the in-site simulator.',
        })

        // Reuse an idle simulator device; a device can only have one active
        // recording, and the seed device may already be in use by the CLI.
        let device = simulatorDevices.find(
          (candidate) =>
            candidate.status === 'active' && !activeDeviceIds.has(candidate.id),
        )
        if (!device) {
          device = await devicesApi.create('In-site simulator')
        }

        session = await sessionsApi.start(patient.id, device.id)
        setCreated(session)
      }

      if (mode === 'scenario') {
        await startScenario(session.id, scenarioKey, scenarioSeconds)
      } else if (file) {
        await replayCsv(session.id, file, rateHz)
      }
      onStarted(session)
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : 'Could not start the stream. Is FastAPI running?',
      )
      setBusy(false)
      if (session) {
        // The recording exists, so a retry must not create a second patient.
        setCreated(session)
      }
    }
  }

  return (
    <Modal
      title="Simulate a patient"
      subtitle="Creates a demo patient, starts a recording and streams data live"
      onClose={onClose}
      footer={
        <>
          <button type="button" className="button button--ghost" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button
            type="button"
            className="button button--primary"
            onClick={() => void submit()}
            disabled={
              busy ||
              (!created && !fullName.trim()) ||
              (mode === 'csv' && !file)
            }
          >
            {busy
              ? 'Starting…'
              : mode === 'scenario'
                ? 'Create patient and stream'
                : created
                  ? 'Upload and replay'
                  : 'Create patient and replay'}
            {!busy && <Icon name="play" size={15} />}
          </button>
        </>
      }
    >
      <div className="stack">
        <Notice tone="info" icon="activity">
          The signal is streamed into a real recording one second at a time, so the live
          chart fills as if a device were connected. Stop the recording afterwards to run
          the analysis.
        </Notice>

        {error && <ErrorBanner message={error} />}

        {created && (
          <p className="small muted">
            Demo patient and recording already created (session{' '}
            <code>{created.id.slice(0, 8)}</code>). Retrying only starts the stream again.
          </p>
        )}

        <label className="field">
          <span>Patient name</span>
          <input
            value={fullName}
            onChange={(event) => setFullName(event.target.value)}
            disabled={Boolean(created) || busy}
            maxLength={200}
          />
          <small>A new demo record is registered in the patient registry.</small>
        </label>

        <label className="field">
          <span>Data source</span>
          <select
            value={mode}
            onChange={(event) => setMode(event.target.value as Mode)}
            disabled={busy}
          >
            <option value="scenario">Generated demo rhythm (no file)</option>
            <option value="csv">Upload a CSV file</option>
          </select>
        </label>

        {mode === 'scenario' ? (
          <>
            <label className="field">
              <span>Rhythm</span>
              <select
                value={scenarioKey}
                onChange={(event) => setScenarioKey(event.target.value)}
                disabled={busy}
              >
                {scenarios.map((scenario) => (
                  <option key={scenario.key} value={scenario.key}>
                    {scenario.label}
                  </option>
                ))}
              </select>
              {selectedScenario && <small>{selectedScenario.description}</small>}
            </label>

            <label className="field">
              <span>Duration</span>
              <select
                value={scenarioSeconds}
                onChange={(event) => setScenarioSeconds(Number(event.target.value))}
                disabled={busy}
              >
                {DURATIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          </>
        ) : (
          <>
            <label className="field">
              <span>ECG file (CSV)</span>
              <input
                ref={fileInput}
                type="file"
                accept=".csv,.txt,text/csv,text/plain"
                onChange={(event) => chooseFile(event.target.files?.[0] ?? null)}
                disabled={busy}
              />
              <small>
                One voltage column, or <code>time,voltage</code>. A header row is optional;
                the server keeps the file&apos;s own rate (100–2000 Hz).
              </small>
            </label>

            <label className="field">
              <span>Sample rate — only for files without a time column</span>
              <input
                type="number"
                min={MIN_RATE_HZ}
                max={MAX_RATE_HZ}
                step={1}
                value={rateHz}
                onChange={(event) => setRateHz(Number(event.target.value))}
                disabled={busy}
                aria-invalid={rateHz < MIN_RATE_HZ || rateHz > MAX_RATE_HZ}
              />
              <small>
                Ignored when the file has a <code>time</code> column: the server reads the
                rate from it and keeps it (100–2000 Hz), so a 300 Hz file stays at 300 Hz.
              </small>
            </label>
          </>
        )}

        {simulatorDevices.length > 0 && (
          <p className="small muted">
            <Icon name="devices" size={13} /> Available simulator device:{' '}
            {simulatorDevices.find(
              (candidate) =>
                candidate.status === 'active' && !activeDeviceIds.has(candidate.id),
            )?.name ?? 'all busy — a new one will be registered'}
          </p>
        )}
      </div>
    </Modal>
  )
}
