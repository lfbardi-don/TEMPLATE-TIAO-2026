import { useEffect, useState } from 'react'
import { Button } from '../../components/ui/button'
import { getInspectionCaseEvents } from '../../lib/api-client'
import type { InspectionCaseEvent, InspectionCaseEvents } from '../../lib/api-contracts'
import { formatCaseResult, formatCaseStatus, formatDateTime, formatFindingStatus } from '../../lib/presentation'

type HistoryState =
  | { kind: 'idle' | 'loading' | 'error' }
  | { kind: 'ready'; caseVersion: number; value: InspectionCaseEvents }

const actionNames: Record<InspectionCaseEvent['action'], string> = {
  CREATE: 'Caso aberto',
  UPDATE: 'Dados atualizados',
  START: 'Vistoria iniciada',
  SAVE_DRAFT: 'Achados salvos',
  COMPLETE: 'Vistoria concluída',
  CANCEL: 'Caso cancelado',
}

const roleNames: Record<InspectionCaseEvent['actor_role'], string> = {
  ADMIN: 'administrador',
  INSURER: 'especialista da seguradora',
  INSPECTOR: 'vistoriador',
  FLEET_MANAGER: 'gestor da frota',
}

function optionalValue(value: string | null): string {
  return value ?? 'Não definido'
}

function eventDetails(event: InspectionCaseEvent): string | null {
  if (event.action === 'CREATE') {
    return `Vistoriador: ${optionalValue(event.details.assignee)} · Data prevista: ${optionalValue(event.details.due_date)}`
  }
  if (event.action === 'UPDATE') {
    const { assignee, due_date: dueDate } = event.details.changes
    const changes = [
      assignee === undefined ? null : `Vistoriador: ${optionalValue(assignee.from)} → ${optionalValue(assignee.to)}`,
      dueDate === undefined ? null : `Data prevista: ${optionalValue(dueDate.from)} → ${optionalValue(dueDate.to)}`,
    ].filter((change) => change !== null)
    return changes.length === 0 ? null : changes.join(' · ')
  }
  if (event.action === 'COMPLETE') {
    const counts = Object.entries(event.details.finding_status_counts)
      .filter(([, count]) => count > 0)
      .map(([status, count]) => `${count} ${formatFindingStatus(status as keyof typeof event.details.finding_status_counts).toLowerCase()}`)
    return `Resultado: ${formatCaseResult(event.details.result)}${counts.length === 0 ? ' · Sem achados por item' : ` · Achados: ${counts.join(', ')}`}`
  }
  return null
}

function CaseHistory({ caseId, caseVersion }: { caseId: string; caseVersion: number }) {
  const [open, setOpen] = useState(false)
  const [retry, setRetry] = useState(0)
  const [state, setState] = useState<HistoryState>({ kind: 'idle' })

  useEffect(() => {
    if (!open) return
    const controller = new AbortController()
    void getInspectionCaseEvents(caseId, controller.signal)
      .then((value) => { if (!controller.signal.aborted) setState({ kind: 'ready', caseVersion, value }) })
      .catch(() => { if (!controller.signal.aborted) setState({ kind: 'error' }) })
    return () => controller.abort()
  }, [caseId, caseVersion, open, retry])

  const visibleState: HistoryState = state.kind === 'ready' && state.caseVersion !== caseVersion ? { kind: 'loading' } : state

  return <details className="case-history" onToggle={(event) => { setOpen(event.currentTarget.open); if (event.currentTarget.open) setState({ kind: 'loading' }) }}>
    <summary>Histórico de ações</summary>
    {visibleState.kind === 'idle' || visibleState.kind === 'loading' ? <p className="muted" role="status">Carregando histórico…</p> : null}
    {visibleState.kind === 'error' ? <div role="alert" className="stack"><p>Não foi possível carregar o histórico deste caso.</p><div><Button type="button" variant="secondary" onClick={() => setRetry((value) => value + 1)}>Tentar novamente</Button></div></div> : null}
    {visibleState.kind === 'ready' && visibleState.value.events.length === 0 ? <p className="muted">Este caso não tem ações registradas no histórico.</p> : null}
    {visibleState.kind === 'ready' && visibleState.value.events.length > 0 ? <ol className="case-events">{[...visibleState.value.events].sort((left, right) => right.case_version - left.case_version).map((event) => {
      const details = eventDetails(event)
      return <li key={event.id}>
        <div className="spread"><strong>{actionNames[event.action]}</strong><time dateTime={event.occurred_at_utc}>{formatDateTime(event.occurred_at_utc)} UTC</time></div>
        <p>Trabalhador {event.actor_worker_id} · {roleNames[event.actor_role]}</p>
        <p className="muted">{event.prior_status === null ? `Estado: ${formatCaseStatus(event.new_status)}` : `${formatCaseStatus(event.prior_status)} → ${formatCaseStatus(event.new_status)}`} · versão {event.case_version}</p>
        {details === null ? null : <p className="muted">{details}</p>}
      </li>
    })}</ol> : null}
  </details>
}

export { CaseHistory }
