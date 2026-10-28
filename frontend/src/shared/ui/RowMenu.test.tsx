import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { RowMenu } from './RowMenu'

describe('RowMenu', () => {
  it('closes when clicking outside and with Escape', async () => {
    const user = userEvent.setup()
    render(
      <RowMenu label="Actions for patient">
        <button type="button">View profile</button>
      </RowMenu>,
    )

    const trigger = screen.getByLabelText('Actions for patient')
    await user.click(trigger)
    expect(screen.getByText('View profile')).toBeInTheDocument()

    await user.click(document.body)
    expect(screen.queryByText('View profile')).not.toBeInTheDocument()

    await user.click(trigger)
    expect(screen.getByText('View profile')).toBeInTheDocument()
    await user.keyboard('{Escape}')
    expect(screen.queryByText('View profile')).not.toBeInTheDocument()
  })
})
