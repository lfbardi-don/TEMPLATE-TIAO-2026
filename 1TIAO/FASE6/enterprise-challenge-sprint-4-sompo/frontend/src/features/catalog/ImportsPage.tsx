import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { usePrincipal } from '../../app/session-context'
import { Button } from '../../components/ui/button'
import { usePollingResource } from '../../hooks/usePollingResource'
import { formatDateTime, formatNumber } from '../../lib/presentation'
import { ResourceError } from '../common/ResourceViews'
import { MachineDataLayout } from './MachineDataLayout'
import { getCsvScenarios, getImports, importCsv, intakeError, previewCsv, sourceLabel, type CsvScenario, type CsvUpload, type ImportPreview, type ImportResult } from './intake-client'

function CsvImporter({ tractorId, onImported }: { tractorId: string; onImported: () => void }) {
  const [source, setSource] = useState<CsvUpload['source_kind']>('simulated_csv')
  const [payload, setPayload] = useState<CsvUpload | null>(null)
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [result, setResult] = useState<ImportResult | null>(null)
  const [stage, setStage] = useState<'idle' | 'validating' | 'ready' | 'processing' | 'done'>('idle')
  const [error, setError] = useState<string | null>(null)
  const [scenarios, setScenarios] = useState<CsvScenario[]>([])
  const request = useRef<AbortController | null>(null)
  const locked = useRef(false)
  const busy = stage === 'validating' || stage === 'processing'
  useEffect(() => {
    const controller = new AbortController()
    void getCsvScenarios(controller.signal).then((data) => setScenarios(data.scenarios)).catch(() => {})
    return () => { controller.abort(); request.current?.abort() }
  }, [])

  async function validate(fileName: string, getText: () => Promise<string>, selectedSource: CsvUpload['source_kind']) {
    if (locked.current) return
    locked.current = true
    request.current?.abort()
    const controller = new AbortController(); request.current = controller
    setError(null); setResult(null); setPreview(null); setPayload(null); setStage('validating')
    try {
      const next = { file_name: fileName, csv_text: await getText(), source_kind: selectedSource }
      if (controller.signal.aborted) return
      const checked = await previewCsv(tractorId, next, controller.signal)
      if (controller.signal.aborted) return
      setPayload(next); setPreview(checked); setStage('ready')
    } catch (reason) { if (!controller.signal.aborted) { setError(intakeError(reason)); setStage('idle') } }
    finally { locked.current = false }
  }

  function chooseFile(file: File | undefined) {
    if (!file) return
    if (file.size > 12 * 1024 * 1024) { setError('Use um CSV de até 12 MB.'); setPreview(null); setPayload(null); setResult(null); setStage('idle'); return }
    void validate(file.name, () => file.text(), source)
  }

  async function example(scenario: CsvScenario) {
    setSource('simulated_csv')
    await validate(scenario.file_name, async () => {
      const response = await fetch(`/api${scenario.download_url}`, { credentials: 'same-origin', signal: request.current?.signal })
      if (!response.ok) throw new Error('CSV indisponível')
      return response.text()
    }, 'simulated_csv')
  }

  async function process() {
    if (!payload || locked.current) return
    locked.current = true; setStage('processing'); setError(null)
    const controller = new AbortController(); request.current = controller
    try {
      const imported = await importCsv(tractorId, payload, controller.signal)
      if (controller.signal.aborted) return
      setResult(imported); setStage('done'); onImported()
    } catch (reason) { if (!controller.signal.aborted) { setError(intakeError(reason)); setStage('ready') } }
    finally { locked.current = false }
  }

  return <section className="ui-card" aria-labelledby="import-heading"><div className="ui-card-content stack">
    <div><h2 id="import-heading">Adicionar dados de operação</h2><p className="muted">Selecione o arquivo, confira o período e processe a análise.</p></div>
    <ol className="import-steps" aria-label="Etapas da importação"><li data-active={stage === 'idle' || stage === 'validating'}>1. Arquivo</li><li data-active={stage === 'ready'}>2. Conferir</li><li data-active={stage === 'processing' || stage === 'done'}>3. Analisar</li></ol>
    <div className="grid two">
      <label className="field">Origem<select disabled={busy} value={source} onChange={(event) => { setSource(event.target.value as CsvUpload['source_kind']); setPayload(null); setPreview(null); setResult(null); setStage('idle') }}><option value="simulated_csv">Dados simulados</option><option value="operational_csv">Dados reais da unidade de referência</option></select></label>
      <label className="field">Arquivo CSV<input type="file" accept=".csv,text/csv" disabled={busy} onChange={(event) => { chooseFile(event.target.files?.[0]); event.target.value = '' }} /></label>
    </div>
    {scenarios.length ? <details className="example-files"><summary>Experimentar com CSVs simulados</summary><div className="example-grid">{scenarios.map((scenario) => <div key={scenario.id}><strong>{scenario.label}</strong><span className="muted">{scenario.description}</span><div className="inline"><Button size="sm" variant="secondary" disabled={busy} onClick={() => void example(scenario)}>Usar {scenario.machine_name}{scenario.followup_for ? ' · novo período' : ''}</Button><a href={`/api${scenario.download_url}`} download={scenario.file_name}>Baixar CSV</a></div></div>)}</div></details> : null}
    {stage === 'validating' ? <p role="status">Validando datas, sinais e cobertura…</p> : null}
    {preview && payload ? <div className="import-preview stack"><div className="spread"><strong>{payload.file_name}</strong><span className="source-tag">{sourceLabel(preview.source_kind)}</span></div><dl className="import-facts"><div><dt>Período UTC</dt><dd>{formatDateTime(preview.started_at_utc)} → {formatDateTime(preview.ended_at_utc)}</dd></div><div><dt>Registros</dt><dd>{formatNumber(preview.sample_count, 0)}</dd></div><div><dt>Operações</dt><dd>{preview.mission_count}</dd></div><div><dt>Minutos disponíveis para análise</dt><dd>{preview.ready_window_count}</dd></div></dl><span className="muted">{preview.reference_label}</span>{(preview.skipped_window_count ?? 0) > 0 ? <span>{preview.skipped_window_count} trechos sem cobertura suficiente ficam fora da análise.</span> : null}</div> : null}
    {stage === 'ready' ? <Button onClick={() => void process()}>Processar dados</Button> : null}
    {stage === 'processing' ? <div role="status" className="stack"><progress className="processing-progress" aria-label="Executando análise" /><span>Executando o modelo e organizando os episódios…</span></div> : null}
    {result ? <div className="import-success stack" role="status"><strong>{result.duplicate ? 'Este arquivo já foi processado' : 'Análise concluída'}</strong><span>{formatNumber(result.sample_count, 0)} registros · {result.alert_count} {result.alert_count === 1 ? 'janela sinalizada' : 'janelas sinalizadas'}</span><div className="inline"><Link className="ui-button ui-button-primary ui-button-default" to={`/tratores/${tractorId}`}>Ver resultado</Link><Link to={`/tratores/${tractorId}/telemetria`}>Explorar gráficos</Link></div></div> : null}
    {error ? <p className="field-error" role="alert">{error}</p> : null}
    <details className="technical-details"><summary>Formato do arquivo</summary><p>CSV com data e hora UTC explícitas, identificação da operação e os sensores Fendt 314. Use os arquivos de exemplo como modelo. Envie períodos posteriores aos já analisados; importar novamente o mesmo arquivo preserva o resultado.</p><p>Novas unidades simuladas são comparadas à referência treinada Fendt 314. A aplicação de dados reais de outra unidade precisa de validação técnica.</p></details>
  </div></section>
}

