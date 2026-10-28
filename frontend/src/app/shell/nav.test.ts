import { describe, expect, it } from 'vitest'

import { isNavActive, NAV, pageTitle } from './nav'

describe('shell navigation', () => {
  it('keeps Reports active for both report lists and analysis pages', () => {
    const reports = NAV.find((item) => item.label === 'Reports')
    expect(reports).toBeDefined()
    expect(isNavActive(reports!, '/reports')).toBe(true)
    expect(isNavActive(reports!, '/sessions/abc')).toBe(true)
    expect(isNavActive(reports!, '/patients')).toBe(false)
  })

  it('derives a useful page title', () => {
    expect(pageTitle('/')).toBe('Dashboard')
    expect(pageTitle('/monitor/abc')).toBe('ECG Monitor')
    expect(pageTitle('/patients/1')).toBe('Patient Profile')
  })
})
