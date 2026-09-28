import { useCallback } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Alert, AlertDescription, AlertTitle } from '../../components/ui/alert'
import { Badge } from '../../components/ui/badge'
import { Button } from '../../components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card'
import { usePollingResource } from '../../hooks/usePollingResource'
import { getTractorOverview } from '../../lib/api-client'
import { formatCondition, formatConfidence, formatDateTime, formatNumber, formatScore, formatScoreStatus, formatTrend, tractorLabel } from '../../lib/presentation'
import { LoadingView, ResourceError } from '../common/ResourceViews'
import { EpisodeList } from '../presentation/EpisodeList'
import { ProvenanceList } from '../presentation/ProvenanceList'
import { ScoreSummary } from '../presentation/ScoreSummary'
import { InspectionCasesPanel } from './InspectionCasesPanel'
import { TelemetryPeriodsPanel } from './TelemetryPeriodsPanel'

function TractorOverviewPage() {
  const { tractorId } = useParams()
  const loader = useCallback((signal: AbortSignal) => tractorId === undefined ? Promise.reject(new Error('Identificador de trator ausente.')) : getTractorOverview(tractorId, signal), [tractorId])
  const resource = usePollingResource(loader)

  function content() {
    if (resource.state.kind === 'loading') return <LoadingView />
    if (resource.state.kind === 'empty') return <Card className="empty"><CardHeader><CardTitle>Trator não encontrado ou sem histórico</CardTitle></CardHeader><CardContent><p>A consulta será refeita automaticamente. Cadastre uma nova frota caso este identificador não exista.</p><Link to="/frotas/nova">Cadastrar frota</Link></CardContent></Card>
    if (resource.state.kind === 'error') return <ResourceError error={resource.state.error} onRetry={resource.refresh}>{resource.state.data === null ? null : <TractorDetails overview={resource.state.data} />}</ResourceError>
    return <TractorDetails overview={resource.state.data} />
  }

  const overview = resource.state.kind === 'success' ? resource.state.data : resource.state.kind === 'error' ? resource.state.data : null
  return <main className="page"><div className="page-heading"><div><p className="eyebrow">Detalhe explicável</p><h1>{overview === null ? 'Trator' : tractorLabel(overview.tractor.external_id, overview.tractor.display_name)}</h1><p className="muted">Horizontes, episódios, períodos observados e revisão preventiva persistida.</p></div><div className="stack"><Button type="button" variant="secondary" onClick={resource.refresh}>Atualizar agora</Button><span aria-live="polite" className="muted">{resource.isRefreshing ? 'Atualizando…' : ''}</span></div></div>{content()}<div className="stack"><TelemetryPeriodsPanel tractorId={tractorId} /><InspectionCasesPanel tractorId={tractorId} /></div></main>
}

function InspectionDecisionSummary({ overview }: { overview: import('../../lib/api-contracts').TractorOverview }) {
  const thirtyDayScore = overview.scores['30_days']

  if (thirtyDayScore.status === 'NO_DATA') {
    return <Card><CardHeader><CardTitle>Sem base observada para triagem</CardTitle></CardHeader><CardContent className="stack"><p>Continue a coleta e verifique a disponibilidade e a proveniência antes de orientar uma revisão.</p><p className="decision-limit">Nenhuma falha foi diagnosticada.</p></CardContent></Card>
  }

  return <Card className="decision-card"><CardHeader><CardTitle>Próximo passo de revisão</CardTitle></CardHeader><CardContent className="stack"><p className="decision-statement">Revise as evidências e considere inspeção preventiva conforme o contexto.</p><dl className="detail-list"><dt>Exposição relativa em 30 dias</dt><dd>{formatScore(thirtyDayScore.relative_exposure_score)}</dd><dt>Tendência</dt><dd>{formatTrend(overview.trend_30_day)}</dd><dt>Confiança da evidência</dt><dd>{formatConfidence(overview.confidence)}</dd><dt>Horas observadas</dt><dd>{formatNumber(overview.observed_hours)} h</dd><dt>Episódios</dt><dd>{thirtyDayScore.episode_count}</dd><dt>Condições</dt><dd>{thirtyDayScore.represented_conditions.length === 0 ? 'Não informadas' : thirtyDayScore.represented_conditions.map(formatCondition).join(', ')}</dd></dl><p className="decision-limit">Nenhuma falha foi diagnosticada.</p></CardContent></Card>
}

function TractorDetails({ overview }: { overview: import('../../lib/api-contracts').TractorOverview }) {
  return <div className="stack"><Alert><AlertTitle>Fechamento histórico</AlertTitle><AlertDescription><time dateTime={overview.as_of_utc}>{formatDateTime(overview.as_of_utc)} UTC</time> · evidência operacional.</AlertDescription></Alert><InspectionDecisionSummary overview={overview} /><Card><CardHeader><CardTitle>Resumo atual</CardTitle></CardHeader><CardContent><div className="grid three"><dl className="detail-list"><dt>Frota</dt><dd><Link to={`/frotas/${overview.fleet.id}`}>{overview.fleet.name}</Link></dd><dt>Modelo</dt><dd>{overview.tractor.model_name}</dd><dt>Confiança</dt><dd><Badge variant={overview.confidence === 'HIGH' ? 'secondary' : overview.confidence === 'MEDIUM' ? 'warning' : 'outline'}>{formatConfidence(overview.confidence)}</Badge></dd></dl><dl className="detail-list"><dt>30 dias</dt><dd>{formatScore(overview.scores['30_days'].relative_exposure_score)}</dd><dt>Score anterior</dt><dd>{formatScore(overview.previous_30_day_score)}</dd><dt>Tendência</dt><dd>{formatTrend(overview.trend_30_day)}</dd></dl><dl className="detail-list"><dt>Horas observadas</dt><dd>{formatNumber(overview.observed_hours)} h</dd><dt>Episódios</dt><dd>{overview.episodes_last_30_days.length}</dd><dt>Status</dt><dd>{formatScoreStatus(overview.scores['30_days'].status)}</dd></dl></div></CardContent></Card><ScoreSummary scores={overview.scores} /><EpisodeList episodes={overview.episodes_last_30_days} /><ProvenanceList provenance={overview.provenance} /></div>
}

export { TractorOverviewPage }
