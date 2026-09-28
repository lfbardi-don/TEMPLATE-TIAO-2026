import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { jsonResponse, stubApi } from '../../test/api-stub'
import { tractorOverviewFixture } from '../../test/fixtures'
import { SessionFixture } from '../../test/session'
import { adminFixture, inspectorFixture } from '../../test/session-fixtures'
import { AdminPage } from './AdminPage'

const createdAt = '2024-06-03T10:00:00+00:00'
const adminAccount = { ...adminFixture, active: true, created_at_utc: createdAt }
const inspectorAccount = { ...inspectorFixture, active: true, created_at_utc: createdAt }
const scored = tractorOverviewFixture
const unscoredFleet = { id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', name: 'Frota sem operação', tractors: [{ id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', external_id: 'FENDT-314-02', display_name: 'Trator sem histórico', model_name: 'Fendt 314' }] }
const catalogFixture = { fleets: [
  { id: scored.fleet.id, name: scored.fleet.name, tractors: [{ id: scored.tractor.id, external_id: scored.tractor.external_id, display_name: scored.tractor.display_name, model_name: scored.tractor.model_name }] },
  unscoredFleet,
  { id: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc', name: 'Frota vazia', tractors: [] },
] }
const accountEvent = {
  id: '99999999-9999-4999-8999-999999999999',
  target_user_id: inspectorFixture.id, target_worker_id: inspectorFixture.worker_id,
  actor_user_id: adminFixture.id, actor_worker_id: adminFixture.worker_id,
  action: 'CREATE', occurred_at_utc: createdAt,
  details: { role: 'INSPECTOR', fleet_id: null, active: true },
}

function renderPage() {
  return render(<MemoryRouter><SessionFixture principal={adminFixture}><AdminPage /></SessionFixture></MemoryRouter>)
}

afterEach(() => vi.unstubAllGlobals())

describe('AdminPage', () => {
  it('lista máquinas e histórico e entrega a senha temporária apenas na criação', async () => {
    const user = userEvent.setup()
    let accounts = [adminAccount]
    const fetchMock = stubApi((url, init) => {
      if (url.endsWith('/v1/admin/users') && init?.method === 'POST') {
        accounts = [adminAccount, inspectorAccount]
        return jsonResponse({ user: inspectorAccount, temporary_password: 'senha-temporaria-01' }, 201)
      }
      if (url.endsWith('/v1/admin/users')) return jsonResponse({ users: accounts })
      if (url.endsWith('/v1/admin/user-events')) return jsonResponse({ events: [accountEvent] })
      if (url.endsWith('/v1/admin/catalog')) return jsonResponse(catalogFixture)
      return jsonResponse({ detail: 'not found' }, 404)
    })
    renderPage()

    expect(await screen.findByRole('heading', { name: 'Contas e acesso' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Trator Norte/ })).toHaveAttribute('href', `/tratores/${scored.tractor.id}`)
    expect(screen.getByRole('link', { name: /Trator sem histórico/ })).toHaveAttribute('href', `/tratores/${unscoredFleet.tractors[0]?.id}`)
    expect(screen.getByText('Nenhuma máquina cadastrada nesta frota.')).toBeInTheDocument()
    expect(screen.getByText(`Trabalhador ${adminFixture.worker_id} → conta ${inspectorFixture.worker_id}`)).toBeInTheDocument()
    const ownRow = screen.getByRole('row', { name: new RegExp(adminFixture.worker_id) })
    expect(within(ownRow).getByRole('combobox', { name: `Perfil de ${adminFixture.worker_id}` })).toBeDisabled()
    expect(within(ownRow).getByRole('checkbox')).toBeDisabled()

    await user.type(screen.getByLabelText('Número do trabalhador'), inspectorFixture.worker_id)
    await user.click(screen.getByRole('button', { name: 'Criar conta' }))

    expect(await screen.findByText(`Senha temporária de ${inspectorFixture.worker_id}`)).toBeInTheDocument()
    expect(screen.getByText('senha-temporaria-01')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('row', { name: new RegExp(inspectorFixture.worker_id) })).toBeInTheDocument())
    const createCall = fetchMock.mock.calls.find(([url, init]) => String(url).endsWith('/v1/admin/users') && init?.method === 'POST')
    expect(JSON.parse(String(createCall?.[1]?.body))).toEqual({ worker_id: inspectorFixture.worker_id, role: 'INSPECTOR', fleet_id: null })
  })

  it('altera o perfil e a frota, depois redefine a senha da conta', async () => {
    const user = userEvent.setup()
    let account = inspectorAccount
    const fetchMock = stubApi((url, init) => {
      if (url.endsWith(`/v1/admin/users/${inspectorFixture.id}/reset-password`) && init?.method === 'POST') return jsonResponse({ temporary_password: 'nova-senha-temporaria' })
      if (url.endsWith(`/v1/admin/users/${inspectorFixture.id}`) && init?.method === 'PATCH') {
        account = { ...account, role: 'FLEET_MANAGER', fleet_id: unscoredFleet.id }
        return jsonResponse({ user: account })
      }
      if (url.endsWith('/v1/admin/users')) return jsonResponse({ users: [adminAccount, account] })
      if (url.endsWith('/v1/admin/user-events')) return jsonResponse({ events: [] })
      if (url.endsWith('/v1/admin/catalog')) return jsonResponse(catalogFixture)
      return jsonResponse({ detail: 'not found' }, 404)
    })
    renderPage()

    const row = await screen.findByRole('row', { name: new RegExp(inspectorFixture.worker_id) })
    await user.selectOptions(within(row).getByRole('combobox', { name: `Perfil de ${inspectorFixture.worker_id}` }), 'FLEET_MANAGER')
    await user.selectOptions(within(row).getByRole('combobox', { name: `Frota de ${inspectorFixture.worker_id}` }), unscoredFleet.id)
    await user.click(within(row).getByRole('button', { name: 'Salvar alterações' }))

    const patchCall = fetchMock.mock.calls.find(([url, init]) => String(url).endsWith(`/v1/admin/users/${inspectorFixture.id}`) && init?.method === 'PATCH')
    expect(JSON.parse(String(patchCall?.[1]?.body))).toEqual({ role: 'FLEET_MANAGER', fleet_id: unscoredFleet.id, active: true })
    await waitFor(() => expect(screen.getByRole('row', { name: new RegExp(inspectorFixture.worker_id) })).toHaveTextContent('Frota sem operação'))
    await user.click(within(screen.getByRole('row', { name: new RegExp(inspectorFixture.worker_id) })).getByRole('button', { name: 'Redefinir senha' }))
    expect(await screen.findByText('nova-senha-temporaria')).toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([url, init]) => String(url).endsWith(`/v1/admin/users/${inspectorFixture.id}/reset-password`) && init?.method === 'POST')).toBe(true)
  })

  it('mantém a edição disponível após uma falha na operação', async () => {
    const user = userEvent.setup()
    stubApi((url, init) => {
      if (url.endsWith(`/v1/admin/users/${inspectorFixture.id}/reset-password`) && init?.method === 'POST') return jsonResponse({ detail: 'unavailable' }, 503)
      if (url.endsWith('/v1/admin/users')) return jsonResponse({ users: [inspectorAccount] })
      if (url.endsWith('/v1/admin/user-events')) return jsonResponse({ events: [] })
      if (url.endsWith('/v1/admin/catalog')) return jsonResponse(catalogFixture)
      return jsonResponse({ detail: 'not found' }, 404)
    })
    renderPage()

    await user.click(await screen.findByRole('button', { name: 'Redefinir senha' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Não foi possível salvar a alteração.')
    expect(screen.getByRole('button', { name: 'Redefinir senha' })).toBeEnabled()
  })

  it('mantém a senha temporária visível quando o administrador redefine a própria senha', async () => {
    const user = userEvent.setup()
    const fetchMock = stubApi((url, init) => {
      if (url.endsWith(`/v1/admin/users/${adminFixture.id}/reset-password`) && init?.method === 'POST') return jsonResponse({ temporary_password: 'senha-do-admin' })
      if (url.endsWith('/v1/admin/users')) return jsonResponse({ users: [adminAccount] })
      if (url.endsWith('/v1/admin/user-events')) return jsonResponse({ events: [] })
      if (url.endsWith('/v1/admin/catalog')) return jsonResponse(catalogFixture)
      return jsonResponse({ detail: 'not found' }, 404)
    })
    renderPage()

    await user.click(await screen.findByRole('button', { name: 'Redefinir senha' }))
    expect(await screen.findByText('senha-do-admin')).toBeInTheDocument()
    expect(screen.getByText(/Sua sessão foi encerrada/)).toBeInTheDocument()
    expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith('/v1/admin/users'))).toHaveLength(1)
  })
})
