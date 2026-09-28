import { Badge } from '../../components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card'
import type { TractorOverview } from '../../lib/api-contracts'
import { explainExposureBand, formatConfidence, formatCoverage, formatExposureBand, formatNumber, formatScore, formatTrend } from '../../lib/presentation'

const metrics = [
  { key: 'physical_exposure_seconds_per_hour', label: 'Condições físicas', unit: 's/h' },
  { key: 'alert_exposure_seconds_per_hour', label: 'Exposição em alertas', unit: 's/h' },
  { key: 'episodes_per_hour', label: 'Episódios', unit: '/h' },
] as const

function ExposureSummary({ overview }: { overview: TractorOverview }) {
  const score = overview.scores['30_days']
  const previous = overview.previous_30_days
  return <Card className="decision-card wf-summary-card" role="region" aria-labelledby="exposure-summary-heading">
    <CardHeader><div className="spread"><CardTitle id="exposure-summary-heading">Últimos 30 dias</CardTitle><Badge variant="outline">Referência Fendt 314</Badge></div></CardHeader>
    <CardContent className="stack">
      <div className="wf-summary-head"><div><span className={`exposure-band exposure-band-${score.exposure_band ?? 'none'}`}>{formatExposureBand(score.exposure_band)}</span></div><strong className="wf-index">{formatScore(score.relative_exposure_score)}<small>índice combinado</small></strong></div>
      <div className="wf-metrics">{metrics.map(({ key, label, unit }) => {
        const current = score[key]
        const reference = overview.reference_30_day_medians?.[key]
        const maximum = Math.max(current ?? 0, reference ?? 0, 1)
        return <div className="wf-metric" key={key}><div className="spread"><strong>{label}</strong><span>{formatNumber(current, 2)} {current === null ? '' : unit}</span></div><div className="wf-metric-track" aria-hidden="true"><span style={{ width: `${(current ?? 0) / maximum * 100}%` }} /></div>{reference === undefined ? <small className="muted">Referência indisponível</small> : <><div className="wf-metric-track wf-metric-reference" aria-hidden="true"><span style={{ width: `${reference / maximum * 100}%` }} /></div><small className="muted">Referência: {formatNumber(reference, 2)} {unit}</small></>}</div>
      })}</div>
      <p className="wf-caption"><span className="wf-key" /> Atual <span className="wf-key wf-key-reference" /> Mediana da referência</p>
      <div className="wf-coverage"><div><strong>{formatCoverage(score.active_days, 30)}</strong><span>{formatNumber(score.observed_hours, 1)} h · <span className={score.status === 'OK' && score.confidence === 'LOW' ? 'wf-low-coverage' : undefined}>cobertura {formatConfidence(score.confidence).toLowerCase()}</span></span></div><div><strong>{formatTrend(overview.trend_30_day)}</strong><span>{previous == null ? 'Cobertura anterior indisponível' : `Anterior: ${formatCoverage(previous.active_days, 30)} · ${formatNumber(previous.observed_hours, 1)} h`}</span></div><div><strong>{overview.episodes_last_30_days.length} episódios</strong><span>no período observado</span></div></div>
      <div className="wf-summary-footer"><small className="muted">Vistoria preventiva · não é diagnóstico de dano.</small><details className="wf-summary-help"><summary>Como ler o índice</summary><p>{explainExposureBand(score.exposure_band)} O índice combina as três medidas.</p><p>A referência vem do treinamento da Fendt 314. Cobertura baixa limita a comparação. Não indica falha ou mau uso.</p></details></div>
    </CardContent>
  </Card>
}
export { ExposureSummary }
