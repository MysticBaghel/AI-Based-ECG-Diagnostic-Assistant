import type { IconName } from '@/shared/icons/Icon'

export interface NavItem {
  to: string
  label: string
  icon: IconName
  match?: string[]
  exact?: boolean
}

export const NAV: NavItem[] = [
  { to: '/', label: 'Dashboard', icon: 'dashboard', exact: true },
  { to: '/patients', label: 'Patients', icon: 'users', match: ['/patients'] },
  { to: '/monitor', label: 'ECG Monitor', icon: 'activity', match: ['/monitor'] },
  {
    to: '/reports',
    label: 'Reports',
    icon: 'file-text',
    match: ['/reports', '/sessions'],
  },
  { to: '/devices', label: 'Devices', icon: 'devices', match: ['/devices'] },
  { to: '/settings', label: 'Settings', icon: 'settings', match: ['/settings'] },
]

export function pageTitle(pathname: string): string {
  if (pathname.startsWith('/monitor')) return 'ECG Monitor'
  if (pathname.startsWith('/sessions/')) return 'ECG Analysis & Report'
  if (pathname.startsWith('/reports')) return 'Reports'
  if (pathname.startsWith('/patients/')) return 'Patient Profile'
  if (pathname.startsWith('/patients')) return 'Patients'
  if (pathname.startsWith('/devices')) return 'Devices'
  if (pathname.startsWith('/settings')) return 'Settings'
  return 'Dashboard'
}

export function isNavActive(item: NavItem, pathname: string): boolean {
  if (item.exact) return pathname === item.to
  if (item.to === '/patients') return pathname.startsWith('/patients')
  return (item.match ?? [item.to]).some((prefix) => pathname.startsWith(prefix))
}
