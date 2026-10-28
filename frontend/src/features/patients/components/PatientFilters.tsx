import type { FormEvent } from 'react'

import { Icon } from '@/shared/icons/Icon'

export type PatientTab = 'all' | 'recent'
export type PatientSearchField = 'name' | 'phone' | 'id'

export function PatientFilters({
  tab,
  field,
  searchInput,
  query,
  onTab,
  onField,
  onSearchInput,
  onSearch,
  onClear,
}: {
  tab: PatientTab
  field: PatientSearchField
  searchInput: string
  query: string
  onTab: (tab: PatientTab) => void
  onField: (field: PatientSearchField) => void
  onSearchInput: (value: string) => void
  onSearch: (event?: FormEvent) => void
  onClear: () => void
}) {
  return (
    <form className="table-toolbar" onSubmit={onSearch}>
      <div className="tabs" role="tablist" aria-label="Patient filters">
        <button
          type="button"
          className={`tab${tab === 'all' ? ' tab--active' : ''}`}
          onClick={() => onTab('all')}
        >
          All Patients
        </button>
        <button
          type="button"
          className={`tab${tab === 'recent' ? ' tab--active' : ''}`}
          onClick={() => onTab('recent')}
        >
          Recent
        </button>
      </div>

      <span className="table-toolbar__spacer" />

      <select
        className="filter-select"
        value={field}
        onChange={(event) => onField(event.target.value as PatientSearchField)}
        aria-label="Search field"
      >
        <option value="name">Name</option>
        <option value="phone">Phone</option>
        <option value="id">Patient ID</option>
      </select>

      <label className="table-search">
        <Icon name="search" size={15} />
        <input
          value={searchInput}
          onChange={(event) => onSearchInput(event.target.value)}
          placeholder={field === 'phone' ? '+91 98765 43210' : field === 'id' ? 'PT-…' : 'Search...'}
          aria-label="Search patients"
        />
      </label>
      <button type="submit" className="button button--primary button--sm">
        Search
      </button>
      {query && (
        <button type="button" className="button button--ghost button--sm" onClick={onClear}>
          Clear
        </button>
      )}
    </form>
  )
}
