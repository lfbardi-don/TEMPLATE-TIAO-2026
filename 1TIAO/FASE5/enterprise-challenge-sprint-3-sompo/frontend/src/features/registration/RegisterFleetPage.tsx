import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { Alert, AlertDescription, AlertTitle } from '../../components/ui/alert'
import { Button } from '../../components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card'
import { Input } from '../../components/ui/input'
import { Label } from '../../components/ui/label'
import { Separator } from '../../components/ui/separator'
import { ApiHttpError, createFleet } from '../../lib/api-client'
import type { FleetRegistration } from '../../lib/api-contracts'
import { readLastRegistration, writeLastRegistration } from './registration-storage'
import { hasRegistrationErrors, toCreateFleetRequest, validateRegistration, type RegistrationDraft, type RegistrationErrors, type TractorDraft } from './validation'

function newTractorDraft(formId: string): TractorDraft {
  return { formId, externalId: '', displayName: '' }
}

function submitErrorMessage(error: unknown): string {
  if (!(error instanceof ApiHttpError)) return 'O cadastro não foi concluído. Tente novamente quando a API local estiver disponível.'
  if (error.kind === 'network') return 'Não foi possível alcançar a API local. Verifique se ela está ativa em 127.0.0.1:8000.'
  if (error.status === 409) return 'A frota ou um identificador externo já existe. Ajuste os dados e tente novamente.'
  if (error.status === 422) return 'A API recusou os dados enviados. Revise os campos e tente novamente.'
  if (error.status === 503) return 'A API local está indisponível porque uma dependência não está pronta. Tente novamente mais tarde.'
  if (error.status !== null && error.status >= 500) return 'A API local encontrou uma indisponibilidade. Tente novamente mais tarde.'
  return 'A API respondeu com um erro inesperado. Tente novamente manualmente.'
}

async function copyText(value: string): Promise<'copied' | 'manual'> {
  if (!navigator.clipboard?.writeText) return 'manual'
  try {
    await navigator.clipboard.writeText(value)
    return 'copied'
  } catch (error: unknown) {
    if (error instanceof DOMException || error instanceof Error) return 'manual'
    throw error
  }
}

function RegistrationResult({ registration }: { registration: FleetRegistration }) {
  const [copyStatus, setCopyStatus] = useState('')

  async function copy(value: string, successMessage: string): Promise<void> {
    const result = await copyText(value)
    setCopyStatus(result === 'copied' ? successMessage : 'Não foi possível copiar automaticamente. Selecione e copie o valor exibido.')
  }

  return (
    <section className="stack" aria-labelledby="registration-result-heading">
      <Alert><AlertTitle id="registration-result-heading">Frota cadastrada</AlertTitle><AlertDescription>Cada unidade exige uma importação de telemetria observada própria. O recorte de validação no repositório é a referência da demonstração Fendt 314 e não deve ser reutilizado para clonar evidência entre tratores.</AlertDescription></Alert>
      <Card><CardHeader><CardTitle>{registration.fleet.name}</CardTitle></CardHeader><CardContent className="stack">
        <div className="inline"><Link to={`/frotas/${registration.fleet.id}`}>Abrir visão da frota</Link><Link to="/prioridades">Ver fila global</Link></div>
        <Separator />
        {registration.tractors.map((tractor) => {
          return (
            <article className="stack" key={tractor.id}>
              <div className="spread"><div><h3>{tractor.display_name ?? tractor.external_id}</h3><p className="muted">{tractor.model_name} · {tractor.external_id}</p></div><Link to={`/tratores/${tractor.id}`}>Abrir detalhe</Link></div>
              <div className="inline"><dl className="detail-list"><dt>UUID do trator</dt><dd><code>{tractor.id}</code></dd></dl><Button type="button" size="sm" variant="secondary" onClick={() => void copy(tractor.id, 'UUID copiado.')}>Copiar UUID</Button></div>
              <p className="muted">Depois de importar o arquivo observado específico desta unidade, execute o replay com o <code>import_id</code> retornado. Não existe comando automático porque a origem deve ser distinta por trator.</p>
              <span className="copy-status" aria-live="polite">{copyStatus}</span>
            </article>
          )
        })}
      </CardContent></Card>
    </section>
  )
}

