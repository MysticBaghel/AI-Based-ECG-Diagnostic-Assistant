import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { healthApi } from '@/shared/api/health'
import { useResource } from '@/shared/api/useResource'
import type { Patient, Session } from '@/shared/types'
import { Icon } from '@/shared/icons/Icon'
import { ErrorBanner, PageHeader, StatCard } from '@/shared/ui'
import { PatientForm } from '@/features/patients/components/PatientForm'
import { StartSessionDialog } from '@/features/patients/components/StartSessionDialog'
import { useDevices, useDeviceStatus } from '@/features/devices/hooks/useDevices'
import { useSessions } from '@/features/sessions/hooks/useSessions'
import { DeviceHeartbeatCard } from '../components/DeviceHeartbeatCard'
import { PatientSearchCard } from '../components/PatientSearchCard'
import { RecordingsCard } from '../components/RecordingsCard'
import { SimulatorStepsCard } from '../components/SimulatorStepsCard'
import { SystemStatusCard } from '../components/SystemStatusCard'

export function DashboardPage() {
  const navigate = useNavigate()
  const sessions = useSessions()
  const devices = useDevices()
  const status = useDeviceStatus()
  const service = useResource(
    'dashboard-services',
    async () => {
      const [django, fastapi] = await Promise.allSettled([
        healthApi.django(),
        healthApi.telemetry(),
      ])
      return {
        django: django.status === 'fulfilled',
        fastapi: fastapi.status === 'fulfilled',
        analysis: fastapi.status === 'fulfilled' ? fastapi.value.analysis : undefined,
      }
    },
    { pollMs: 30_000 },
  )

  const [selected, setSelected] = useState<Patient | null>(null)
  const [registering, setRegistering] = useState(false)

  const allSessions = useMemo(() => sessions.data ?? [], [sessions.data])
  const active = useMemo(
    () => allSessions.filter((session) => session.status === 'active'),
    [allSessions],
  )
  const analysed = allSessions.filter(
    (session) => session.analysis_status === 'completed',
  ).length
  const reportCount = allSessions.reduce((sum, session) => sum + session.report_count, 0)
  const online = (status.data?.devices ?? []).filter((device) => device.online).length
  const recent = allSessions.slice(0, 6)
  const loading = sessions.loading && devices.loading
  const error = sessions.error ?? devices.error ?? status.error

  function started(session: Session) {
    setSelected(null)
    navigate(`/monitor/${session.id}`)
  }

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Overview of patients, recordings, analyses and reports. Start a new ECG or continue from a patient profile."
        actions={
          <button
            type="button"
            className="button button--primary"
            onClick={() => setRegistering(true)}
          >
            <Icon name="plus" size={16} />
            Add Patient
          </button>
        }
      />

      {error && (
        <ErrorBanner
          message={error}
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
        <StatCard icon="shield" label="Reports generated" value={reportCount} hint="stored PDFs" />
        <StatCard
          icon="wifi"
          label="Devices online"
          value={online}
          hint={`of ${devices.data?.length ?? 0} registered`}
          tone={online > 0 ? 'ok' : 'warn'}
        />
      </div>

      <div className="dashboard-grid">
        <PatientSearchCard
          active={active}
          onSelect={setSelected}
          onRegister={() => setRegistering(true)}
        />
        <SystemStatusCard
          service={service.data}
          deviceCount={devices.data?.length ?? 0}
        />
      </div>

      <RecordingsCard
        sessions={allSessions}
        recent={recent}
        loading={loading}
        refreshing={sessions.refreshing}
        error={sessions.error}
        onRefresh={sessions.refresh}
      />

      <div className="dashboard-grid dashboard-grid--narrow">
        <DeviceHeartbeatCard status={status.data} devices={devices.data ?? []} />
        <SimulatorStepsCard />
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
