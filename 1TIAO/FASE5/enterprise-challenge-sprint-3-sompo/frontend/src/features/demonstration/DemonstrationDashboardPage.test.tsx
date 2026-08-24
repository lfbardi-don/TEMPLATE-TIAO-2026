import { render, screen } from '@testing-library/react'
import { createMemoryRouter, MemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AppShell } from '../../app/AppShell'
import { replayProgressSchema } from '../../lib/api-contracts'
import { tractorOverviewFixture } from '../../test/fixtures'
import { DemonstrationDashboardPage } from './DemonstrationDashboardPage'

const runningProgress = replayProgressSchema.parse({
  evidence_role: 'operational_output_only',
  status: 'running',
  tractor_id: tractorOverviewFixture.tractor.id,
  telemetry_import_id: '33333333-3333-4333-8333-333333333333',
  dataset_split: 'validation',
  source_doi: '10.5281/zenodo.14619787',
  source_license: 'CC-BY-4.0',
  semantic_sha256: 'd876974fdbf7a8053038ef652bea027783291f5321fae029a411ba21ce6e390c',
  total_samples: 152_561,
  samples_replayed: 76_280,
  ready_windows: 1_200,
  created_windows: 1_200,
  duplicate_windows: 0,
  alert_windows: 31,
  no_data_windows: 4,
  failures: 0,
  recent_inferences: [
    { mission_index: 301, window_index: 12, model_version: 'fendt314-hybrid-v2.0.1', hybrid_alert: false },
    { mission_index: 301, window_index: 13, model_version: 'fendt314-hybrid-v2.0.1', hybrid_alert: true },
  ],
  error_code: null,
})

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

function stubLiveApi(progress = runningProgress) {
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.includes('/v1/demo/replay-progress')) return jsonResponse(progress)
    if (url.includes(`/v1/tractors/${progress.tractor_id}/overview`)) return jsonResponse(tractorOverviewFixture)
    throw new Error(`unexpected request: ${url}`)
  }))
}

afterEach(() => vi.unstubAllGlobals())

describe('DemonstrationDashboardPage', () => {
  it('mostra progresso e decisões produzidas pela execução viva', async () => {
    stubLiveApi()
    render(<MemoryRouter><DemonstrationDashboardPage /></MemoryRouter>)

    expect(await screen.findByText('Inferência em andamento')).toBeInTheDocument()
    expect(screen.getByText('Avaliação acadêmica de uma unidade observada')).toBeInTheDocument()
    expect(screen.getByText('Como a IA produz um alerta')).toBeInTheDocument()
    expect(screen.getByText('Evidência experimental congelada')).toBeInTheDocument()
    expect(screen.getByText('74/2.522 alertas (2,93%)')).toBeInTheDocument()
    expect(screen.getByText('telemetria real · não sintética')).toBeInTheDocument()
    expect(screen.getByText('76.280 de 152.561 amostras')).toBeInTheDocument()
    expect(screen.getByText('Missão 301 · janela 13')).toBeInTheDocument()
    expect(screen.getByText('Exposição contextual sinalizada')).toBeInTheDocument()
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '50')
  })

  it('mostra agregados da API e destinos operacionais após uma execução completa', async () => {
    const complete = replayProgressSchema.parse({ ...runningProgress, status: 'complete', samples_replayed: runningProgress.total_samples, error_code: null })
    stubLiveApi(complete)
    render(<MemoryRouter><DemonstrationDashboardPage /></MemoryRouter>)

    expect(await screen.findByText('Execução concluída')).toBeInTheDocument()
    expect(await screen.findByText('Exposição relativa por horizonte')).toBeInTheDocument()
    expect(screen.getAllByText('50 / 100')).toHaveLength(3)
    expect(screen.getByRole('link', { name: 'Abrir evidências do trator' })).toHaveAttribute('href', `/tratores/${tractorOverviewFixture.tractor.id}`)
    expect(screen.getByRole('link', { name: 'Ver prioridades' })).toHaveAttribute('href', '/prioridades')
  })

  it('não inventa resultados quando a demo não foi iniciada', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ detail: 'not found' }, 404)))
    render(<MemoryRouter><DemonstrationDashboardPage /></MemoryRouter>)

    expect(await screen.findByText('Demonstração local não iniciada')).toBeInTheDocument()
    expect(screen.getByText('make demo-real')).toBeInTheDocument()
    expect(screen.queryByText('74 / 2.522')).not.toBeInTheDocument()
  })

  it('mantém o limite explícito quando a API local não responde', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('offline') }))
    const rootRouter = createMemoryRouter([
      { path: '/', element: <AppShell />, children: [{ index: true, element: <DemonstrationDashboardPage /> }] },
    ], { initialEntries: ['/'] })

    render(<RouterProvider router={rootRouter} />)

    expect(await screen.findByText('Demonstração · inferência observável')).toBeInTheDocument()
    expect(await screen.findByText('API indisponível')).toBeInTheDocument()
    expect(await screen.findByText('Atualização não concluída')).toBeInTheDocument()
  })
})