function ImportsPage() {
  const { tractorId } = useParams()
  const principal = usePrincipal()
  const load = useCallback((signal: AbortSignal) => getImports(tractorId!, signal), [tractorId])
  const resource = usePollingResource(load, { successDelayMs: 15000 })
  if (!tractorId) return null
  const imports = resource.state.kind === 'success' || resource.state.kind === 'error' ? resource.state.data?.imports : null
  return <MachineDataLayout tractorId={tractorId} refreshKey={imports?.length ?? 0}><div className="stack">
    {principal.role === 'INSURER' ? <CsvImporter tractorId={tractorId} onImported={resource.refresh} /> : null}
    <section className="ui-card"><div className="ui-card-content stack"><h2>Importações</h2>
      {resource.state.kind === 'error' ? <ResourceError error={resource.state.error} onRetry={resource.refresh} /> : null}
      {resource.state.kind === 'loading' ? <p role="status">Carregando importações…</p> : null}
      {imports?.length === 0 ? <p className="muted">Nenhum arquivo importado para esta máquina.</p> : null}
      {imports?.map((item) => <div className="import-history-row" key={item.id}><div><strong>{item.file_name}</strong><span className="muted">{formatDateTime(item.started_at_utc)} → {formatDateTime(item.ended_at_utc)} UTC</span></div><span className="source-tag">{sourceLabel(item.source_kind)}</span><Link to={`/tratores/${tractorId}/telemetria?import=${item.id}`}>Ver gráficos</Link></div>)}
    </div></section>
  </div></MachineDataLayout>
}
export { ImportsPage, CsvImporter }
