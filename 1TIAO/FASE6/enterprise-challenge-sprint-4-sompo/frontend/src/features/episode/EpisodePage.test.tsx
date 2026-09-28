import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { jsonResponse, notFound, stubApi } from '../../test/api-stub'
import { episodeDetailFixture, episodeId, tractorOverviewFixture } from '../../test/fixtures'
import { EpisodePage } from './EpisodePage'

const tractorId = tractorOverviewFixture.tractor.id

function renderEpisode(query = '') {
  render(<MemoryRouter initialEntries={[`/tratores/${tractorId}/episodios/${episodeId}${query}`]}><Routes><Route path="/tratores/:tractorId/episodios/:episodeId" element={<EpisodePage />} /></Routes></MemoryRouter>)
}

afterEach(() => vi.unstubAllGlobals())

describe('EpisodePage', () => {
  it('mostra as duas condições do alerta e os sinais segundo a segundo', async () => {
    const fetchMock = stubApi((url) => url.endsWith(`/v1/tractors/${tractorId}/episodes/${episodeId}`) ? jsonResponse(episodeDetailFixture) : notFound())
    renderEpisode()

    const why = await screen.findByRole('region', { name: 'Por que este trecho foi sinalizado' })
    expect(within(why).getByText('baixa rotação sob carga: 12 s')).toBeInTheDocument()
    expect(within(why).getByText('rotação entre 600 e 1.400 rpm com carga acima de 70%')).toBeInTheDocument()
    const criteria = within(why).getByText(/índice de raridade 0,62, acima do limite 0,55 para esta operação/)
    expect(criteria).not.toBeVisible()
    await userEvent.setup().click(within(why).getByText('Ver critérios da sinalização'))
    expect(criteria).toBeVisible()

    const signals = screen.getByRole('region', { name: 'Sinais segundo a segundo' })
    expect(within(signals).getAllByRole('img')).toHaveLength(2)
    expect(within(signals).getByRole('img', { name: 'Rotação do motor: de 1.200 a 1.800 rpm em 59 segundos' })).toBeInTheDocument()
    expect(within(signals).getByText('1.400')).toBeInTheDocument()

    await userEvent.setup().click(screen.getByText('Pistas e critérios da sinalização'))
    expect(screen.getByText('média de variação de rotação em 1 s: desvio de 11,8× a faixa habitual')).toBeInTheDocument()
    expect(screen.getByText(/não identificam sua causa/)).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'O que olhar por causa deste episódio' })).toBeInTheDocument()
    expect(screen.getByText(/1 min de duração · 12 s em condição de atenção/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Voltar para a máquina' })).toHaveAttribute('href', `/tratores/${tractorId}`)
    expect(fetchMock).toHaveBeenCalledWith(`/api/v1/tractors/${tractorId}/episodes/${episodeId}`, expect.any(Object))
  })


  it('mantém o instante do resumo no acesso direto ao episódio', async () => {
    const asOf = tractorOverviewFixture.as_of_utc
    const fetchMock = stubApi(() => jsonResponse(episodeDetailFixture))
    renderEpisode(`?as_of_utc=${encodeURIComponent(asOf)}`)
    await screen.findByRole('region', { name: 'Sinais segundo a segundo' })
    expect(fetchMock).toHaveBeenCalledWith(`/api/v1/tractors/${tractorId}/episodes/${episodeId}?as_of_utc=${encodeURIComponent(asOf)}`, expect.any(Object))
  })

  it('usa o snapshot do caso e retorna para a vistoria no link direto', async () => {
    const caseId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
    const fetchMock = stubApi(() => jsonResponse(episodeDetailFixture))
    renderEpisode(`?caseId=${caseId}`)
    await screen.findByRole('region', { name: 'Sinais segundo a segundo' })
    expect(fetchMock).toHaveBeenCalledWith(`/api/v1/inspection-cases/${caseId}/episodes/${episodeId}`, expect.any(Object))
    expect(screen.getByRole('link', { name: 'Voltar para a vistoria' })).toHaveAttribute('href', `/vistorias/${caseId}`)
  })

  it('avisa quando o episódio não existe mais no histórico', async () => {
    stubApi(() => notFound())
    renderEpisode()

    expect(await screen.findByText('Episódio não encontrado')).toBeInTheDocument()
  })
})
