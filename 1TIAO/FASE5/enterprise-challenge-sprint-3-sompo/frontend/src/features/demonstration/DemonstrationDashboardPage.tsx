import { useCallback } from 'react'
import { Link } from 'react-router-dom'
import { Alert, AlertDescription, AlertTitle } from '../../components/ui/alert'
import { Badge } from '../../components/ui/badge'
import { Button } from '../../components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card'
import { usePollingResource } from '../../hooks/usePollingResource'
import { getDemoReplayProgress, getTractorOverview } from '../../lib/api-client'
import type { RecentInference, ReplayProgress } from '../../lib/api-contracts'
import { formatNumber } from '../../lib/presentation'
import { LoadingView, ResourceError } from '../common/ResourceViews'
import { ScoreSummary } from '../presentation/ScoreSummary'

const integerFormatter = new Intl.NumberFormat('pt-BR')

function statusLabel(status: ReplayProgress['status']): string {
  if (status === 'waiting') return 'Preparando replay'
  if (status === 'running') return 'Inferência em andamento'
  if (status === 'complete') return 'Execução concluída'
  return 'Execução interrompida'
}

function statusBadgeLabel(status: ReplayProgress['status']): string {
  if (status === 'waiting') return 'aguardando'
  if (status === 'running') return 'ao vivo'
  if (status === 'complete') return 'concluída'
  return 'interrompida'
}

function statusDescription(progress: ReplayProgress): string {
  if (progress.status === 'waiting') return 'A telemetria já foi validada e o motor de inferência será iniciado em seguida.'
  if (progress.status === 'running' && progress.samples_replayed === progress.total_samples) return 'Todas as amostras foram reproduzidas. A verificação estrutural está sendo finalizada.'
  if (progress.status === 'running') return 'Cada resultado abaixo aparece somente depois que a janela foi inferida e persistida no PostgreSQL.'
  if (progress.status === 'complete') return 'A fonte observada foi reproduzida por completo nesta execução.'
  return 'A execução parou sem inventar resultados. Os números parciais permanecem visíveis para diagnóstico.'
}

function progressPercent(progress: ReplayProgress): number {
  return Math.min(100, (progress.samples_replayed / progress.total_samples) * 100)
}

function PipelineStage({ label, detail, state }: { label: string; detail: string; state: 'pending' | 'active' | 'complete' }) {
  return (
    <li className={`demo-stage demo-stage-${state}`}>
      <span aria-hidden="true" className="demo-stage-dot" />
      <div><strong>{label}</strong><span>{detail}</span></div>
    </li>
  )
}

function ReplayPipeline({ progress }: { progress: ReplayProgress }) {
  const hasStarted = progress.samples_replayed > 0
  const hasInference = progress.created_windows > 0
  const isComplete = progress.status === 'complete'

  return (
    <ol className="demo-pipeline" aria-label="Fluxo da execução">
      <PipelineStage label="Telemetria observada" detail={`${integerFormatter.format(progress.total_samples)} amostras verificadas`} state="complete" />
      <PipelineStage label="Janelas causais" detail={`${integerFormatter.format(progress.ready_windows)} janelas construídas`} state={isComplete ? 'complete' : hasStarted ? 'active' : 'pending'} />
      <PipelineStage label="Modelo híbrido" detail={`${integerFormatter.format(progress.created_windows)} inferências persistidas`} state={isComplete ? 'complete' : hasInference ? 'active' : 'pending'} />
      <PipelineStage label="Evidência operacional" detail={`${integerFormatter.format(progress.alert_windows)} janelas contextualizadas`} state={isComplete ? 'complete' : hasInference ? 'active' : 'pending'} />
    </ol>
  )
}

function ReplayCounters({ progress }: { progress: ReplayProgress }) {
  return (
    <div className="demo-counter-grid" aria-live="polite">
      <dl className="demo-counter"><dt>Amostras reproduzidas</dt><dd>{integerFormatter.format(progress.samples_replayed)}</dd></dl>
      <dl className="demo-counter"><dt>Janelas inferidas</dt><dd>{integerFormatter.format(progress.created_windows)}</dd></dl>
      <dl className="demo-counter demo-counter-alert"><dt>Alertas contextuais</dt><dd>{integerFormatter.format(progress.alert_windows)}</dd></dl>
      <dl className="demo-counter"><dt>Janelas sem cobertura</dt><dd>{integerFormatter.format(progress.no_data_windows)}</dd></dl>
    </div>
  )
}

function InferenceRow({ inference }: { inference: RecentInference }) {
  return (
    <li className="inference-row">
      <span className={`inference-decision ${inference.hybrid_alert ? 'inference-decision-alert' : ''}`} aria-hidden="true" />
      <div><strong>Missão {inference.mission_index} · janela {inference.window_index}</strong><span>{inference.hybrid_alert ? 'Exposição contextual sinalizada' : 'Sem alerta híbrido'}</span></div>
      <Badge variant={inference.hybrid_alert ? 'default' : 'outline'}>{inference.hybrid_alert ? 'alerta' : 'observada'}</Badge>
    </li>
  )
}

