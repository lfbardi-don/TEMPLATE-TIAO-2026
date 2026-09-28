import { useCallback, useEffect, useState } from 'react'
import { Link, useBlocker, useParams } from 'react-router-dom'
import { usePrincipal } from '../../app/session-context'
import { Badge } from '../../components/ui/badge'
import { Button } from '../../components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card'
import { Input } from '../../components/ui/input'
import { Label } from '../../components/ui/label'
import { usePollingResource } from '../../hooks/usePollingResource'
import { ApiHttpError, getInspectionCase, getInspectionCaseEpisode, getInspectors, getTractorOverview, updateInspectionCase } from '../../lib/api-client'
import type { FindingStatus, InspectionCase, InspectionAgendaItem, Inspectors, UpdateInspectionCaseRequest } from '../../lib/api-contracts'
import { findingNeedsNotes, formatCaseResult, formatCaseStatus, formatCondition, formatDateTime, formatFindingStatus, tractorLabel } from '../../lib/presentation'
import { LoadingView, ResourceError } from '../common/ResourceViews'
import { EpisodeSignals } from '../episode/EpisodeSignals'
import { CaseHistory } from '../machine/CaseHistory'
import './workflow.css'

type Draft = { status: FindingStatus | null; notes: string }
const statuses: FindingStatus[] = ['OK', 'ATTENTION', 'PROBLEM', 'NOT_CHECKED']

function FrozenEpisode({ caseId, episodeId, conditions, tractorId }: { caseId: string; episodeId: string; conditions: string[]; tractorId: string }) {
  const loader = useCallback((signal: AbortSignal) => getInspectionCaseEpisode(caseId, episodeId, signal), [caseId, episodeId])
  const resource = usePollingResource(loader, { successDelayMs: 300_000 })
  if (resource.state.kind === 'loading') return <LoadingView />
  if (resource.state.kind === 'error') return <ResourceError error={resource.state.error} onRetry={resource.refresh} />
  if (resource.state.kind === 'empty') return <p className="muted">Os sinais deste episódio não estão disponíveis.</p>
  return <div className="stack"><EpisodeSignals key={`${episodeId}:${conditions.join(',')}`} detail={resource.state.data} conditions={conditions} /><Link target="_blank" rel="noreferrer" to={`/tratores/${tractorId}/episodios/${episodeId}?caseId=${encodeURIComponent(caseId)}`}>Abrir detalhe completo →</Link></div>
}

function CompletionSummary({ value }: { value: InspectionCase }) {
  const loader = useCallback((signal: AbortSignal) => getTractorOverview(value.tractor_id, signal), [value.tractor_id])
  const resource = usePollingResource(loader, { successDelayMs: 60_000 })
  const overview = resource.state.kind === 'success' ? resource.state.data : null
  return <Card className="wf-completed"><CardContent className="stack"><div className="spread"><div><p className="eyebrow">Vistoria concluída</p><h2>{value.result === null ? 'Resultado registrado' : formatCaseResult(value.result)}</h2></div><Badge variant="secondary">{value.findings?.length ?? 0} achados registrados</Badge></div><p>{value.result_notes}</p><p className="muted">Dados revisados até {formatDateTime(value.evidence_as_of_utc)} UTC. Conclusão em {value.completed_at_utc === null ? '—' : `${formatDateTime(value.completed_at_utc)} UTC`}.</p>{overview === null ? <p className="muted">{resource.state.kind === 'loading' ? 'Consultando episódios após a revisão…' : 'Acompanhamento atual indisponível.'}</p> : <div className="spread"><strong>{overview.episodes_last_30_days.filter((episode) => Date.parse(episode.started_at_utc) + 60_000 > Date.parse(value.evidence_as_of_utc)).length} episódios novos no período atual</strong><Link to={`/tratores/${value.tractor_id}`}>Ver acompanhamento da máquina →</Link></div>}</CardContent></Card>
}

