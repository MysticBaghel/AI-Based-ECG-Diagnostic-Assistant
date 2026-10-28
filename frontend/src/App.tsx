import { Route, Routes } from 'react-router-dom'

import { AuthProvider } from './auth/AuthContext'
import { RequireAuth, RoleGate } from './auth/Guards'
import { AppShell } from './components/AppShell'
import { DashboardPage } from './pages/DashboardPage'
import { DevicesPage } from './pages/DevicesPage'
import { LivePage } from './pages/LivePage'
import { LoginPage } from './pages/LoginPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { PatientsPage } from './pages/PatientsPage'
import { RecordingPage } from './pages/RecordingPage'
import { SessionsPage } from './pages/SessionsPage'

function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />

        <Route element={<RequireAuth />}>
          <Route element={<AppShell />}>
            <Route index element={<DashboardPage />} />
            <Route path="patients" element={<PatientsPage />} />
            <Route
              path="devices"
              element={
                <RoleGate allow={['doctor', 'admin']}>
                  <DevicesPage />
                </RoleGate>
              }
            />
            <Route path="sessions" element={<SessionsPage />} />
            <Route path="sessions/:sessionId" element={<RecordingPage />} />
            <Route path="live" element={<LivePage />} />
            <Route path="live/:sessionId" element={<LivePage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Route>
      </Routes>
    </AuthProvider>
  )
}

export default App
