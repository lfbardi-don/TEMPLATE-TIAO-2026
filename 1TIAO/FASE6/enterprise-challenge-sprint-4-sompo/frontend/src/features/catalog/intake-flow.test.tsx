import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { SessionFixture } from '../../test/session'
import { managerFixture } from '../../test/session-fixtures'
import { jsonResponse, notFound, stubApi } from '../../test/api-stub'
import { CatalogPage } from './CatalogPage'
import { CsvImporter } from './ImportsPage'

const catalog = { fleets: [{ id: 'fleet-a', name: 'Aurora', tractors: [{
  id: 'tractor-a', fleet_id: 'fleet-a', external_id: 'AURORA-01', display_name: 'Trator norte', model_name: 'Fendt 314',
  source_kind: null, latest_observed_at_utc: null, import_count: 0, window_count: 0, alert_count: 0,
}] }] }
const preview = { sample_count: 3600, mission_count: 1, started_at_utc: '2026-09-01T08:00:00Z', ended_at_utc: '2026-09-01T08:59:59Z', ready_window_count: 60, skipped_window_count: 0, source_kind: 'simulated_csv', reference_label: 'Referência treinada Fendt 314' }
const scenario = { id: 'aurora', label: 'Operação regular', fleet_name: 'Aurora', machine_name: 'Aurora 01', file_name: 'aurora.csv', description: 'Dados simulados para testar a entrada.', download_url: '/v1/demo/csv-scenarios/aurora.csv', followup_for: null }
afterEach(() => vi.unstubAllGlobals())

describe('entrada de máquinas e dados', () => {
  it('mostra máquinas sem dados e cadastra uma nova máquina na frota existente', async () => {
    const user = userEvent.setup()
    const calls: unknown[] = []
    stubApi((url, init) => {
      if (url === '/api/v1/catalog') return jsonResponse(catalog)
      if (url === '/api/v1/fleets/fleet-a/tractors') { calls.push(JSON.parse(String(init?.body))); return jsonResponse({ id: 'tractor-b' }, 201) }
      return notFound()
    })
    render(<SessionFixture><MemoryRouter><Routes><Route path="/" element={<CatalogPage />} /><Route path="/tratores/tractor-b/importacoes" element={<h1>Importar na nova máquina</h1>} /></Routes></MemoryRouter></SessionFixture>)
    expect(await screen.findByRole('heading', { name: 'Trator norte' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Importar dados' })).toHaveAttribute('href', '/tratores/tractor-a/importacoes')
    await user.click(screen.getByText('Cadastrar máquina', { selector: 'summary' }))
    await user.type(screen.getByLabelText('Identificador da máquina'), 'AURORA-02')
    await user.click(screen.getByRole('button', { name: 'Cadastrar e importar dados' }))
    expect(await screen.findByRole('heading', { name: 'Importar na nova máquina' })).toBeInTheDocument()
    expect(calls).toEqual([{ external_id: 'AURORA-02', display_name: null }])
  })

  it('gestor consulta seu catálogo sem ações de cadastro/importação', async () => {
    stubApi(() => jsonResponse(catalog))
    render(<SessionFixture principal={managerFixture}><MemoryRouter><CatalogPage /></MemoryRouter></SessionFixture>)
    expect(await screen.findByRole('heading', { name: 'Trator norte' })).toBeInTheDocument()
    expect(screen.queryByText('Cadastrar máquina')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Ver máquina' })).toHaveAttribute('href', '/tratores/tractor-a')
  })

  it('valida um CSV simulado antes de processar e leva ao resultado', async () => {
    const user = userEvent.setup(), onImported = vi.fn(), writes: unknown[] = []
    stubApi((url, init) => {
      if (url === '/api/v1/demo/csv-scenarios') return jsonResponse({ scenarios: [scenario] })
      if (url.endsWith('/aurora.csv')) return new Response('observed_at_utc,engine_rpm\n2026-09-01T08:00:00Z,1600')
      if (url.endsWith('/preview')) return jsonResponse(preview)
      if (url.endsWith('/imports')) { writes.push(JSON.parse(String(init?.body))); return jsonResponse({ ...preview, id: 'import-a', duplicate: false, window_count: 60, physical_candidate_count: 10, alert_count: 2, model_version: 'fendt314-hybrid-v2.0.1' }, 201) }
      return notFound()
    })
    render(<SessionFixture><MemoryRouter><CsvImporter tractorId="tractor-a" onImported={onImported} /></MemoryRouter></SessionFixture>)
    await user.click(await screen.findByText('Experimentar com CSVs simulados'))
    await user.click(screen.getByRole('button', { name: 'Usar Aurora 01' }))
    expect(await screen.findByText('aurora.csv')).toBeInTheDocument()
    expect(writes).toHaveLength(0)
    await user.click(screen.getByRole('button', { name: 'Processar dados' }))
    expect(await screen.findByText('Análise concluída')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Ver resultado' })).toHaveAttribute('href', '/tratores/tractor-a')
    expect(writes).toEqual([expect.objectContaining({ source_kind: 'simulated_csv', file_name: 'aurora.csv' })])
    expect(onImported).toHaveBeenCalledOnce()
  })

  it('erro de validação impede o processamento', async () => {
    const user = userEvent.setup()
    stubApi((url) => {
      if (url === '/api/v1/demo/csv-scenarios') return jsonResponse({ scenarios: [scenario] })
      if (url.endsWith('/aurora.csv')) return new Response('invalid')
      if (url.endsWith('/preview')) return jsonResponse({ detail: 'A coluna observed_at_utc é obrigatória.' }, 422)
      return notFound()
    })
    render(<SessionFixture><MemoryRouter><CsvImporter tractorId="tractor-a" onImported={() => {}} /></MemoryRouter></SessionFixture>)
    await user.click(await screen.findByText('Experimentar com CSVs simulados'))
    await user.click(screen.getByRole('button', { name: 'Usar Aurora 01' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('observed_at_utc')
    expect(screen.queryByRole('button', { name: 'Processar dados' })).not.toBeInTheDocument()
  })
})
