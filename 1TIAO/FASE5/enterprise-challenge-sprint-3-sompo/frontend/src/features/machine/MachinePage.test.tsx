import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { TractorOverviewPage } from './TractorOverviewPage'
import { tractorOverviewFixture } from '../../test/fixtures'
import { tractorOverviewSchema } from '../../lib/api-contracts'

describe('TractorOverviewPage', () => {
  it('começa pelo próximo passo, mantém os detalhes acessíveis e preserva episódio e proveniência', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(tractorOverviewFixture), { status: 200, headers: { 'Content-Type': 'application/json' } })))
    render(<MemoryRouter initialEntries={['/tratores/22222222-2222-4222-8222-222222222222']}><Routes><Route path="/tratores/:tractorId" element={<TractorOverviewPage />} /></Routes></MemoryRouter>)

    expect(await screen.findByText('Próximo passo de revisão')).toBeInTheDocument()
    expect(screen.getByText('Nenhuma falha foi diagnosticada.')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Ver detalhes técnicos' }).length).toBe(3)
    expect(screen.getByText('7 dias')).toBeInTheDocument()
    expect(screen.getByText('15 dias')).toBeInTheDocument()
    expect(screen.getAllByText('30 dias').length).toBeGreaterThan(0)
    expect(screen.getAllByText('+10 pontos').length).toBeGreaterThan(0)
    await user.click(screen.getAllByRole('button', { name: 'Ver detalhes técnicos' })[0])
    expect(screen.getByText('3,1 s')).toBeInTheDocument()
    expect(screen.getByText('0,2')).toBeInTheDocument()
    expect(screen.getByText(/Missão 277/)).toBeInTheDocument()
    expect(screen.getByText(/replay do conjunto observado/)).toBeInTheDocument()
  })

  it('não sugere inspeção quando o horizonte de 30 dias não tem base observada', async () => {
    const noDataOverview = tractorOverviewSchema.parse({
      ...tractorOverviewFixture,
      scores: {
        ...tractorOverviewFixture.scores,
        '30_days': {
          ...tractorOverviewFixture.scores['30_days'],
          status: 'NO_DATA',
          physical_exposure_seconds_per_hour: null,
          alert_exposure_seconds_per_hour: null,
          episodes_per_hour: null,
          component_percentiles: {},
          relative_exposure_score: null,
        },
      },
    })
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(noDataOverview), { status: 200, headers: { 'Content-Type': 'application/json' } })))
    render(<MemoryRouter initialEntries={['/tratores/22222222-2222-4222-8222-222222222222']}><Routes><Route path="/tratores/:tractorId" element={<TractorOverviewPage />} /></Routes></MemoryRouter>)

    expect(await screen.findByText('Sem base observada para triagem')).toBeInTheDocument()
    expect(screen.getByText(/Continue a coleta e verifique a disponibilidade e a proveniência/)).toBeInTheDocument()
    expect(screen.queryByText('Próximo passo de revisão')).not.toBeInTheDocument()
    expect(screen.getByText('Nenhuma falha foi diagnosticada.')).toBeInTheDocument()
  })
})
