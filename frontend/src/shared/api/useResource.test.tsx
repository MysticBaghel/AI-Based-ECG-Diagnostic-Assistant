import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { useResource } from './useResource'

function Harness({ value }: { value: number }) {
  const resource = useResource(
    `probe:${value}`,
    () =>
      new Promise<number>((resolve) => {
        setTimeout(() => resolve(value), 25)
      }),
    { pollMs: 0 },
  )
  return (
    <div data-testid="out">
      {resource.loading ? 'loading' : resource.data === null ? 'empty' : String(resource.data)}
    </div>
  )
}

function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

describe('useResource', () => {
  it('does not show the previous key data while the next one loads', async () => {
    // The waveform player relies on this: a window change must report
    // `loading` instead of keeping the old samples on screen.
    const client = makeClient()
    const view = render(
      <QueryClientProvider client={client}>
        <Harness value={1} />
      </QueryClientProvider>,
    )

    expect(screen.getByTestId('out')).toHaveTextContent('loading')
    await waitFor(() => expect(screen.getByTestId('out')).toHaveTextContent('1'))

    // Same client: this is the real transition, not a fresh cache.
    view.rerender(
      <QueryClientProvider client={client}>
        <Harness value={2} />
      </QueryClientProvider>,
    )

    expect(screen.getByTestId('out')).toHaveTextContent('loading')
    await waitFor(() => expect(screen.getByTestId('out')).toHaveTextContent('2'))
  })
})
