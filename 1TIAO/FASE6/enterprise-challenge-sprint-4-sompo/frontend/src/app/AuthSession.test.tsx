import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { getTractorOverview } from '../lib/api-client'
import { jsonResponse } from '../test/api-stub'
import { adminFixture, insurerFixture, managerFixture } from '../test/session-fixtures'
import { AppShell } from './AppShell'
import { RequireRole, RequireSession, SessionProvider } from './AuthSession'
import { LoginPage } from './LoginPage'

function testRouter(initialPath: string) {
  return createMemoryRouter([
    { path: '/login', element: <LoginPage /> },
    { element: <RequireSession />, children: [
      { path: '/', element: <AppShell />, children: [
        { index: true, element: <p>Máquina protegida</p> },
        { path: 'tratores/:tractorId', element: <p>Máquina protegida</p> },
        { path: 'vistorias', element: <RequireRole role={['INSURER', 'ADMIN', 'INSPECTOR']}><p>Vistorias protegidas</p></RequireRole> },
        { path: 'admin', element: <RequireRole role="ADMIN"><p>Administração protegida</p></RequireRole> },
      ] },
    ] },
  ], { initialEntries: [initialPath] })
}

afterEach(() => vi.unstubAllGlobals())

describe('sessão e rotas', () => {
  it('mostra erro de credenciais sem abrir a aplicação', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ detail: 'invalid credentials' }, 401)))
    render(<SessionProvider><RouterProvider router={testRouter('/login')} /></SessionProvider>)

    await user.type(await screen.findByLabelText('Número do trabalhador'), insurerFixture.worker_id)
    await user.type(screen.getByLabelText('Senha'), 'errada')
    await user.click(screen.getByRole('button', { name: 'Entrar' }))

    expect(await screen.findByText('Número do trabalhador ou senha inválidos.')).toBeInTheDocument()
    expect(screen.queryByText('Máquina protegida')).not.toBeInTheDocument()
  })

  it('exige login e volta à rota pedida depois da autenticação', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      const path = String(input)
      if (path === '/api/v1/auth/me') return jsonResponse({ detail: 'Sessão ausente' }, 401)
      if (path === '/api/v1/auth/login') return jsonResponse(insurerFixture)
      if (path === '/api/health/ready') return jsonResponse({ status: 'ready' })
      if (path === '/api/v1/auth/logout') return new Response(null, { status: 204 })
      return jsonResponse({ detail: 'not found' }, 404)
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<SessionProvider><RouterProvider router={testRouter('/tratores/123')} /></SessionProvider>)

    expect(await screen.findByRole('heading', { name: 'Entrar' })).toBeInTheDocument()
    expect(screen.queryByText('Máquina protegida')).not.toBeInTheDocument()
    await user.type(screen.getByLabelText('Número do trabalhador'), `00a${insurerFixture.worker_id.slice(2)}`)
    expect(screen.getByLabelText('Número do trabalhador')).toHaveValue(insurerFixture.worker_id)
    await user.type(screen.getByLabelText('Senha'), 'senha de teste')
    await user.click(screen.getByRole('button', { name: 'Entrar' }))

    expect(await screen.findByText('Máquina protegida')).toBeInTheDocument()
    expect(screen.getByText(`Especialista da seguradora · ${insurerFixture.worker_id}`)).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/auth/login', expect.objectContaining({ credentials: 'same-origin', method: 'POST' }))
    const loginCall = fetchMock.mock.calls.find(([input]) => String(input) === '/api/v1/auth/login')
    expect(JSON.parse(String(loginCall?.[1]?.body))).toEqual({ worker_id: insurerFixture.worker_id, password: 'senha de teste' })

    await user.click(screen.getByRole('button', { name: 'Sair' }))
    expect(await screen.findByRole('heading', { name: 'Entrar' })).toBeInTheDocument()
    expect(screen.queryByText('Máquina protegida')).not.toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/auth/logout', expect.objectContaining({ credentials: 'same-origin', method: 'POST' }))
  })

  it('nega URL direta de vistorias ao gestor', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => String(input) === '/api/v1/auth/me' ? jsonResponse(managerFixture) : jsonResponse({ status: 'ready' })))
    render(<SessionProvider><RouterProvider router={testRouter('/vistorias')} /></SessionProvider>)

    expect(await screen.findByRole('heading', { name: 'Você não tem acesso a esta página' })).toBeInTheDocument()
    expect(screen.queryByText('Vistorias protegidas')).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Vistorias' })).not.toBeInTheDocument()
  })

  it('permite ao administrador abrir contas e vistorias, mas nega administração ao gestor', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => String(input) === '/api/v1/auth/me' ? jsonResponse(adminFixture) : jsonResponse({ status: 'ready' })))
    render(<SessionProvider><RouterProvider router={testRouter('/admin')} /></SessionProvider>)

    expect(await screen.findByText('Administração protegida')).toBeInTheDocument()
    expect(screen.getByText(`Administrador · ${adminFixture.worker_id}`)).toBeInTheDocument()
    await user.click(screen.getByRole('link', { name: 'Vistorias' }))
    expect(await screen.findByText('Vistorias protegidas')).toBeInTheDocument()
  })

  it('nega URL direta de administração ao gestor', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => String(input) === '/api/v1/auth/me' ? jsonResponse(managerFixture) : jsonResponse({ status: 'ready' })))
    render(<SessionProvider><RouterProvider router={testRouter('/admin')} /></SessionProvider>)

    expect(await screen.findByRole('heading', { name: 'Você não tem acesso a esta página' })).toBeInTheDocument()
    expect(screen.queryByText('Administração protegida')).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Administração' })).not.toBeInTheDocument()
  })

  it('encerra a sessão quando uma chamada protegida retorna 401', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input) === '/api/v1/auth/me') return jsonResponse(insurerFixture)
      if (String(input) === '/api/health/ready') return jsonResponse({ status: 'ready' })
      return jsonResponse({ detail: 'Sessão expirada' }, 401)
    })
    vi.stubGlobal('fetch', fetchMock)
    const router = createMemoryRouter([
      { path: '/login', element: <LoginPage /> },
      { element: <RequireSession />, children: [
        { path: '/', element: <AppShell />, children: [{ index: true, element: <button type="button" onClick={() => void getTractorOverview('22222222-2222-4222-8222-222222222222', new AbortController().signal).catch(() => undefined)}>Consultar máquina</button> }] },
      ] },
    ], { initialEntries: ['/'] })
    render(<SessionProvider><RouterProvider router={router} /></SessionProvider>)

    await user.click(await screen.findByRole('button', { name: 'Consultar máquina' }))
    expect(await screen.findByRole('heading', { name: 'Entrar' })).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Consultar máquina' })).not.toBeInTheDocument())
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/tractors/22222222-2222-4222-8222-222222222222/overview', expect.any(Object))
  })
})
