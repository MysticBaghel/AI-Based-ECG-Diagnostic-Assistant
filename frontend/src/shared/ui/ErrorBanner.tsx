import { Icon } from '@/shared/icons/Icon'

export function ErrorBanner({
  message,
  onRetry,
}: {
  message: string
  onRetry?: () => void
}) {
  return (
    <div className="banner banner--error" role="alert">
      <Icon name="alert" size={18} />
      <div className="banner__body">
        <strong>Something needs attention</strong>
        <span>{message}</span>
      </div>
      {onRetry && (
        <button type="button" className="button button--ghost button--sm" onClick={onRetry}>
          <Icon name="refresh" size={15} />
          Retry
        </button>
      )}
    </div>
  )
}
