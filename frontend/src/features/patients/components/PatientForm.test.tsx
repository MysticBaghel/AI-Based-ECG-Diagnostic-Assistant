import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { PatientForm } from './PatientForm'

vi.mock('@/features/patients/api', () => ({
  patientsApi: {
    create: vi.fn(),
    update: vi.fn(),
  },
}))

describe('PatientForm', () => {
  it('validates the full name before calling the API', async () => {
    const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <PatientForm onClose={() => undefined} onSaved={() => undefined} />
      </QueryClientProvider>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Register patient' }))

    await waitFor(() => {
      expect(screen.getByText("Enter the patient's full name.")).toBeInTheDocument()
    })
  })
})
