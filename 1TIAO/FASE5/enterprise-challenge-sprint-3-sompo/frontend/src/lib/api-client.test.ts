import { describe, expect, it, vi } from 'vitest'
import { ApiHttpError, getDemoReplayProgress, requestJson } from './api-client'
import { portfolioSchema } from './api-contracts'
import { portfolioFixture } from '../test/fixtures'

describe('requestJson', () => {
  it('valida a resposta externa antes de devolvê-la', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(portfolioFixture), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    vi.stubGlobal('fetch', fetchMock)

    const result = await requestJson('/v1/portfolio/inspection-priorities', portfolioSchema, new AbortController().signal)

    expect(result.priorities[0]?.rank).toBe(1)
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/portfolio/inspection-priorities', expect.any(Object))
  })

  it('recusa uma resposta incompatível com o contrato', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ evidence_role: 'wrong' }), { status: 200 })))

    await expect(requestJson('/v1/portfolio/inspection-priorities', portfolioSchema, new AbortController().signal)).rejects.toMatchObject({ kind: 'invalid_response' })
  })

  it('distingue falha HTTP', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: 'resource not found' }), { status: 404 })))

    try {
      await requestJson('/v1/portfolio/inspection-priorities', portfolioSchema, new AbortController().signal)
    } catch (error: unknown) {
      expect(error).toBeInstanceOf(ApiHttpError)
      expect(error).toMatchObject({ kind: 'http', status: 404 })
    }
  })

  it('valida o progresso da inferência viva antes de expor os contadores', async () => {
    const response = {
      evidence_role: 'operational_output_only',
      status: 'running',
      tractor_id: '22222222-2222-4222-8222-222222222222',
      telemetry_import_id: '33333333-3333-4333-8333-333333333333',
      dataset_split: 'validation',
      source_doi: '10.5281/zenodo.14619787',
      source_license: 'CC-BY-4.0',
      semantic_sha256: 'd876974fdbf7a8053038ef652bea027783291f5321fae029a411ba21ce6e390c',
      total_samples: 152561,
      samples_replayed: 1000,
      ready_windows: 10,
      created_windows: 10,
      duplicate_windows: 0,
      alert_windows: 1,
      no_data_windows: 0,
      failures: 0,
      recent_inferences: [{ mission_index: 1, window_index: 9, model_version: 'fendt314-hybrid-v2.0.1', hybrid_alert: true }],
      error_code: null,
    }
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(response), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    const result = await getDemoReplayProgress(new AbortController().signal)

    expect(result.created_windows).toBe(10)
    expect(result.recent_inferences[0]?.hybrid_alert).toBe(true)
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/demo/replay-progress', expect.any(Object))
  })

  it('recusa progresso impossível antes de renderizar a demo', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      evidence_role: 'operational_output_only', status: 'complete', tractor_id: '22222222-2222-4222-8222-222222222222', telemetry_import_id: '33333333-3333-4333-8333-333333333333', dataset_split: 'validation', source_doi: '10.5281/zenodo.14619787', source_license: 'CC-BY-4.0', semantic_sha256: 'd876974fdbf7a8053038ef652bea027783291f5321fae029a411ba21ce6e390c', total_samples: 10, samples_replayed: 11, ready_windows: 0, created_windows: 0, duplicate_windows: 0, alert_windows: 0, no_data_windows: 0, failures: 0, recent_inferences: [], error_code: null,
    }), { status: 200 })))

    await expect(getDemoReplayProgress(new AbortController().signal)).rejects.toMatchObject({ kind: 'invalid_response' })
  })
})
