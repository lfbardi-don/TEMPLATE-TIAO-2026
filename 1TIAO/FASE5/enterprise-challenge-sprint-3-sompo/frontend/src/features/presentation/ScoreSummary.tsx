import type { Score } from '../../lib/api-contracts'
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '../../components/ui/accordion'
import { formatCondition, formatConfidence, formatMetricName, formatNumber, formatPercent, formatPercentile, formatRegime, formatScore, formatScoreStatus } from '../../lib/presentation'
import { Badge } from '../../components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card'

type ScoreSummaryProps = { scores: { '7_days': Score; '15_days': Score; '30_days': Score } }

const horizons: Array<{ key: '7_days' | '15_days' | '30_days'; label: string }> = [
  { key: '7_days', label: '7 dias' },
  { key: '15_days', label: '15 dias' },
  { key: '30_days', label: '30 dias' },
]

function ScoreSummary({ scores }: ScoreSummaryProps) {
  return (
    <section aria-labelledby="scores-heading">
      <div className="page-heading"><div><p className="eyebrow">Horizontes</p><h2 id="scores-heading">Exposição operacional relativa</h2></div></div>
      <div className="grid three">
        {horizons.map(({ key, label }) => {
          const score = scores[key]
          return (
            <Card key={key}>
              <CardHeader><CardTitle>{label}</CardTitle></CardHeader>
              <CardContent className="stack">
                <div className="spread"><span className="score-value">{formatScore(score.relative_exposure_score)}</span><Badge variant={score.status === 'OK' ? 'secondary' : 'warning'}>{formatScoreStatus(score.status)}</Badge></div>
                <dl className="detail-list">
                  <dt>Confiança</dt><dd>{formatConfidence(score.confidence)}</dd>
                  <dt>Horas observadas</dt><dd>{formatNumber(score.observed_hours)} h</dd>
                  <dt>Dias ativos</dt><dd>{score.active_days}</dd>
                  <dt>Cobertura</dt><dd>{formatPercent(score.calendar_coverage)}</dd>
                  <dt>Episódios</dt><dd>{score.episode_count}</dd>
                </dl>
                <Accordion type="single" collapsible>
                  <AccordionItem value="technical-details">
                    <AccordionTrigger>Ver detalhes técnicos</AccordionTrigger>
                    <AccordionContent>
                      <dl className="detail-list">
                        <dt>Exposição física/h</dt><dd>{formatNumber(score.physical_exposure_seconds_per_hour)} s</dd>
                        <dt>Exposição em alertas/h</dt><dd>{formatNumber(score.alert_exposure_seconds_per_hour)} s</dd>
                        <dt>Episódios/h</dt><dd>{formatNumber(score.episodes_per_hour, 3)}</dd>
                        <dt>Condições</dt><dd>{score.represented_conditions.map(formatCondition).join(', ') || 'Não informado'}</dd>
                        <dt>Regimes</dt><dd>{score.predominant_regimes.map(formatRegime).join(', ') || 'Não informado'}</dd>
                        <dt>Percentis</dt><dd>{Object.entries(score.component_percentiles).map(([name, value]) => `${formatMetricName(name)}: ${formatPercentile(value)}`).join(' · ') || 'Não informado'}</dd>
                      </dl>
                    </AccordionContent>
                  </AccordionItem>
                </Accordion>
              </CardContent>
            </Card>
          )
        })}
      </div>
    </section>
  )
}

export { ScoreSummary }
