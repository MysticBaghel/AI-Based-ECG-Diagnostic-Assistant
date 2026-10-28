import { Component, type ErrorInfo, type ReactNode } from 'react'

import { Icon } from '@/shared/icons/Icon'

interface State {
  error: Error | null
}

export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Unhandled UI error', error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="splash">
          <span className="splash__mark">
            <Icon name="alert" size={28} />
          </span>
          <h1>Something went wrong</h1>
          <p>{this.state.error.message}</p>
          <button
            type="button"
            className="button button--primary"
            onClick={() => this.setState({ error: null })}
          >
            Try again
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
