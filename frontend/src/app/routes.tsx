import { lazy } from 'react'
import { Route, Routes } from 'react-router-dom'

import { RequireAuth } from '@/features/auth/Guards'
import { AppShell } from './shell/AppShell'

const LoginPage = lazy(() =>
  import('@/features/auth/pages/LoginPage').then((module) => ({ default: module.LoginPage })),
)
const DashboardPage = lazy(() =>
  import('@/features/dashboard/pages/DashboardPage').then((module) => ({
    default: module.DashboardPage,
  })),
)
const PatientsPage = lazy(() =>
  import('@/features/patients/pages/PatientsPage').then((module) => ({
    default: module.PatientsPage,
  })),
)
const PatientProfilePage = lazy(() =>
  import('@/features/patients/pages/PatientProfilePage').then((module) => ({
    default: module.PatientProfilePage,
  })),
)
const MonitorPage = lazy(() =>
  import('@/features/monitor/pages/MonitorPage').then((module) => ({
    default: module.MonitorPage,
  })),
)
const AnalysisPage = lazy(() =>
  import('@/features/analysis/pages/AnalysisPage').then((module) => ({
    default: module.AnalysisPage,
  })),
)
const ReportsPage = lazy(() =>
  import('@/features/reports/pages/ReportsPage').then((module) => ({
    default: module.ReportsPage,
  })),
)
const DevicesPage = lazy(() =>
  import('@/features/devices/pages/DevicesPage').then((module) => ({
    default: module.DevicesPage,
  })),
)
const SettingsPage = lazy(() =>
  import('@/features/settings/pages/SettingsPage').then((module) => ({
    default: module.SettingsPage,
  })),
)
const NotFoundPage = lazy(() =>
  import('./NotFoundPage').then((module) => ({ default: module.NotFoundPage })),
)

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<AppShell />}>
          <Route index element={<DashboardPage />} />
          <Route path="patients" element={<PatientsPage />} />
          <Route path="patients/:patientId" element={<PatientProfilePage />} />
          <Route path="monitor" element={<MonitorPage />} />
          <Route path="monitor/:sessionId" element={<MonitorPage />} />
          <Route path="reports" element={<ReportsPage />} />
          <Route path="sessions/:sessionId" element={<AnalysisPage />} />
          <Route path="devices" element={<DevicesPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Route>
    </Routes>
  )
}
