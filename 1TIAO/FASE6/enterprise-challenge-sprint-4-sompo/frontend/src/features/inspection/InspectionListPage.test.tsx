import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { jsonResponse, stubApi } from '../../test/api-stub'
import { completedCaseFixture, inProgressCaseFixture } from '../../test/fixtures'
import { SessionFixture } from '../../test/session'
import { inspectorFixture } from '../../test/session-fixtures'
import { InspectionListPage } from './InspectionListPage'
afterEach(() => vi.unstubAllGlobals())
it('filtra casos por andamento e responsável e abre o workspace', async () => {
  stubApi(() => jsonResponse({ evidence_role: 'operational_output_only', cases: [{ ...inProgressCaseFixture, assignee: inspectorFixture.worker_id }, { ...completedCaseFixture, id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa' }] }))
  render(<SessionFixture principal={inspectorFixture}><MemoryRouter><InspectionListPage /></MemoryRouter></SessionFixture>)
  const active = await screen.findByRole('link', { name: /Em vistoria/ })
  expect(active).toHaveAttribute('href', `/vistorias/${inProgressCaseFixture.id}`)
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: 'Concluídas' }))
  expect(screen.getByRole('link', { name: /Concluído/ })).toBeInTheDocument()
  await user.click(screen.getByRole('checkbox', { name: 'Minhas vistorias' }))
  expect(screen.getByText('Nenhuma vistoria neste filtro')).toBeInTheDocument()
})
