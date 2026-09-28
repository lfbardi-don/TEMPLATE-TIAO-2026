import { useState } from 'react'
import { Link } from 'react-router-dom'
import { usePrincipal } from '../../app/session-context'
import { Badge } from '../../components/ui/badge'
import { Button } from '../../components/ui/button'
import { Card, CardContent } from '../../components/ui/card'
import { usePollingResource } from '../../hooks/usePollingResource'
import { getAllInspectionCases } from '../../lib/api-client'
import type { InspectionCase } from '../../lib/api-contracts'
import { formatCaseStatus, formatDateTime, tractorLabel } from '../../lib/presentation'
import { LoadingView, ResourceError } from '../common/ResourceViews'
import './workflow.css'

function InspectionListPage() {
  const principal = usePrincipal()
  const resource = usePollingResource(getAllInspectionCases, { successDelayMs: 30_000 })
  const [status, setStatus] = useState('active')
  const [mine, setMine] = useState(false)
  const data = resource.state.kind === 'success' || resource.state.kind === 'error' ? resource.state.data : null
  const cases = data?.cases ?? []
  const visible = cases.filter((value) => (status === 'all' || (status === 'active' ? ['OPEN', 'IN_PROGRESS'].includes(value.status) : value.status === status)) && (!mine || value.assignee === principal.worker_id))
  function machineName(value: InspectionCase) { const tractor = value.evidence_snapshot.tractor; return tractor === undefined ? `Máquina ${value.tractor_id.slice(0, 8)}` : tractorLabel(tractor.external_id, tractor.display_name) }
  return <main className="page stack"><div className="page-heading"><div><p className="eyebrow">Vistorias</p><h1>Pauta de trabalho</h1><p className="muted">Acompanhe os casos e registre o que foi encontrado.</p></div><Button variant="secondary" onClick={resource.refresh}>Atualizar</Button></div>
    <div className="wf-filters" aria-label="Filtrar vistorias">{[['active', 'Em aberto'], ['COMPLETED', 'Concluídas'], ['CANCELLED', 'Canceladas'], ['all', 'Todas']].map(([value, label]) => <button key={value} type="button" aria-pressed={status === value} onClick={() => setStatus(value!)}>{label}</button>)}{principal.role === 'INSPECTOR' ? <label className="wf-checkbox"><input type="checkbox" checked={mine} onChange={(event) => setMine(event.target.checked)} /> Minhas vistorias</label> : null}</div>
    {resource.state.kind === 'loading' ? <LoadingView /> : resource.state.kind === 'error' ? <ResourceError error={resource.state.error} onRetry={resource.refresh} /> : null}
    {data !== null && visible.length === 0 ? <Card><CardContent className="empty"><h2>Nenhuma vistoria neste filtro</h2><p>Abra uma máquina para revisar os episódios e iniciar o próximo caso.</p><Link to="/">Ver máquinas</Link></CardContent></Card> : <div className="wf-case-list">{visible.map((value) => {
      const total = value.evidence_snapshot.inspection_agenda?.items.length ?? 0
      const completed = value.findings?.length ?? 0
      return <Link key={value.id} className="wf-case-list-item" to={`/vistorias/${value.id}`}><div><Badge variant={value.status === 'COMPLETED' ? 'secondary' : 'outline'}>{formatCaseStatus(value.status)}</Badge><h2>{machineName(value)}</h2><p className="muted">{value.evidence_snapshot.fleet?.name ?? 'Frota'} · {value.assignee === null ? 'Sem responsável' : `Responsável ${value.assignee}`}</p></div><div className="wf-case-progress"><strong>{completed}/{total} itens</strong><progress value={completed} max={Math.max(total, 1)} /><small className="muted">{value.due_date === null ? `Aberto em ${formatDateTime(value.created_at_utc)} UTC` : `Prevista: ${value.due_date}`}</small></div><span aria-hidden="true">→</span></Link>
    })}</div>}
  </main>
}
export { InspectionListPage }
