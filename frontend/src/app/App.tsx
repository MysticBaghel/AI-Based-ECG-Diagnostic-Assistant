import { Suspense } from 'react'

import { Spinner } from '@/shared/ui'
import { ErrorBoundary } from './ErrorBoundary'
import { AppProviders } from './providers'
import { AppRoutes } from './routes'

function RouteFallback() {
  return (
    <div className="splash">
      <span className="splash__mark">
        <span className="spinner__ring" />
      </span>
      <Spinner label="Loading PulseTrace…" />
    </div>
  )
}

function App() {
  return (
    <AppProviders>
      <ErrorBoundary>
        <Suspense fallback={<RouteFallback />}>
          <AppRoutes />
        </Suspense>
      </ErrorBoundary>
    </AppProviders>
  )
}

export default App
