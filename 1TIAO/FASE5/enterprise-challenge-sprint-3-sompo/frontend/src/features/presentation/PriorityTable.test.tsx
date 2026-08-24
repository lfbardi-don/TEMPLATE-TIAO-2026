import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { PriorityTable } from './PriorityTable'
import { portfolioFixture } from '../../test/fixtures'
import { portfolioSchema } from '../../lib/api-contracts'

describe('PriorityTable', () => {
  it('preserva a posição da API e cria links pelos UUIDs', () => {
    const firstPriority = portfolioFixture.priorities[0]
    const orderedPortfolio = portfolioSchema.parse({
      ...portfolioFixture,
      priorities: [
        {
          ...firstPriority,
          rank: 2,
          tractor: {
            ...firstPriority.tractor,
            id: '33333333-3333-4333-8333-333333333333',
            external_id: 'FENDT-314-02',
            display_name: 'Trator Sul',
          },
        },
        firstPriority,
      ],
    })
    const { container } = render(<MemoryRouter><PriorityTable priorities={orderedPortfolio.priorities} /></MemoryRouter>)

    const desktopRows = screen.getAllByRole('row').slice(1)
    expect(desktopRows).toHaveLength(2)
    expect(within(desktopRows[0]).getByText('2')).toBeInTheDocument()
    expect(within(desktopRows[0]).getByRole('link', { name: 'Trator Sul (FENDT-314-02)' })).toHaveAttribute('href', '/tratores/33333333-3333-4333-8333-333333333333')
    expect(within(desktopRows[1]).getByText('1')).toBeInTheDocument()
    expect(within(desktopRows[1]).getByRole('link', { name: 'Trator Norte (FENDT-314-01)' })).toHaveAttribute('href', '/tratores/22222222-2222-4222-8222-222222222222')

    const mobileCards = Array.from(container.querySelectorAll<HTMLElement>('.priority-card'))
    expect(mobileCards).toHaveLength(2)
    expect(within(mobileCards[0]).getByText('Prioridade 2')).toBeInTheDocument()
    expect(within(mobileCards[0]).getByRole('link', { name: 'Trator Sul (FENDT-314-02)' })).toHaveAttribute('href', '/tratores/33333333-3333-4333-8333-333333333333')
    expect(within(mobileCards[1]).getByText('Prioridade 1')).toBeInTheDocument()
    expect(within(mobileCards[1]).getByRole('link', { name: 'Trator Norte (FENDT-314-01)' })).toHaveAttribute('href', '/tratores/22222222-2222-4222-8222-222222222222')

    expect(screen.getAllByText(/baixa rotação sob carga/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/50 \/ 100/).length).toBeGreaterThan(0)
    expect(screen.getByText('Ordem devolvida pela API. A fila orienta revisão preventiva e não diagnostica falha.')).toBeInTheDocument()
    for (const group of ['Máquina e frota', 'Exposição relativa', 'Base observada', 'Evidências', 'Ação']) {
      expect(screen.getAllByText(group)).toHaveLength(3)
    }
  })

  it('não sugere revisão por um score inexistente', () => {
    const noDataPortfolio = portfolioSchema.parse({
      ...portfolioFixture,
      priorities: portfolioFixture.priorities.map((priority) => ({
        ...priority,
        scores: {
          ...priority.scores,
          '30_days': {
            ...priority.scores['30_days'],
            status: 'NO_DATA',
            physical_exposure_seconds_per_hour: null,
            alert_exposure_seconds_per_hour: null,
            episodes_per_hour: null,
            component_percentiles: {},
            relative_exposure_score: null,
          },
        },
      })),
    })
    render(<MemoryRouter><PriorityTable priorities={noDataPortfolio.priorities} /></MemoryRouter>)

    expect(screen.getAllByText('Sem base observada para triagem.')).toHaveLength(2)
    expect(screen.queryByText(/50 \/ 100/)).not.toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: 'Abrir evidências' })[0]).toHaveAttribute('href', '/tratores/22222222-2222-4222-8222-222222222222')
  })
})
