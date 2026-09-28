import { useCallback } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card'
import { usePollingResource } from '../../hooks/usePollingResource'
import { getEpisodeDetail, getInspectionCaseEpisode } from '../../lib/api-client'
import type { EpisodeDetail } from '../../lib/api-contracts'
import { formatCondition, formatConditionRule, formatContextualReason, formatDateTime, formatDuration, formatNumber, formatRegime, tractorLabel } from '../../lib/presentation'
import { LoadingView, ResourceError } from '../common/ResourceViews'
import { InspectionAgendaCard } from '../presentation/InspectionAgendaCard'
import { EpisodeSignals } from './EpisodeSignals'
import '../inspection/workflow.css'

function EpisodeEvidence({ detail }: { detail: EpisodeDetail }) {
  const { episode, regimes } = detail
  const firedConditions = Object.entries(detail.condition_seconds).filter(([, seconds]) => seconds > 0)

  return (
    <div className="stack">
      <Card className="decision-card" role="region" aria-labelledby="why-heading">
        <CardHeader><CardTitle id="why-heading">Por que este trecho foi sinalizado</CardTitle></CardHeader>
        <CardContent className="grid two">
          <section className="stack">
            <h3>1. Condição física por 5 segundos ou mais</h3>
            <ul className="rule-list">{firedConditions.map(([condition, seconds]) => (
              <li key={condition}><strong>{formatCondition(condition)}: {formatDuration(seconds)}</strong><span className="muted">{formatConditionRule(condition)}</span></li>
            ))}</ul>
          </section>
          <section className="stack">
            <h3>2. Fora do padrão de referência</h3>
            <p className="muted">O comportamento destoou da referência Fendt 314 em operações semelhantes.</p>
            <ul className="rule-list">{episode.operational_regimes.map((regime) => <li key={regime}>{formatRegime(regime, regimes)}</li>)}</ul>
            <details className="technical-details"><summary>Ver critérios da sinalização</summary>
              <ul className="rule-list">{detail.windows.map((window) => (
                <li key={window.window_index}><span className="muted">{formatDateTime(window.observed_at_utc)} UTC: índice de raridade {formatNumber(window.decision.contextual_rarity_score, 3)}, acima do limite {formatNumber(window.decision.contextual_rarity_threshold, 3)} para esta operação.</span></li>
              ))}</ul>
            </details>
          </section>
        </CardContent>
      </Card>

      <Card role="region" aria-labelledby="signals-heading">
        <CardHeader><CardTitle id="signals-heading">Sinais segundo a segundo</CardTitle></CardHeader>
        <CardContent className="stack">
          <EpisodeSignals key={detail.episode.id} detail={detail} />
        </CardContent>
      </Card>

      <details className="wf-details"><summary>Pistas e critérios da sinalização</summary><Card role="region" aria-labelledby="context-heading">
        <CardHeader><CardTitle id="context-heading">Pistas para a vistoria</CardTitle></CardHeader>
        <CardContent className="stack">
          <ul className="rule-list">{episode.contextual_reasons.map((reason) => <li key={String(reason.feature)}>{formatContextualReason(reason)}</li>)}</ul>
          <p className="muted">Medidas que mais se afastaram do comportamento habitual. Essas diferenças ajudam a investigar o trecho, mas não identificam sua causa.</p>
        </CardContent>
      </Card>

      </details>
      <InspectionAgendaCard tractorId={detail.tractor.id} asOf={detail.as_of_utc} agenda={detail.inspection_agenda} title="O que olhar por causa deste episódio" emptyText="Nenhum item da pauta está ligado às condições deste episódio." />
    </div>
  )
}

function EpisodePage() {
  const { tractorId, episodeId } = useParams()
  const [search] = useSearchParams()
  const asOf = search.get('as_of_utc') ?? undefined
  const caseId = search.get('caseId')
  const loader = useCallback(
    (signal: AbortSignal) => tractorId === undefined || episodeId === undefined
      ? Promise.reject(new Error('Identificador ausente.'))
      : caseId === null ? getEpisodeDetail(tractorId, episodeId, signal, asOf) : getInspectionCaseEpisode(caseId, episodeId, signal),
    [tractorId, episodeId, asOf, caseId],
  )
  const resource = usePollingResource(loader, { successDelayMs: 60_000 })
  const detail = resource.state.kind === 'success' ? resource.state.data : resource.state.kind === 'error' ? resource.state.data : null

  function content() {
    if (resource.state.kind === 'loading') return <LoadingView />
    if (resource.state.kind === 'empty') return <Card className="empty"><CardHeader><CardTitle>Episódio não encontrado</CardTitle></CardHeader><CardContent><p>Ele pode ter saído da janela de 60 dias do histórico consultado.</p></CardContent></Card>
    if (resource.state.kind === 'error') return <ResourceError error={resource.state.error} onRetry={resource.refresh}>{resource.state.data === null ? null : <EpisodeEvidence detail={resource.state.data} />}</ResourceError>
    return <EpisodeEvidence detail={resource.state.data} />
  }

  const seconds = detail === null ? null : (Date.parse(detail.episode.ended_at_utc) - Date.parse(detail.episode.started_at_utc)) / 1000
  return (
    <main className="page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Episódio</p>
          <h1>{detail === null ? 'Episódio' : `${formatDateTime(detail.episode.started_at_utc)} UTC`}</h1>
          {detail === null || seconds === null ? null : <p className="muted">{tractorLabel(detail.tractor.external_id, detail.tractor.display_name)} · {formatDuration(seconds)} de duração · {formatDuration(detail.episode.physical_exposure_seconds)} em condição de atenção</p>}
        </div>
        <Link className="ui-button ui-button-secondary ui-button-default" to={caseId !== null ? `/vistorias/${caseId}` : tractorId === undefined ? '/' : `/tratores/${tractorId}`}>{caseId === null ? 'Voltar para a máquina' : 'Voltar para a vistoria'}</Link>
      </div>
      {detail?.provenance?.some((item) => item.source_kind === 'simulated_csv') ? <p className="wf-synthetic">Dados simulados</p> : null}
      {caseId === null ? null : <p className="muted">Evidência preservada para esta vistoria.</p>}
      {content()}
    </main>
  )
}

export { EpisodePage }
