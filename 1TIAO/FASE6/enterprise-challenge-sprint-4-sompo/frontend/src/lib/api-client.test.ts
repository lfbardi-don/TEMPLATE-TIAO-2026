import { describe, expect, it, vi } from 'vitest'
import { ApiHttpError, getTractorOverview, logoutUser } from './api-client'
import { tractorOverviewFixture } from '../test/fixtures'
const tractorId = tractorOverviewFixture.tractor.id

describe('API client', () => {
  it('valida a resposta externa antes de devolvê-la', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(tractorOverviewFixture), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    vi.stubGlobal('fetch', fetchMock)
    const result = await getTractorOverview(tractorId, new AbortController().signal)
    expect(result.tractor.id).toBe(tractorId)
    expect(fetchMock).toHaveBeenCalledWith(`/api/v1/tractors/${tractorId}/overview`, expect.any(Object))
  })

  it('recusa uma resposta incompatível com o contrato', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ evidence_role: 'wrong' }), { status: 200 })))
    await expect(getTractorOverview(tractorId, new AbortController().signal)).rejects.toMatchObject({ kind: 'invalid_response' })
  })

  it('distingue falha HTTP', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: 'resource not found' }), { status: 404 })))
    const response = getTractorOverview(tractorId, new AbortController().signal)
    await expect(response).rejects.toBeInstanceOf(ApiHttpError)
    await expect(response).rejects.toMatchObject({ kind: 'http', status: 404 })
  })

  it('aceita 204 ao encerrar a sessão', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(null, { status: 204 })))
    await expect(logoutUser(new AbortController().signal)).resolves.toBeUndefined()
  })
})
