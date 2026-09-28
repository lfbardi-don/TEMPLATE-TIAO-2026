import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { jsonResponse, stubApi } from '../../test/api-stub'
import { completedCaseFixture, inProgressCaseFixture } from '../../test/fixtures'
import { SessionFixture } from '../../test/session'
import { adminFixture, inspectorFixture, insurerFixture } from '../../test/session-fixtures'
import type { Principal, TractorOverview } from '../../lib/api-contracts'
import { InspectionCasesPanel } from './InspectionCasesPanel'
const tractorId = inProgressCaseFixture.tractor_id
function renderPanel(principal: Principal, workflow?: TractorOverview['workflow']) { render(<SessionFixture principal={principal}><MemoryRouter><Routes><Route path="/" element={<InspectionCasesPanel tractorId={tractorId} workflow={workflow} />} /><Route path="/vistorias/:caseId" element={<h1>Workspace da vistoria</h1>} /></Routes></MemoryRouter></SessionFixture>) }
afterEach(() => vi.unstubAllGlobals())
describe('InspectionCasesPanel', () => {
  it('abre a vistoria com responsável e leva ao workspace', async () => {
    const fetchMock = stubApi((url, init) => url.endsWith('/inspectors') ? jsonResponse({ inspectors: [inspectorFixture] }) : init?.method === 'POST' ? jsonResponse(inProgressCaseFixture) : jsonResponse({ evidence_role: 'operational_output_only', cases: [] }))
    renderPanel(insurerFixture)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Abrir vistoria' }))
    await user.selectOptions(await screen.findByLabelText('Vistoriador (opcional)'), inspectorFixture.worker_id)
    await user.click(screen.getByRole('button', { name: 'Confirmar abertura' }))
    expect(await screen.findByRole('heading', { name: 'Workspace da vistoria' })).toBeInTheDocument()
    expect(JSON.parse(String(fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')?.[1]?.body))).toMatchObject({ assignee: inspectorFixture.worker_id, due_date: null })
  })
  it('mostra continuar ao vistoriador e somente consulta ao administrador', async () => {
    stubApi(() => jsonResponse({ evidence_role: 'operational_output_only', cases: [inProgressCaseFixture] }))
    renderPanel(adminFixture)
    expect(await screen.findByRole('link', { name: 'Ver vistoria' })).toHaveAttribute('href', `/vistorias/${inProgressCaseFixture.id}`)
    expect(screen.queryByRole('button', { name: 'Abrir vistoria' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Concluir vistoria' })).not.toBeInTheDocument()
  })

  it('orienta o administrador sem sugerir uma ação que seu perfil não pode executar', async () => {
    stubApi(() => jsonResponse({ evidence_role: 'operational_output_only', cases: [] }))
    renderPanel(adminFixture)
    expect(await screen.findByText('O especialista da seguradora abre a vistoria a partir dos episódios observados.')).toBeInTheDocument()
    expect(screen.queryByText(/Abra uma vistoria para transformar/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Abrir vistoria' })).not.toBeInTheDocument()
  })

  it('não diz que houve revisão quando não há episódios nem conclusão anterior', async () => {
    stubApi(() => jsonResponse({ evidence_role: 'operational_output_only', cases: [] }))
    renderPanel(insurerFixture, { active_case: null, last_completed_case: null, new_episode_ids: [], can_open_case: false })
    expect(await screen.findByText('Nenhum episódio pendente de vistoria no período.')).toBeInTheDocument()
    expect(screen.queryByText(/já foram revisados/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Abrir vistoria' })).not.toBeInTheDocument()
  })

  it('não reabre os mesmos episódios depois de uma conclusão', async () => {
    stubApi(() => jsonResponse({ evidence_role: 'operational_output_only', cases: [completedCaseFixture] }))
    renderPanel(insurerFixture, { active_case: null, last_completed_case: { id: completedCaseFixture.id, evidence_as_of_utc: completedCaseFixture.evidence_as_of_utc, completed_at_utc: completedCaseFixture.completed_at_utc!, result: 'MONITOR' }, new_episode_ids: [], can_open_case: false })
    expect(await screen.findByRole('link', { name: 'Ver resultado' })).toBeInTheDocument()
    expect(screen.getByText(/já foram revisados/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Abrir vistoria' })).not.toBeInTheDocument()
  })
})