function RecentInferenceFeed({ inferences }: { inferences: RecentInference[] }) {
  return (
    <Card className="inference-feed-card">
      <CardHeader><div className="spread"><CardTitle>Decisões recentes do modelo</CardTitle><Badge variant="outline">v2.0.1</Badge></div></CardHeader>
      <CardContent>
        {inferences.length === 0
          ? <div className="inference-feed-empty"><span aria-hidden="true" className="live-orbit" /><p>Aguardando a primeira janela causal completa.</p></div>
          : <ol className="inference-feed">{[...inferences].reverse().map((inference) => <InferenceRow key={`${inference.mission_index}-${inference.window_index}`} inference={inference} />)}</ol>}
      </CardContent>
    </Card>
  )
}

function LiveOverview({ tractorId, replayStatus }: { tractorId: string; replayStatus: ReplayProgress['status'] }) {
  const loader = useCallback((signal: AbortSignal) => getTractorOverview(tractorId, signal), [tractorId])
  const resource = usePollingResource(loader, { successDelayMs: 2000, retryDelayMs: 2000 })

  if (resource.state.kind === 'loading' || resource.state.kind === 'empty') {
    return <Card><CardContent className="live-overview-waiting"><span aria-hidden="true" className="live-orbit" /><div><strong>Agregados longitudinais em formação</strong><p className="muted">Os escores de 7, 15 e 30 dias surgem da API conforme as janelas observadas são persistidas.</p></div></CardContent></Card>
  }
  if (resource.state.kind === 'error' && resource.state.data === null) return <ResourceError error={resource.state.error} onRetry={resource.refresh} />

  const overview = resource.state.kind === 'success' ? resource.state.data : resource.state.data
  if (overview === null) return null
  const isStale = resource.state.kind === 'error'
  const status = isStale
    ? 'Último resultado válido; atualização falhou'
    : resource.isRefreshing || replayStatus === 'running'
      ? 'Atualizando pela API…'
      : 'Fechamento concluído'

  return (
    <section className="stack" aria-label="Resultados longitudinais da execução">
      {isStale ? <Alert variant="destructive"><AlertTitle>Agregado possivelmente desatualizado</AlertTitle><AlertDescription>A última resposta válida permanece visível, mas a atualização longitudinal falhou.</AlertDescription></Alert> : null}
      <div className="spread demo-results-heading"><div><p className="eyebrow">Resultados produzidos agora</p><h2>Exposição relativa por horizonte</h2></div><span className="muted" aria-live="polite">{status}</span></div>
      <ScoreSummary scores={overview.scores} />
      <Card><CardContent className="spread demo-results-footer"><div><strong>{overview.episodes_last_30_days.length} episódios no horizonte atual</strong><p className="muted">{formatNumber(overview.observed_hours)} horas observadas no fechamento mais recente.</p></div><div className="inline"><Link className="ui-button ui-button-secondary ui-button-default" to={`/tratores/${overview.tractor.id}`}>Abrir evidências do trator</Link><Link className="ui-button ui-button-secondary ui-button-default" to="/prioridades">Ver prioridades</Link></div></CardContent></Card>
    </section>
  )
}

function LiveDemo({ progress }: { progress: ReplayProgress }) {
  const percent = progressPercent(progress)

  return (
    <div className="stack demo-live-content">
      {progress.status === 'failed' ? <Alert variant="destructive"><AlertTitle>Replay interrompido</AlertTitle><AlertDescription>Nenhum resultado foi completado artificialmente. Execute <code>make demo-real</code> novamente e consulte o log local.</AlertDescription></Alert> : null}

      <section className="grid two demo-runtime-grid" aria-label="Estado da inferência">
        <Card className="demo-runtime-card">
          <CardHeader><div className="spread"><CardTitle>{statusLabel(progress.status)}</CardTitle><Badge variant={progress.status === 'complete' ? 'secondary' : progress.status === 'failed' ? 'default' : 'warning'}><span aria-hidden="true" className={progress.status === 'running' ? 'live-dot' : ''} />{statusBadgeLabel(progress.status)}</Badge></div></CardHeader>
          <CardContent className="stack">
            <p className="muted demo-runtime-description">{statusDescription(progress)}</p>
            <div className="demo-progress-meta"><strong>{formatNumber(percent, 1)}%</strong><span>{integerFormatter.format(progress.samples_replayed)} de {integerFormatter.format(progress.total_samples)} amostras</span></div>
            <div className="demo-progress-track" role="progressbar" aria-label="Progresso da telemetria reproduzida" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(percent)}><span style={{ width: `${percent}%` }} /></div>
            <ReplayPipeline progress={progress} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Fonte desta execução</CardTitle></CardHeader>
          <CardContent className="stack">
            <Badge variant="outline">telemetria real · não sintética</Badge>
            <dl className="detail-list">
              <dt>Trator</dt><dd>Fendt 314</dd>
              <dt>Partição</dt><dd>Validação observada</dd>
              <dt>Fonte pública</dt><dd><a href={`https://doi.org/${progress.source_doi}`} target="_blank" rel="noreferrer">DOI {progress.source_doi}</a></dd>
              <dt>Licença</dt><dd>{progress.source_license}</dd>
              <dt>Integridade</dt><dd><code>{progress.semantic_sha256.slice(0, 12)}…{progress.semantic_sha256.slice(-8)}</code></dd>
            </dl>
            <p className="decision-limit">O dataset não contém rótulos de dano, falha, sinistro, culpa ou mau uso.</p>
          </CardContent>
        </Card>
      </section>

      <ReplayCounters progress={progress} />
      <RecentInferenceFeed inferences={progress.recent_inferences} />
      <LiveOverview tractorId={progress.tractor_id} replayStatus={progress.status} />
    </div>
  )
}

