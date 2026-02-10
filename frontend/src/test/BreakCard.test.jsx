import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { FavoritesProvider } from '../context/FavoritesContext'
import BreakCard from '../components/BreakCard'
import { describe, it, expect } from 'vitest'

const mockBreak = {
  id: 1,
  name: 'Bells Beach',
  state: 'Victoria',
  skill_level: 'advanced',
}

function renderCard(breakData = mockBreak) {
  return render(
    <MemoryRouter>
      <FavoritesProvider>
        <BreakCard breakData={breakData} />
      </FavoritesProvider>
    </MemoryRouter>
  )
}

describe('BreakCard', () => {
  it('renders break name and state', () => {
    renderCard()
    expect(screen.getByText('Bells Beach')).toBeInTheDocument()
    expect(screen.getByText('Victoria')).toBeInTheDocument()
  })

  it('renders skill level tag', () => {
    renderCard()
    expect(screen.getByText('Advanced')).toBeInTheDocument()
  })

  it('renders as a link to the break detail', () => {
    renderCard()
    const link = screen.getByRole('link')
    expect(link).toHaveAttribute('href', '/Victoria/Bells%20Beach')
  })

  it('renders favorite button', () => {
    renderCard()
    expect(screen.getByLabelText('Add to favorites')).toBeInTheDocument()
  })
})