function AssignmentForm({ value, busy, onSave }: { value: InspectionCase; busy: boolean; onSave: (payload: UpdateInspectionCaseRequest) => Promise<void> }) {
  const [inspectors, setInspectors] = useState<Inspectors['inspectors']>([])
  const [assignee, setAssignee] = useState(value.assignee ?? '')
  const [dueDate, setDueDate] = useState(value.due_date ?? '')
  useEffect(() => { const controller = new AbortController(); void getInspectors(controller.signal).then((response) => { if (!controller.signal.aborted) setInspectors(response.inspectors) }).catch(() => undefined); return () => controller.abort() }, [])
  return <details className="wf-details"><summary>Responsável e data prevista</summary><form className="wf-open-form" onSubmit={(event) => { event.preventDefault(); void onSave({ version: value.version, action: 'UPDATE', assignee: assignee || null, due_date: dueDate || null }) }}><div className="field"><Label htmlFor="case-assignee">Vistoriador</Label><select id="case-assignee" disabled={busy} value={assignee} onChange={(event) => setAssignee(event.target.value)}><option value="">Sem responsável</option>{assignee !== '' && !inspectors.some((item) => item.worker_id === assignee) ? <option value={assignee}>{assignee}</option> : null}{inspectors.map((item) => <option key={item.id} value={item.worker_id}>Trabalhador {item.worker_id}</option>)}</select></div><div className="field"><Label htmlFor="case-due-date">Data prevista</Label><Input id="case-due-date" disabled={busy} type="date" value={dueDate} onChange={(event) => setDueDate(event.target.value)} /></div><Button type="submit" disabled={busy}>Salvar atribuição</Button></form></details>
}

