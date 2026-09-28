import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Button } from '../../components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card'
import { Input } from '../../components/ui/input'
import { Label } from '../../components/ui/label'
import { usePollingResource } from '../../hooks/usePollingResource'
import { usePrincipal } from '../../app/session-context'
import { ApiHttpError, createInspectionCase, getInspectionCases, getInspectors } from '../../lib/api-client'
import type { Inspectors, TractorOverview } from '../../lib/api-contracts'
import { formatCaseResult, formatCaseStatus, formatDateTime } from '../../lib/presentation'
import { LoadingView, ResourceError } from '../common/ResourceViews'

function InspectionCasesPanel({ tractorId, workflow }: { tractorId: string; workflow?: TractorOverview['workflow'] }) {
  const principal = usePrincipal()
  const navigate = useNavigate()
  const loader = useCallback((signal: AbortSignal) => getInspectionCases(tractorId, signal), [tractorId])
  const resource = usePollingResource(loader, { successDelayMs: 30_000 })
  const [opening, setOpening] = useState(false)
  const [assignee, setAssignee] = useState('')
  const [inspectors, setInspectors] = useState<Inspectors['inspectors']>([])
  const [dueDate, setDueDate] = useState('')
  const [message, setMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    if (!opening) return
    const controller = new AbortController()
    void getInspectors(controller.signal).then((value) => { if (!controller.signal.aborted) setInspectors(value.inspectors) }).catch(() => undefined)
    return () => controller.abort()
  }, [opening])
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setMessage(null)
    try {
      const value = await createInspectionCase(tractorId, { assignee: assignee || null, due_date: dueDate || null }, new AbortController().signal)
      navigate(`/vistorias/${value.id}`)
    } catch (error: unknown) { setMessage(error instanceof ApiHttpError && error.status === 409 ? 'Já existe um caso ativo ou estes episódios já foram revisados. Atualize a página.' : 'Não foi possível abrir a vistoria. Tente novamente.'); resource.refresh() } finally { setBusy(false) }
  }
  if (resource.state.kind === 'loading') return <LoadingView />
  if (resource.state.kind === 'error') return <ResourceError error={resource.state.error} onRetry={resource.refresh} />
  const cases = resource.state.kind === 'success' ? resource.state.data.cases : []
  const active = cases.find((item) => item.status === 'OPEN' || item.status === 'IN_PROGRESS')
  const completed = cases.find((item) => item.status === 'COMPLETED')
  const canOpen = workflow?.can_open_case ?? active === undefined
  return <Card className="wf-case-cta" role="region" aria-labelledby="cases-heading"><CardHeader><div className="spread"><CardTitle id="cases-heading">Vistoria preventiva</CardTitle><Link to="/vistorias">Todas as vistorias →</Link></div></CardHeader><CardContent className="stack">
    <div className="spread"><div>{active !== undefined ? <><strong>{formatCaseStatus(active.status)}</strong><p className="muted">{active.assignee === null ? 'Aguardando atribuição' : `Responsável: ${active.assignee}`} · pauta preservada em {formatDateTime(active.evidence_as_of_utc)} UTC</p></> : completed !== undefined ? <><strong>Última vistoria concluída{completed.result === null ? '' : ` · ${formatCaseResult(completed.result)}`}</strong><p className="muted">Dados revisados até {formatDateTime(completed.evidence_as_of_utc)} UTC · {workflow?.new_episode_ids.length ?? 0} episódios novos no período</p></> : <p className="muted">{!canOpen ? 'Nenhum episódio pendente de vistoria no período.' : principal.role === 'INSURER' ? 'Abra uma vistoria para transformar os episódios em uma pauta de verificação.' : 'O especialista da seguradora abre a vistoria a partir dos episódios observados.'}</p>}</div>
    {active !== undefined ? <Link className="ui-button ui-button-primary ui-button-default" to={`/vistorias/${active.id}`}>{principal.role === 'INSPECTOR' ? 'Continuar vistoria' : 'Ver vistoria'}</Link> : principal.role === 'INSURER' && canOpen ? <Button onClick={() => setOpening(!opening)}>{opening ? 'Fechar formulário' : 'Abrir vistoria'}</Button> : completed !== undefined ? <Link className="ui-button ui-button-secondary ui-button-default" to={`/vistorias/${completed.id}`}>Ver resultado</Link> : <span className="muted">Nenhuma vistoria aberta</span>}</div>
    {!canOpen && active === undefined && completed !== undefined && principal.role === 'INSURER' ? <p className="muted">Os episódios atuais já foram revisados. Novos episódios permitem abrir outra vistoria.</p> : null}
    {message === null ? null : <p role="alert" className="field-error">{message}</p>}
    {opening && canOpen && principal.role === 'INSURER' ? <form className="wf-open-form" onSubmit={(event) => void create(event)}><div className="field"><Label htmlFor="inspection-assignee">Vistoriador (opcional)</Label><select id="inspection-assignee" value={assignee} onChange={(event) => setAssignee(event.target.value)}><option value="">Sem responsável</option>{inspectors.map((inspector) => <option key={inspector.id} value={inspector.worker_id}>Trabalhador {inspector.worker_id}</option>)}</select></div><div className="field"><Label htmlFor="inspection-due-date">Data prevista (opcional)</Label><Input id="inspection-due-date" type="date" value={dueDate} onChange={(event) => setDueDate(event.target.value)} /></div><Button disabled={busy} type="submit">{busy ? 'Abrindo…' : 'Confirmar abertura'}</Button></form> : null}
  </CardContent></Card>
}
export { InspectionCasesPanel }