function DemoNotRunning() {
  return (
    <Card className="empty">
      <CardHeader><CardTitle>Demonstração local não iniciada</CardTitle></CardHeader>
      <CardContent className="stack"><p>Esta tela não possui números preparados. Inicie uma nova inferência sobre as amostras observadas:</p><pre className="code-block">make demo-real</pre><p className="muted">O comando recria somente o banco isolado da demonstração.</p></CardContent>
    </Card>
  )
}

function AcademicContext() {
  return (
    <Alert>
      <AlertTitle>Avaliação acadêmica de uma unidade observada</AlertTitle>
      <AlertDescription>O modelo congelado foi calibrado e validado temporalmente em uma Fendt 314. Os dados abaixo descrevem apenas a execução local atual; não comprovam generalização para outros tratores, dano, falha ou sinistro.</AlertDescription>
    </Alert>
  )
}

function ModelSummary() {
  return (
    <section className="grid two" aria-label="Resumo acadêmico do modelo">
      <Card>
        <CardHeader><CardTitle>Como a IA produz um alerta</CardTitle></CardHeader>
        <CardContent className="stack">
          <ol>
            <li>Agrega a telemetria observada em uma janela causal de 60 segundos.</li>
            <li>O K-Means identifica um entre três regimes operacionais.</li>
            <li>Uma Isolation Forest mede a raridade dentro daquele regime.</li>
            <li>O alerta exige raridade acima do quantil 0,97 e uma regra física presente por pelo menos 5 segundos.</li>
            <li>O histórico vira exposição relativa em 7, 15 e 30 dias.</li>
          </ol>
          <p className="decision-limit">Alerta contextual não é diagnóstico de falha.</p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Evidência experimental congelada</CardTitle></CardHeader>
        <CardContent className="stack">
          <dl className="detail-list">
            <dt>Treino</dt><dd>7.317 janelas</dd>
            <dt>Validação</dt><dd>74/2.522 alertas (2,93%)</dd>
            <dt>Teste temporal</dt><dd>95/3.617 alertas (2,63%)</dd>
            <dt>Artefato</dt><dd><code>fendt314-hybrid-v2.0.1</code></dd>
          </dl>
          <p className="muted">O GO mede aderência aos critérios operacionais e estabilidade temporal no único Fendt 314 estudado; não mede acurácia de dano ou sinistro.</p>
        </CardContent>
      </Card>
    </section>
  )
}

function DemonstrationDashboardPage() {
  const loader = useCallback((signal: AbortSignal) => getDemoReplayProgress(signal), [])
  const resource = usePollingResource(loader, { successDelayMs: 1000, retryDelayMs: 2000 })

  function content() {
    if (resource.state.kind === 'loading') return <LoadingView />
    if (resource.state.kind === 'empty') return <DemoNotRunning />
    if (resource.state.kind === 'error') return <ResourceError error={resource.state.error} onRetry={resource.refresh}>{resource.state.data === null ? null : <><Alert variant="destructive"><AlertTitle>Dados possivelmente desatualizados</AlertTitle><AlertDescription>A última execução continua visível, mas a atualização falhou. Confirme o estado antes de tomar qualquer ação.</AlertDescription></Alert><LiveDemo progress={resource.state.data} /></>}</ResourceError>
    return <LiveDemo progress={resource.state.data} />
  }

  return (
    <main className="page demonstration-page">
      <div className="page-heading"><div><p className="eyebrow">Demonstração · inferência observável</p><h1>Veja a telemetria virar evidência operacional</h1><p className="muted">Uma nova execução sobre amostras observadas da Fendt 314, do PostgreSQL ao modelo e ao dashboard.</p></div><div className="stack"><Button type="button" variant="secondary" onClick={resource.refresh}>Atualizar agora</Button><span aria-live="polite" className="muted">{resource.isRefreshing ? 'Sincronizando…' : ''}</span></div></div>
      <AcademicContext />
      <ModelSummary />
      {content()}
    </main>
  )
}

export { DemonstrationDashboardPage }
