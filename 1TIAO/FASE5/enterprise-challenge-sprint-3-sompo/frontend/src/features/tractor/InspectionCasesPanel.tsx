import { useCallback, useState, type FormEvent } from 'react'
import { Alert, AlertDescription, AlertTitle } from '../../components/ui/alert'
import { Button } from '../../components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card'
import { Input } from '../../components/ui/input'
import { Label } from '../../components/ui/label'
import { usePollingResource } from '../../hooks/usePollingResource'
import { ApiHttpError, createInspectionCase, getInspectionCases, updateInspectionCase } from '../../lib/api-client'
import type { InspectionCase, UpdateInspectionCaseRequest } from '../../lib/api-contracts'
import { formatDateTime } from '../../lib/presentation'
import { LoadingView, ResourceError } from '../common/ResourceViews'

function InspectionCasesPanel({ tractorId }: { tractorId: string | undefined }) {
  const loader = useCallback(
    (signal: AbortSignal) => tractorId === undefined
      ? Promise.reject(new Error('Identificador de trator ausente.'))
      : getInspectionCases(tractorId, signal),
    [tractorId],
  )
  const resource = usePollingResource(loader)
  const [assignee, setAssignee] = useState('')
  const [dueDate, setDueDate] = useState('')
  const [result, setResult] = useState<InspectionCase['result']>(null)
  const [notes, setNotes] = useState('')
  const [message, setMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function create(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault()
    if (tractorId === undefined) return
    setBusy(true); setMessage(null)
    try {
      await createInspectionCase(tractorId, { assignee: assignee.trim() || null, due_date: dueDate || null }, new AbortController().signal)
      setAssignee(''); setDueDate('')
      resource.refresh()
    } catch (error: unknown) { setMessage(errorMessage(error)) } finally { setBusy(false) }
  }

  async function transition(value: InspectionCase, action: UpdateInspectionCaseRequest['action']): Promise<void> {
    setBusy(true); setMessage(null)
    const payload: UpdateInspectionCaseRequest = {
      version: value.version,
      action,
      assignee: value.assignee,
      due_date: value.due_date,
      result: action === 'COMPLETE' ? result : null,
      result_notes: action === 'COMPLETE' ? notes : null,
    }
    try {
      await updateInspectionCase(value.id, payload, new AbortController().signal)
      setResult(null); setNotes('')
      resource.refresh()
    } catch (error: unknown) { setMessage(errorMessage(error)); resource.refresh() } finally { setBusy(false) }
  }

  if (resource.state.kind === 'loading') return <LoadingView />
  if (resource.state.kind === 'empty') return <Card><CardHeader><CardTitle>Casos de inspeção</CardTitle></CardHeader><CardContent><p>O histórico de casos estará disponível quando o trator existir.</p></CardContent></Card>
  if (resource.state.kind === 'error') return <ResourceError error={resource.state.error} onRetry={resource.refresh} />
  const cases = resource.state.data.cases
  const active = cases.find((item) => item.status === 'OPEN' || item.status === 'IN_PROGRESS')

  return <Card><CardHeader><CardTitle>Casos de inspeção</CardTitle></CardHeader><CardContent className="stack">
    <p className="muted">O caso preserva o snapshot operacional gerado no servidor. Ele registra revisão preventiva, não um diagnóstico.</p>
    {message === null ? null : <Alert variant="destructive"><AlertTitle>Operação não concluída</AlertTitle><AlertDescription>{message}</AlertDescription></Alert>}
    <form className="grid two" onSubmit={(event) => void create(event)}>
      <div className="field"><Label htmlFor="inspection-assignee">Responsável (opcional)</Label><Input id="inspection-assignee" value={assignee} onChange={(event) => setAssignee(event.target.value)} disabled={busy || active !== undefined} /></div>
      <div className="field"><Label htmlFor="inspection-due-date">Data prevista (opcional)</Label><Input id="inspection-due-date" type="date" value={dueDate} onChange={(event) => setDueDate(event.target.value)} disabled={busy || active !== undefined} /></div>
      <div><Button type="submit" disabled={busy || active !== undefined}>{active === undefined ? 'Criar caso de inspeção' : 'Há um caso ativo'}</Button></div>
    </form>
    {cases.length === 0 ? <p>Nenhum caso de inspeção foi criado.</p> : <div className="stack">{cases.map((item) => <CaseRow key={item.id} value={item} busy={busy} result={result} notes={notes} setResult={setResult} setNotes={setNotes} onTransition={transition} />)}</div>}
  </CardContent></Card>
}

function CaseRow({ value, busy, result, notes, setResult, setNotes, onTransition }: {
  value: InspectionCase; busy: boolean; result: InspectionCase['result']; notes: string
  setResult: (value: InspectionCase['result']) => void; setNotes: (value: string) => void
  onTransition: (value: InspectionCase, action: UpdateInspectionCaseRequest['action']) => Promise<void>
}) {
  const active = value.status === 'OPEN' || value.status === 'IN_PROGRESS'
  return <section className="stack"><dl className="detail-list"><dt>Estado</dt><dd>{value.status}</dd><dt>Versão</dt><dd>{value.version}</dd><dt>Responsável</dt><dd>{value.assignee ?? 'Não atribuído'}</dd><dt>Data prevista</dt><dd>{value.due_date ?? 'Não definida'}</dd><dt>Snapshot</dt><dd><code>{value.evidence_sha256.slice(0, 12)}…</code> · {formatDateTime(value.evidence_as_of_utc)} UTC</dd>{value.result === null ? null : <><dt>Resultado</dt><dd>{value.result}</dd><dt>Observação</dt><dd>{value.result_notes}</dd></>}</dl>
    {!active ? null : <div className="stack"><div className="inline">{value.status === 'OPEN' ? <Button type="button" variant="secondary" disabled={busy} onClick={() => void onTransition(value, 'START')}>Iniciar caso</Button> : null}<Button type="button" variant="ghost" disabled={busy} onClick={() => void onTransition(value, 'CANCEL')}>Cancelar caso</Button></div>
      {value.status !== 'IN_PROGRESS' ? null : <div className="stack"><div className="field"><Label htmlFor={`inspection-result-${value.id}`}>Resultado da revisão</Label><select id={`inspection-result-${value.id}`} value={result ?? ''} onChange={(event) => setResult(event.target.value === '' ? null : event.target.value as InspectionCase['result'])}><option value="">Selecione</option><option value="NO_ACTION">Nenhuma ação</option><option value="MONITOR">Monitorar</option><option value="MAINTENANCE_RECOMMENDED">Manutenção recomendada</option></select></div><div className="field"><Label htmlFor={`inspection-notes-${value.id}`}>Observação</Label><textarea id={`inspection-notes-${value.id}`} maxLength={4000} value={notes} onChange={(event) => setNotes(event.target.value)} /></div><Button type="button" disabled={busy || result === null || notes.trim().length === 0} onClick={() => void onTransition(value, 'COMPLETE')}>Concluir caso</Button></div>}
    </div>}
  </section>
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiHttpError && error.code === 'STALE_INSPECTION_CASE_VERSION') return 'O caso foi atualizado. A lista foi recarregada; revise antes de tentar novamente.'
  if (error instanceof ApiHttpError && error.code === 'INVALID_INSPECTION_TRANSITION') return 'A transição não é permitida para o estado atual do caso.'
  if (error instanceof ApiHttpError && error.status === 409) return 'Já existe um caso ativo ou o estado persistido entrou em conflito.'
  return 'Não foi possível concluir a operação. Atualize a lista e tente novamente.'
}

export { InspectionCasesPanel }
