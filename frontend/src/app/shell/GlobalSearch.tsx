import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { usePatients } from '@/features/patients/hooks/usePatients'
import { Icon } from '@/shared/icons/Icon'
import { initials } from '@/shared/lib/format'

export function GlobalSearch() {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const patients = usePatients(query, query.trim().length >= 2)
  const results = (patients.data ?? []).slice(0, 5)
  const hostRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function onClick(event: MouseEvent) {
      if (!hostRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  function choose(patientId: number) {
    setQuery('')
    setOpen(false)
    navigate(`/patients/${patientId}`)
  }

  return (
    <div className="topbar-search" ref={hostRef}>
      <Icon name="search" size={17} />
      <input
        value={query}
        onChange={(event) => {
          setQuery(event.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            if (results[0]) choose(results[0].id)
            else if (query.trim()) {
              setOpen(false)
              navigate(`/patients?q=${encodeURIComponent(query.trim())}`)
            }
          }
          if (event.key === 'Escape') setOpen(false)
        }}
        placeholder="Search patient by name, phone or ID..."
        aria-label="Search patients"
      />
      {open && query.trim().length >= 2 && (
        <div className="topbar-search__results">
          {patients.loading ? (
            <span className="topbar-search__empty">Searching…</span>
          ) : results.length === 0 ? (
            <span className="topbar-search__empty">No patient matches “{query}”.</span>
          ) : (
            results.map((patient) => (
              <button
                type="button"
                key={patient.id}
                className="topbar-search__result"
                onClick={() => choose(patient.id)}
              >
                <span className="avatar avatar--sm">{initials(patient.full_name)}</span>
                <span>
                  <strong>{patient.full_name}</strong>
                  <small>
                    {patient.patient_id} · {patient.phone || 'no phone'}
                  </small>
                </span>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  )
}
