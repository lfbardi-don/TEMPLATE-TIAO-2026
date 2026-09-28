import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Principal } from '../../lib/api-contracts'
import { tractorOverviewSchema } from '../../lib/api-contracts'
import { jsonResponse, notFound, stubApi } from '../../test/api-stub'
import { episodeId, exposureTimelineFixture, tractorOverviewFixture } from '../../test/fixtures'
import { SessionFixture } from '../../test/session'
import { managerFixture } from '../../test/session-fixtures'
import { MachinePage } from './MachinePage'
const tractorId = tractorOverviewFixture.tractor.id
function machineApi(overview: unknown = tractorOverviewFixture) { return (url: string) => {
  const path = url.split('?')[0]
  if (path?.endsWith(`/v1/tractors/${tractorId}/overview`)) return jsonResponse(overview)
  if (path?.endsWith(`/v1/tractors/${tractorId}/exposure-timeline`)) return jsonResponse(exposureTimelineFixture)
  if (path?.endsWith(`/v1/tractors/${tractorId}/inspection-cases`)) return jsonResponse({ evidence_role: 'operational_output_only', cases: [] })
  return notFound()
} }
function renderMachine(principal?: Principal) { render(<SessionFixture principal={principal}><MemoryRouter initialEntries={[`/tratores/${tractorId}`]}><Routes><Route path="/tratores/:tractorId" element={<MachinePage />} /></Routes></MemoryRouter></SessionFixture>) }
afterEach(() => vi.unstubAllGlobals())
describe('MachinePage', () => {
  it('mostra comparação visual, cobertura anterior e links com o instante observado', async () => {
    stubApi(machineApi({ ...tractorOverviewFixture, previous_30_days: { ...tractorOverviewFixture.scores['30_days'], active_days: 3, observed_hours: 8 }, reference_30_day_medians: { physical_exposure_seconds_per_hour: 10, alert_exposure_seconds_per_hour: 5, episodes_per_hour: 1 } }))
    renderMachine()
    expect(await screen.findByRole('heading', { name: 'Trator Norte (FENDT-314-01)' })).toBeInTheDocument()
    const summary = screen.getByRole('region', { name: 'Últimos 30 dias' })
    expect(within(summary).getByText('Acima do típico')).toBeInTheDocument()
    expect(within(summary).getByText('2 de 30 dias com operação')).toBeInTheDocument()
    expect(within(summary).getByText(/Anterior: 3 de 30 dias com operação · 8 h/)).toBeInTheDocument()
    expect(within(summary).getByText('Referência: 10 s/h')).toBeInTheDocument()
    expect(within(summary).getByText(/O índice combina as três medidas/)).toBeInTheDocument()
    const episodes = screen.getByRole('region', { name: 'Episódios sinalizados nos últimos 30 dias' })
    expect(within(episodes).getByRole('link')).toHaveAttribute('href', `/tratores/${tractorId}/episodios/${episodeId}?as_of_utc=${encodeURIComponent(tractorOverviewFixture.as_of_utc)}`)
    expect(await screen.findByRole('button', { name: 'Abrir vistoria' })).toBeInTheDocument()
    expect(screen.queryByText('Sinais do episódio mais recente')).not.toBeInTheDocument()
  })
  it('filtra episódios por condição e conecta o componente aos trechos', async () => {
    const extra = { ...tractorOverviewFixture.episodes_last_30_days[0]!, id: 'bbbbbbbbbbbbbbbbbbbb', conditions: ['overload_torque'] }
    stubApi(machineApi({ ...tractorOverviewFixture, episodes_last_30_days: [...tractorOverviewFixture.episodes_last_30_days, extra] }))
    renderMachine()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'torque e carga elevados' }))
    const episodes = screen.getByRole('region', { name: 'Episódios sinalizados nos últimos 30 dias' })
    expect(within(episodes).getAllByRole('link')).toHaveLength(1)
    expect(within(episodes).getByRole('link')).toHaveAttribute('href', expect.stringContaining(extra.id))
    const agenda = screen.getByRole('region', { name: 'O que olhar na vistoria' })
    await user.click(within(agenda).getAllByRole('button', { name: /episódios relacionados/ })[0]!)
    expect(within(episodes).getByRole('link')).toHaveAttribute('href', expect.stringContaining(episodeId))
    expect(screen.getByRole('button', { name: 'Limpar componente' })).toBeInTheDocument()
  })
  it('gestor vê evidência e navegação sem carregar casos', async () => {
    const fetchMock = stubApi(machineApi())
    renderMachine(managerFixture)
    expect(await screen.findByRole('region', { name: 'Últimos 30 dias' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Telemetria' })).toHaveAttribute('href', `/tratores/${tractorId}/telemetria`)
    expect(screen.queryByRole('region', { name: 'Vistoria preventiva' })).not.toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/inspection-cases'))).toBe(false)
  })
  it('período sem operação explica a ausência de comparação', async () => {
    const noData = tractorOverviewSchema.parse({ ...tractorOverviewFixture, episodes_last_30_days: [], inspection_agenda: { ...tractorOverviewFixture.inspection_agenda, items: [] }, scores: { ...tractorOverviewFixture.scores, '30_days': { ...tractorOverviewFixture.scores['30_days'], status: 'NO_DATA', active_days: 0, physical_exposure_seconds_per_hour: null, alert_exposure_seconds_per_hour: null, episodes_per_hour: null, component_percentiles: {}, relative_exposure_score: null, exposure_band: null } } })
    stubApi(machineApi(noData)); renderMachine()
    await userEvent.setup().click(await screen.findByText('Como ler o índice'))
    expect(screen.getByText(/Não houve operação observada no período/)).toBeVisible()
    expect(screen.getByText('Nenhum episódio começou nos últimos 30 dias.')).toBeInTheDocument()
    expect(screen.queryByText('Acima do típico')).not.toBeInTheDocument()
  })
})
