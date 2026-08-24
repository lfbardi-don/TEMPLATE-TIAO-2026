import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { RegisterFleetPage } from './RegisterFleetPage'
import { registrationFixture } from '../../test/fixtures'

describe('RegisterFleetPage', () => {
  beforeEach(() => window.localStorage.clear())

  it('envia somente um POST e não reutiliza a mesma telemetria entre tratores', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response(JSON.stringify(registrationFixture), { status: 201, headers: { 'Content-Type': 'application/json' } }))
    vi.stubGlobal('fetch', fetchMock)
    render(<MemoryRouter><RegisterFleetPage /></MemoryRouter>)

    await user.type(screen.getByLabelText('Nome da frota'), 'Frota A')
    await user.type(screen.getByLabelText('Identificador externo'), 'T-01')
    await user.click(screen.getByRole('button', { name: 'Cadastrar frota' }))

    expect(await screen.findByText('Frota cadastrada')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({ method: 'POST' })
    expect(screen.getByText(/cada unidade exige uma importação de telemetria observada própria/i)).toBeInTheDocument()
    expect(screen.getByText(/não existe comando automático/i)).toBeInTheDocument()
  })

  it('mostra a validação sem enviar requisição', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    render(<MemoryRouter><RegisterFleetPage /></MemoryRouter>)

    await user.click(screen.getByRole('button', { name: 'Cadastrar frota' }))

    expect(screen.getByText(/nome de frota entre/)).toBeInTheDocument()
    const summary = screen.getByText('Revise o cadastro').closest('[tabindex="-1"]')
    await waitFor(() => expect(summary).toHaveFocus())
    expect(fetchMock).not.toHaveBeenCalled()
  })

})