function RegisterFleetPage() {
  const nextDraftId = useRef(1)
  const [draft, setDraft] = useState<RegistrationDraft>(() => ({ name: '', tractors: [newTractorDraft('tractor-1')] }))
  const [errors, setErrors] = useState<RegistrationErrors>({ tractors: {} })
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [registration, setRegistration] = useState<FleetRegistration | null>(readLastRegistration)
  const postController = useRef<AbortController | null>(null)
  const errorSummary = useRef<HTMLDivElement | null>(null)

  useEffect(() => () => postController.current?.abort(), [])

  function updateTractor(formId: string, field: 'externalId' | 'displayName', value: string) {
    setDraft((current) => ({ ...current, tractors: current.tractors.map((tractor) => tractor.formId === formId ? { ...tractor, [field]: value } : tractor) }))
  }

  function addTractor() {
    nextDraftId.current += 1
    setDraft((current) => ({ ...current, tractors: [...current.tractors, newTractorDraft(`tractor-${nextDraftId.current}`)] }))
  }

  function removeTractor(formId: string) {
    setDraft((current) => ({ ...current, tractors: current.tractors.filter((tractor) => tractor.formId !== formId) }))
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault()
    const validation = validateRegistration(draft)
    setErrors(validation)
    setSubmitError(null)
    if (hasRegistrationErrors(validation)) {
      window.requestAnimationFrame(() => errorSummary.current?.focus())
      return
    }
    const controller = new AbortController()
    postController.current = controller
    setIsSubmitting(true)
    try {
      const result = await createFleet(toCreateFleetRequest(draft), controller.signal)
      if (!controller.signal.aborted) {
        writeLastRegistration(result)
        setRegistration(result)
      }
    } catch (error: unknown) {
      if (!controller.signal.aborted) setSubmitError(submitErrorMessage(error))
    } finally {
      if (!controller.signal.aborted) setIsSubmitting(false)
    }
  }

  return (
    <main className="page">
      <div className="page-heading"><div><p className="eyebrow">Cadastro local</p><h1>Cadastre uma frota para inspeção preventiva</h1><p className="muted">Crie tratores Fendt 314 e preserve uma importação observada distinta para cada unidade.</p></div></div>
      <div className="grid two">
        <Card><CardHeader><CardTitle>Dados da frota</CardTitle></CardHeader><CardContent>
          <form onSubmit={(event) => void onSubmit(event)} noValidate>
            <div className="field"><Label htmlFor="fleet-name">Nome da frota</Label><Input id="fleet-name" value={draft.name} onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))} aria-invalid={errors.name !== undefined} aria-describedby={errors.name === undefined ? undefined : 'fleet-name-error'} />{errors.name === undefined ? null : <p id="fleet-name-error" className="field-error">{errors.name}</p>}</div>
            <div className="stack" style={{ marginTop: '20px' }}>
              <div className="spread"><h2>Tratores</h2><Button type="button" size="sm" variant="secondary" onClick={addTractor}>Adicionar trator</Button></div>
              {draft.tractors.map((tractor, index) => {
                const tractorErrors = errors.tractors[tractor.formId]
                const externalErrorId = `${tractor.formId}-external-error`
                const displayErrorId = `${tractor.formId}-display-error`
                return <div className="tractor-form stack" key={tractor.formId}><div className="spread"><h3>Trator {index + 1}</h3>{draft.tractors.length > 1 ? <Button type="button" size="sm" variant="ghost" onClick={() => removeTractor(tractor.formId)}>Remover</Button> : null}</div><div className="field"><Label htmlFor={`${tractor.formId}-external`}>Identificador externo</Label><Input id={`${tractor.formId}-external`} value={tractor.externalId} onChange={(event) => updateTractor(tractor.formId, 'externalId', event.target.value)} aria-invalid={tractorErrors?.externalId !== undefined} aria-describedby={tractorErrors?.externalId === undefined ? undefined : externalErrorId} />{tractorErrors?.externalId === undefined ? null : <p id={externalErrorId} className="field-error">{tractorErrors.externalId}</p>}</div><div className="field"><Label htmlFor={`${tractor.formId}-display`}>Nome de exibição (opcional)</Label><Input id={`${tractor.formId}-display`} value={tractor.displayName} onChange={(event) => updateTractor(tractor.formId, 'displayName', event.target.value)} aria-invalid={tractorErrors?.displayName !== undefined} aria-describedby={tractorErrors?.displayName === undefined ? undefined : displayErrorId} />{tractorErrors?.displayName === undefined ? null : <p id={displayErrorId} className="field-error">{tractorErrors.displayName}</p>}</div></div>
              })}
            </div>
            {hasRegistrationErrors(errors) ? <div ref={errorSummary} tabIndex={-1}><Alert variant="destructive" style={{ marginTop: '20px' }}><AlertTitle>Revise o cadastro</AlertTitle><AlertDescription>Corrija os campos destacados antes de enviar novamente.{errors.form === undefined ? '' : ` ${errors.form}`}</AlertDescription></Alert></div> : null}
            {submitError === null ? null : <Alert variant="destructive" style={{ marginTop: '20px' }}><AlertTitle>Cadastro não concluído</AlertTitle><AlertDescription>{submitError}</AlertDescription></Alert>}
            <div className="form-actions"><Button type="submit" disabled={isSubmitting}>{isSubmitting ? 'Cadastrando…' : 'Cadastrar frota'}</Button><span aria-live="polite">{isSubmitting ? 'Uma única solicitação de cadastro está em andamento.' : ''}</span></div>
          </form>
        </CardContent></Card>
        <div className="stack">
          <Card><CardHeader><CardTitle>Como funciona</CardTitle></CardHeader><CardContent><ol><li>Cadastre a frota e copie o UUID da unidade.</li><li>Importe a telemetria observada própria daquela unidade.</li><li>Use o <code>import_id</code> retornado para executar o replay persistido e abra as evidências.</li></ol><p className="muted">O navegador não envia arquivos nem executa importação ou replay. O recorte versionado é exclusivo da demonstração observada.</p></CardContent></Card>
          {registration === null ? null : <RegistrationResult registration={registration} />}
        </div>
      </div>
    </main>
  )
}

export { RegisterFleetPage }
