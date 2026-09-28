import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { InspectionCasesPanel } from './InspectionCasesPanel'

describe('InspectionCasesPanel', () => {
  it('permite criar um caso quando não há caso ativo', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ evidence_role: 'operational_output_only', cases: [] }), { status: 200 })))

    render(<InspectionCasesPanel tractorId="22222222-2222-4222-8222-222222222222" />)

    expect(await screen.findByText('Casos de inspeção')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Criar caso de inspeção' })).toBeEnabled()
    expect(screen.getByText(/não um diagnóstico/)).toBeInTheDocument()
  })
})
