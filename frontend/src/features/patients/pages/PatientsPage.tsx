import { useMemo, useState, type FormEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import type { Patient, Session } from '@/shared/types'
import { Icon } from '@/shared/icons/Icon'
import { EmptyState, ErrorBanner, PageHeader, Spinner } from '@/shared/ui'
import { usePatients } from '@/features/patients/hooks/usePatients'
import { useDevices } from '@/features/devices/hooks/useDevices'
import { useSessions } from '@/features/sessions/hooks/useSessions'
import { useNow } from '@/shared/hooks/useNow'
import { PatientFilters, type PatientSearchField, type PatientTab } from '../components/PatientFilters'
import { PatientForm } from '../components/PatientForm'
import { PatientPagination } from '../components/PatientPagination'
import { PatientTable } from '../components/PatientTable'
import { StartSessionDialog } from '../components/StartSessionDialog'
import { SimulateCsvDialog } from '@/features/simulator/SimulateCsvDialog'

const PAGE_SIZE = 8

function latestByPatient(sessions: Session[]): Map<number, Session> {
  const map = new Map<number, Session>()
  for (const session of sessions) {
    if (!map.has(session.patient)) map.set(session.patient, session)
  }
  return map
}

function initialField(query: string): PatientSearchField {
  const value = query.trim()
  if (/^[+\d\s()-]+$/.test(value) && value.replace(/\D/g, '').length >= 3) return 'phone'
  if (value.toUpperCase().startsWith('PT-')) return 'id'
  return 'name'
}

export function PatientsPage() {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const initialQuery = params.get('q') ?? ''
  const [searchInput, setSearchInput] = useState(initialQuery)
  const [query, setQuery] = useState(initialQuery)
  const [field, setField] = useState<PatientSearchField>(() => initialField(initialQuery))
  const [tab, setTab] = useState<PatientTab>('all')
  const [page, setPage] = useState(1)
  const [registering, setRegistering] = useState(false)
  const [starting, setStarting] = useState<Patient | null>(null)
  const [simulating, setSimulating] = useState(false)

  const patients = usePatients(query)
  const sessions = useSessions()
  const devices = useDevices()
  const now = useNow(60_000)
  const latest = useMemo(() => latestByPatient(sessions.data ?? []), [sessions.data])
  const activeDeviceIds = useMemo(
    () =>
      new Set(
        (sessions.data ?? [])
          .filter((session) => session.status === 'active')
          .map((session) => session.device),
      ),
    [sessions.data],
  )

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase()
    let rows = patients.data ?? []

    if (needle) {
      rows = rows.filter((patient) => {
        if (field === 'phone') return patient.phone.toLowerCase().includes(needle)
        if (field === 'id') return patient.patient_id.toLowerCase().includes(needle)
        return patient.full_name.toLowerCase().includes(needle)
      })
    }

    if (tab === 'recent') {
      const cutoff = now.getTime() - 30 * 24 * 60 * 60 * 1000
      rows = rows.filter((patient) => Date.parse(patient.created_at) >= cutoff)
    }

    return [...rows].sort((a, b) => a.full_name.localeCompare(b.full_name))
  }, [patients.data, query, field, tab, now])

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const safePage = Math.min(page, pageCount)
  const pageRows = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE)

  function applySearch(event?: FormEvent) {
    event?.preventDefault()
    const next = searchInput.trim()
    setQuery(next)
    setPage(1)
    setParams(next ? { q: next } : {}, { replace: true })
  }

  function clearSearch() {
    setSearchInput('')
    setQuery('')
    setPage(1)
    setParams({}, { replace: true })
  }

  function changeTab(next: PatientTab) {
    setTab(next)
    setPage(1)
  }

  function changeField(next: PatientSearchField) {
    setField(next)
    setPage(1)
  }

  const error = patients.error ?? sessions.error ?? devices.error

  return (
    <>
      <PageHeader
        title="Patients"
        description="Manage patient records and view their ECG history"
        actions={
          <div className="button-row">
            <button
              type="button"
              className="button button--ghost"
              onClick={() => setSimulating(true)}
              title="Create a demo patient and replay a CSV into a live recording"
            >
              <Icon name="activity" size={16} />
              Simulate
            </button>
            <button
              type="button"
              className="button button--primary"
              onClick={() => setRegistering(true)}
            >
              <Icon name="plus" size={16} />
              Add Patient
            </button>
          </div>
        }
      />

      {error && (
        <ErrorBanner
          message={error}
          onRetry={() => {
            patients.refresh()
            sessions.refresh()
            devices.refresh()
          }}
        />
      )}

      <PatientFilters
        tab={tab}
        field={field}
        searchInput={searchInput}
        query={query}
        onTab={changeTab}
        onField={changeField}
        onSearchInput={setSearchInput}
        onSearch={applySearch}
        onClear={clearSearch}
      />

      {patients.loading ? (
        <Spinner label="Loading patients…" />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon="users"
          title={query || tab === 'recent' ? 'No patient matches' : 'No patients registered'}
          description={
            query || tab === 'recent'
              ? 'Clear the filter or search by a different name, phone number or patient ID.'
              : 'Register the first patient. A permanent patient ID is generated automatically; the patient does not need a login account.'
          }
          action={
            <button
              type="button"
              className="button button--primary"
              onClick={() => setRegistering(true)}
            >
              Add a patient
            </button>
          }
        />
      ) : (
        <section className="panel">
          <PatientTable
            rows={pageRows}
            latest={latest}
            onStart={setStarting}
            onOpenSession={(session) =>
              navigate(
                session.status === 'active'
                  ? `/monitor/${session.id}`
                  : `/sessions/${session.id}`,
              )
            }
          />
          <PatientPagination
            total={filtered.length}
            page={safePage}
            pageCount={pageCount}
            pageSize={PAGE_SIZE}
            onPage={setPage}
          />
        </section>
      )}

      <p className="muted small">
        <Icon name="shield" size={13} /> Patient records are visible to authenticated operators.
        Duplicate phone numbers trigger a warning before a new record is created.
      </p>

      {registering && (
        <PatientForm
          onClose={() => setRegistering(false)}
          onSaved={(patient) => {
            setRegistering(false)
            patients.refresh()
            navigate(`/patients/${patient.id}`)
          }}
        />
      )}

      {starting && (
        <StartSessionDialog
          patient={starting}
          devices={devices.data ?? []}
          onClose={() => setStarting(null)}
          onStarted={(session) => {
            setStarting(null)
            navigate(`/monitor/${session.id}`)
          }}
        />
      )}

      {simulating && (
        <SimulateCsvDialog
          devices={devices.data ?? []}
          activeDeviceIds={activeDeviceIds}
          onClose={() => setSimulating(false)}
          onStarted={(session) => {
            setSimulating(false)
            navigate(`/monitor/${session.id}`)
          }}
        />
      )}
    </>
  )
}