function CaseWorkspace({ initial, onReload }: { initial: InspectionCase; onReload: () => void }) {
  const principal = usePrincipal()
  const [value, setValue] = useState(initial)
  const items = value.evidence_snapshot.inspection_agenda?.items ?? []
  const [selectedId, setSelectedId] = useState(items[0]?.id ?? '')
  const [episodeSelection, setEpisodeSelection] = useState<Record<string, string>>({})
  const [drafts, setDrafts] = useState<Record<string, Draft>>(() => Object.fromEntries((initial.findings ?? []).map((finding) => [finding.item_id, { status: finding.status, notes: finding.notes ?? '' }])))
  const [result, setResult] = useState<InspectionCase['result']>(initial.result)
  const [notes, setNotes] = useState(initial.result_notes ?? '')
  const [busy, setBusy] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [outcomeDirty, setOutcomeDirty] = useState(false)
  const blocker = useBlocker(dirty || outcomeDirty)
  const [message, setMessage] = useState<string | null>(null)
  const [conflict, setConflict] = useState(false)
  const [saved, setSaved] = useState<string | null>(null)
  const [cancelConfirm, setCancelConfirm] = useState(false)
  const active = value.status === 'OPEN' || value.status === 'IN_PROGRESS'
  const editable = principal.role === 'INSPECTOR' && value.status === 'IN_PROGRESS'
  const item = items.find((candidate) => candidate.id === selectedId) ?? items[0]
  const episodeId = item === undefined ? undefined : episodeSelection[item.id] ?? item.episode_ids[0]
  const draft = item === undefined ? undefined : drafts[item.id]
  const validItem = (candidate: InspectionAgendaItem) => { const finding = drafts[candidate.id]; return finding?.status != null && (!findingNeedsNotes(finding.status) || finding.notes.trim().length > 0) }
  const finished = items.filter(validItem).length
  const complete = finished === items.length && result !== null && notes.trim().length > 0
  const findings = items.flatMap((candidate) => { const finding = drafts[candidate.id]; return finding?.status == null ? [] : [{ item_id: candidate.id, status: finding.status, notes: finding.notes.trim() || null }] })
  const canSave = findings.every((finding) => !findingNeedsNotes(finding.status) || finding.notes !== null)
  const tractor = value.evidence_snapshot.tractor
  const title = tractor === undefined ? `Máquina ${value.tractor_id.slice(0, 8)}` : tractorLabel(tractor.external_id, tractor.display_name)
  useEffect(() => { if (!dirty && !outcomeDirty) return; const prevent = (event: BeforeUnloadEvent) => event.preventDefault(); window.addEventListener('beforeunload', prevent); return () => window.removeEventListener('beforeunload', prevent) }, [dirty, outcomeDirty])
  useEffect(() => {
    if (blocker.state !== 'blocked') return
    if (window.confirm('Há alterações não salvas. Sair e descartá-las?')) blocker.proceed()
    else blocker.reset()
  }, [blocker])
  function changeDraft(change: Partial<Draft>) { if (item === undefined) return; setDrafts((current) => ({ ...current, [item.id]: { ...(current[item.id] ?? { status: null, notes: '' }), ...change } })); setDirty(true); setSaved(null) }
  async function mutate(payload: UpdateInspectionCaseRequest) {
    setBusy(true); setMessage(null); setConflict(false)
    try { const next = await updateInspectionCase(value.id, payload, new AbortController().signal); setValue(next); setDirty(false); if (payload.action === 'COMPLETE') setOutcomeDirty(false); setSaved(payload.action === 'SAVE_DRAFT' ? 'Achados salvos' : null); setCancelConfirm(false) }
    catch (error: unknown) { const isConflict = error instanceof ApiHttpError && error.status === 409; setConflict(isConflict); setMessage(isConflict ? 'Este caso foi alterado por outra pessoa. Recarregue para obter a versão atual; seus rascunhos locais serão descartados.' : error instanceof ApiHttpError && error.status === 403 ? 'Seu perfil não permite esta ação.' : 'Não foi possível salvar. Seus achados continuam nesta tela para tentar novamente.') }
    finally { setBusy(false) }
  }
  function submit(action: 'SAVE_DRAFT' | 'COMPLETE') { void mutate({ version: value.version, action, findings: value.snapshot_schema_version === 'inspection-evidence-v2' ? findings : null, ...(action === 'COMPLETE' ? { result, result_notes: notes.trim() } : {}) }) }
  return <main className="page stack"><div className="page-heading"><div><p className="eyebrow">Vistoria preventiva</p><h1>{title}</h1><p className="muted">{value.evidence_snapshot.fleet?.name} · {value.assignee === null ? 'Sem responsável' : `Responsável ${value.assignee}`} · dados até {formatDateTime(value.evidence_as_of_utc)} UTC</p></div><div className="inline"><Badge variant="outline">{formatCaseStatus(value.status)}</Badge><Link to="/vistorias">Todas as vistorias</Link></div></div>
    {value.evidence_snapshot.provenance?.some((source) => source.source_kind === 'simulated_csv') ? <p className="wf-synthetic">Dados simulados</p> : null}
    {message === null ? null : <div className="wf-notice" role="alert"><p>{message}</p>{conflict ? <Button variant="secondary" onClick={onReload}>Recarregar caso</Button> : null}</div>}
    {value.status === 'COMPLETED' ? <CompletionSummary value={value} /> : null}
    {value.status === 'CANCELLED' ? <p className="wf-notice">Caso cancelado. A pauta e o histórico continuam disponíveis para consulta.</p> : null}
    {principal.role === 'INSPECTOR' && value.status === 'OPEN' ? <div className="wf-start"><div><h2>Pronto para verificar {items.length} componentes</h2><p>A pauta e os episódios correspondem aos dados preservados na abertura.</p></div><Button disabled={busy} onClick={() => void mutate({ version: value.version, action: 'START' })}>Iniciar vistoria</Button></div> : null}
    {principal.role === 'INSURER' && active ? <AssignmentForm key={value.version} value={value} busy={busy} onSave={mutate} /> : null}
    <div className="wf-workspace"><aside className="wf-checklist"><div className="spread"><h2>Pauta</h2><strong>{finished}/{items.length}</strong></div><progress aria-label="Progresso da pauta" value={finished} max={Math.max(items.length, 1)} />{items.length === 0 ? <p className="muted">Este caso não possui pauta por componente. Registre o resultado geral.</p> : <nav aria-label="Itens da vistoria">{items.map((candidate, index) => <button key={candidate.id} type="button" aria-current={item?.id === candidate.id ? 'step' : undefined} onClick={() => setSelectedId(candidate.id)}><span className={validItem(candidate) ? 'wf-item-done' : 'wf-item-number'}>{validItem(candidate) ? '✓' : index + 1}</span><span><strong>{candidate.component}</strong><small>{drafts[candidate.id]?.status == null ? `${candidate.episode_ids.length} episódios` : formatFindingStatus(drafts[candidate.id]!.status!)}</small></span></button>)}</nav>}</aside>
      <section className="wf-item-workspace" aria-label="Item selecionado">{item === undefined ? null : <><Card><CardHeader><CardTitle>{item.component}</CardTitle></CardHeader><CardContent className="stack"><p>{item.check}</p><small className="muted">{item.conditions.map(formatCondition).join(', ')}</small>{editable ? <><fieldset className="wf-findings" disabled={busy}><legend>Achado</legend>{statuses.map((status) => <label key={status} className={draft?.status === status ? 'selected' : ''}><input type="radio" name={`finding-${item.id}`} value={status} checked={draft?.status === status} onChange={() => changeDraft({ status })} />{formatFindingStatus(status)}</label>)}</fieldset><div className="field"><Label htmlFor="finding-notes">O que foi encontrado{draft?.status != null && findingNeedsNotes(draft.status) ? ' (obrigatório)' : ' (opcional)'}</Label><textarea id="finding-notes" disabled={busy} maxLength={1000} value={draft?.notes ?? ''} onChange={(event) => changeDraft({ notes: event.target.value })} /></div></> : <div className="wf-read-finding"><strong>{draft?.status == null ? 'Ainda não verificado' : formatFindingStatus(draft.status)}</strong>{draft?.notes ? <p>{draft.notes}</p> : null}</div>}</CardContent></Card>
      <Card><CardHeader><CardTitle>Episódios relacionados</CardTitle></CardHeader><CardContent className="stack">{item.episode_ids.length === 0 ? <p className="muted">Nenhum episódio ligado a este componente.</p> : <><div className="field"><Label htmlFor="related-episode">Trecho a revisar ({item.episode_ids.length})</Label><select id="related-episode" value={episodeId ?? ''} onChange={(event) => setEpisodeSelection((current) => ({ ...current, [item.id]: event.target.value }))}>{item.episode_ids.map((id, index) => { const episode = value.evidence_snapshot.episodes_last_30_days?.find((candidate) => candidate.id === id); return <option key={id} value={id}>{episode === undefined ? `Episódio ${index + 1}` : `${formatDateTime(episode.started_at_utc)} UTC`}</option> })}</select></div>{episodeId === undefined ? null : <FrozenEpisode key={`${item.id}:${episodeId}`} caseId={value.id} episodeId={episodeId} conditions={item.conditions} tractorId={value.tractor_id} />}</>}</CardContent></Card></>}
      </section>
    </div>
    {editable ? <Card><CardHeader><CardTitle>Resultado da vistoria</CardTitle></CardHeader><CardContent className="stack"><div className="wf-result-grid"><div className="field"><Label htmlFor="case-result">Resultado</Label><select id="case-result" disabled={busy} value={result ?? ''} onChange={(event) => { setResult(event.target.value === '' ? null : event.target.value as InspectionCase['result']); setOutcomeDirty(true) }}><option value="">Selecione o resultado</option><option value="NO_ACTION">Nenhuma ação</option><option value="MONITOR">Monitorar</option><option value="MAINTENANCE_RECOMMENDED">Manutenção recomendada</option></select></div><div className="field"><Label htmlFor="case-notes">Observação geral</Label><textarea id="case-notes" disabled={busy} maxLength={4000} value={notes} onChange={(event) => { setNotes(event.target.value); setOutcomeDirty(true) }} /></div></div><div className="wf-savebar"><span role="status">{saved ?? `${finished} de ${items.length} itens verificados${dirty ? ' · alterações não salvas' : ''}`}</span><div className="inline">{value.snapshot_schema_version === 'inspection-evidence-v2' ? <Button variant="secondary" disabled={busy || !canSave || !dirty} onClick={() => submit('SAVE_DRAFT')}>Salvar achados</Button> : null}<Button disabled={busy || !complete} onClick={() => submit('COMPLETE')}>Concluir vistoria</Button></div></div>{!complete ? <small className="muted">Para concluir, registre todos os itens, descreva os achados de atenção ou problema e informe o resultado geral.</small> : null}<small className="muted">Resultado e observação geral são enviados ao concluir.</small></CardContent></Card> : null}
    {principal.role === 'ADMIN' ? <Card><CardContent><CaseHistory caseId={value.id} caseVersion={value.version} /></CardContent></Card> : null}
    {principal.role === 'INSURER' && active ? <div className="inline">{cancelConfirm ? <><span>Cancelar esta vistoria?</span><Button variant="secondary" disabled={busy} onClick={() => void mutate({ version: value.version, action: 'CANCEL' })}>Confirmar cancelamento</Button><Button variant="ghost" onClick={() => setCancelConfirm(false)}>Manter caso</Button></> : <Button variant="ghost" onClick={() => setCancelConfirm(true)}>Cancelar caso</Button>}</div> : null}
  </main>
}

function InspectionCasePage() {
  const { caseId } = useParams()
  const [revision, setRevision] = useState(0)
  const [state, setState] = useState<{ value: InspectionCase | null; error: ApiHttpError | null }>({ value: null, error: null })
  useEffect(() => { if (caseId === undefined) return; const controller = new AbortController(); void getInspectionCase(caseId, controller.signal).then((value) => { if (!controller.signal.aborted) setState({ value, error: null }) }).catch((error: unknown) => { if (!controller.signal.aborted) setState({ value: null, error: error instanceof ApiHttpError ? error : new ApiHttpError('network', 'Não foi possível carregar a vistoria.') }) }); return () => controller.abort() }, [caseId, revision])
  function reload() { setState({ value: null, error: null }); setRevision((value) => value + 1) }
  if (state.error !== null) return <main className="page"><ResourceError error={state.error} onRetry={reload} /></main>
  if (state.value === null) return <main className="page"><LoadingView /></main>
  return <CaseWorkspace key={`${state.value.id}:${revision}`} initial={state.value} onReload={reload} />
}
export { InspectionCasePage }
