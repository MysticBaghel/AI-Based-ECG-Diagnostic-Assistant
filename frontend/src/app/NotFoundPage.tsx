import { Link } from 'react-router-dom'

import { Icon } from '@/shared/icons/Icon'
import { EmptyState } from '@/shared/ui'

export function NotFoundPage() {
  return (
    <EmptyState
      icon="alert"
      title="Page not found"
      description="That route does not exist in the Phase 4 dashboard."
      action={
        <Link to="/" className="button button--primary">
          <Icon name="dashboard" size={15} />
          Back to the dashboard
        </Link>
      }
    />
  )
}
