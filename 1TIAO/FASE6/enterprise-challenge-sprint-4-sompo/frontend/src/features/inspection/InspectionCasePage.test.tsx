import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Principal } from '../../lib/api-contracts'
import { AppShell } from '../../app/AppShell'
import { jsonResponse, notFound, stubApi } from '../../test/api-stub'
import { episodeDetailFixture, inProgressCaseFixture, legacyCaseFixture, tractorOverviewFixture } from '../../test/fixtures'
import { SessionFixture } from '../../test/session'
import { adminFixture, inspectorFixture, insurerFixture } from '../../test/session-fixtures'
import { InspectionCasePage } from './InspectionCasePage'
const caseId = inProgressCaseFixture.id
function renderCase(principal: Principal = inspectorFixture) {
  const router = createMemoryRouter([{ path: '/', element: <AppShell />, children: [
    { index: true, element: <p>Lista de máquinas</p> },
    { path: 'vistorias', element: <p>Lista de vistorias</p> },
    { path: 'vistorias/:caseId', element: <InspectionCasePage /> },
  ] }], { initialEntries: ['/', `/vistorias/${caseId}`] })
  render(<SessionFixture principal={principal}><RouterProvider router={router} /></SessionFixture>)
  return router
}
function caseApi(initial = inProgressCaseFixture, conflict = false) {
  let current = initial
  return stubApi((url, init) => {
    if (url.includes(`/inspection-cases/${caseId}/episodes/`)) return jsonResponse(episodeDetailFixture)
    if (url.endsWith('/overview')) return jsonResponse(tractorOverviewFixture)
    if (url.endsWith('/inspectors')) return jsonResponse({ inspectors: [] })
    if (url.endsWith('/events')) return jsonResponse({ case_id: caseId, events: [] })
    if (init?.method === 'PATCH') {
      if (conflict) return jsonResponse({ detail: 'changed' }, 409)
      const body = JSON.parse(String(init.body))
      current = { ...current, version: current.version + 1, ...(body.findings === undefined ? {} : { findings: body.findings }), ...(body.action === 'COMPLETE' ? { status: 'COMPLETED', result: body.result, result_notes: body.result_notes, completed_at_utc: '2024-06-03T11:00:00+00:00' } : {}) }
      return jsonResponse(current)
    }
    return url.endsWith(`/inspection-cases/${caseId}`) ? jsonResponse(current) : notFound()
  })
}
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })
describe('Inspection workspace', () => {
  it('mantém os campos bloqueados até salvar e permite editar novamente após a resposta', async () => {
    let releaseSave!: () => void
    let sentFindings: unknown
    const saving = new Promise<void>((resolve) => { releaseSave = resolve })
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === 'PATCH') {
        sentFindings = JSON.parse(String(init.body)).findings
        await saving
        return jsonResponse({ ...inProgressCaseFixture, version: 3, findings: sentFindings })
      }
      return jsonResponse(String(input).includes('/episodes/') ? episodeDetailFixture : inProgressCaseFixture)
    }))
    renderCase()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('radio', { name: 'Sem anomalia' }))
    const findingNotes = screen.getByLabelText('O que foi encontrado (opcional)')
    await user.type(findingNotes, 'Primeira nota')
    await user.click(screen.getByRole('button', { name: 'Salvar achados' }))
    expect(screen.getByRole('radio', { name: 'Atenção' })).toBeDisabled()
    expect(findingNotes).toBeDisabled()
    expect(screen.getByLabelText('Resultado')).toBeDisabled()
    expect(screen.getByLabelText('Observação geral')).toBeDisabled()
    await user.type(findingNotes, ' não enviada')
    expect(findingNotes).toHaveValue('Primeira nota')
    await act(async () => releaseSave())
    expect(await screen.findByText('Achados salvos')).toBeInTheDocument()
    expect(sentFindings).toEqual([{ item_id: 'engine', status: 'OK', notes: 'Primeira nota' }])
    expect(findingNotes).toBeEnabled()
    await user.type(findingNotes, ' atualizada')
    expect(screen.queryByText('Achados salvos')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Salvar achados' })).toBeEnabled()
  })
  it('confirma saída pelo menu e Voltar, preservando achados e resultado ao permanecer', async () => {
    caseApi()
    const router = renderCase()
    const user = userEvent.setup()
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    await user.click(await screen.findByRole('radio', { name: 'Sem anomalia' }))
    await user.click(screen.getByRole('link', { name: 'Máquinas' }))
    expect(confirm).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('radio', { name: 'Sem anomalia' })).toBeChecked()
    const unload = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(unload)
    expect(unload.defaultPrevented).toBe(true)
    await user.click(screen.getByRole('button', { name: 'Salvar achados' }))
    await screen.findByText('Achados salvos')
    await user.selectOptions(screen.getByLabelText('Resultado'), 'MONITOR')
    await user.type(screen.getByLabelText('Observação geral'), 'Rever na próxima parada.')
    await user.click(screen.getByRole('link', { name: 'Vistorias' }))
    expect(confirm).toHaveBeenCalledTimes(2)
    await act(async () => { await router.navigate(-1) })
    expect(confirm).toHaveBeenCalledTimes(3)
    expect(screen.getByLabelText('Resultado')).toHaveValue('MONITOR')
    expect(screen.getByLabelText('Observação geral')).toHaveValue('Rever na próxima parada.')
    confirm.mockReturnValue(true)
    await act(async () => { await router.navigate(-1) })
    expect(await screen.findByText('Lista de máquinas')).toBeInTheDocument()
    expect(confirm).toHaveBeenCalledTimes(4)
  })
  it('salva achados parciais e só conclui após toda a pauta e notas obrigatórias', async () => {
    const fetchMock = caseApi()
    renderCase()
    const user = userEvent.setup()
    await screen.findByRole('heading', { name: 'Motor' })
    expect(screen.getByRole('button', { name: 'Concluir vistoria' })).toBeDisabled()
    await user.click(screen.getByRole('radio', { name: 'Sem anomalia' }))
    await user.click(screen.getByRole('button', { name: 'Salvar achados' }))
    expect(await screen.findByText('Achados salvos')).toBeInTheDocument()
    const draftCall = fetchMock.mock.calls.find(([, init]) => init?.method === 'PATCH')
    expect(JSON.parse(String(draftCall?.[1]?.body))).toMatchObject({ action: 'SAVE_DRAFT', version: 2, findings: [{ item_id: 'engine', status: 'OK', notes: null }] })
    await user.click(screen.getByRole('button', { name: /Embreagem e transmissão/ }))
    await user.click(screen.getByRole('radio', { name: 'Atenção' }))
    await user.selectOptions(screen.getByLabelText('Resultado'), 'MONITOR')
    await user.click(screen.getByLabelText('Observação geral'))
    await user.paste('Revisar na próxima parada.')
    expect(screen.getByRole('button', { name: 'Concluir vistoria' })).toBeDisabled()
    await user.click(screen.getByLabelText('O que foi encontrado (obrigatório)'))
    await user.paste('Folga no pedal.')
    await user.click(screen.getByRole('button', { name: 'Concluir vistoria' }))
    expect(await screen.findByRole('heading', { name: 'Monitorar' })).toBeInTheDocument()
    const completeCall = fetchMock.mock.calls.filter(([, init]) => init?.method === 'PATCH').at(-1)
    expect(JSON.parse(String(completeCall?.[1]?.body))).toMatchObject({ action: 'COMPLETE', version: 3, result: 'MONITOR', findings: [{ item_id: 'engine', status: 'OK', notes: null }, { item_id: 'clutch_transmission', status: 'ATTENTION', notes: 'Folga no pedal.' }] })
    expect(screen.getByText(/Dados revisados até/)).toBeInTheDocument()
  })
  it('carrega sinais pela evidência congelada do caso e preserva o vínculo no detalhe', async () => {
    const fetchMock = caseApi()
    renderCase()
    const detail = await screen.findByRole('link', { name: 'Abrir detalhe completo →' })
    expect(detail).toHaveAttribute('href', expect.stringContaining(`?caseId=${caseId}`))
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes(`/inspection-cases/${caseId}/episodes/`))).toBe(true)
    expect(screen.getAllByRole('img')).toHaveLength(2)
  })
  it('retoma achados salvos e mantém o formulário quando há conflito de versão', async () => {
    caseApi({ ...inProgressCaseFixture, findings: [{ item_id: 'engine', status: 'OK', notes: null }] }, true)
    renderCase()
    const user = userEvent.setup()
    expect(await screen.findByRole('radio', { name: 'Sem anomalia' })).toBeChecked()
    await user.click(screen.getByRole('radio', { name: 'Atenção' }))
    await user.click(screen.getByLabelText('O que foi encontrado (obrigatório)'))
    await user.paste('Observação preservada')
    await user.click(screen.getByRole('button', { name: 'Salvar achados' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('alterado por outra pessoa')
    expect(screen.getByLabelText('O que foi encontrado (obrigatório)')).toHaveValue('Observação preservada')
    expect(screen.getByRole('button', { name: 'Recarregar caso' })).toBeInTheDocument()
  })
  it('admin consulta itens, sinais e histórico sem ações operacionais', async () => {
    const fetchMock = caseApi()
    renderCase(adminFixture)
    await screen.findByRole('heading', { name: 'Motor' })
    expect(screen.queryByRole('radio')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Concluir vistoria' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cancelar caso' })).not.toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/events'))).toBe(false)
    await userEvent.setup().click(screen.getByText('Histórico de ações'))
    expect(await screen.findByText('Este caso não tem ações registradas no histórico.')).toBeInTheDocument()
  })
  it('especialista gerencia atribuição e cancelamento sem preencher achados', async () => {
    caseApi()
    renderCase(insurerFixture)
    await screen.findByRole('heading', { name: 'Motor' })
    expect(screen.getByText('Responsável e data prevista')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cancelar caso' })).toBeInTheDocument()
    expect(screen.queryByRole('radio')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Concluir vistoria' })).not.toBeInTheDocument()
  })
  it('caso legado sem pauta continua concluindo pelo resultado geral', async () => {
    const fetchMock = caseApi(legacyCaseFixture)
    renderCase()
    const user = userEvent.setup()
    await screen.findByText(/não possui pauta por componente/)
    await user.selectOptions(screen.getByLabelText('Resultado'), 'NO_ACTION')
    await user.click(screen.getByLabelText('Observação geral'))
    await user.paste('Sem ação necessária.')
    await user.click(screen.getByRole('button', { name: 'Concluir vistoria' }))
    await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'PATCH')).toBe(true))
    const patch = fetchMock.mock.calls.find(([, init]) => init?.method === 'PATCH')
    expect(JSON.parse(String(patch?.[1]?.body))).toMatchObject({ action: 'COMPLETE', findings: null })
  })
})
