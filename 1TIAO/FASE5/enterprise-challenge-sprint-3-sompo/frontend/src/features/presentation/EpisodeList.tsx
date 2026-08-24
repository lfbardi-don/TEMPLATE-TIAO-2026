import type { InspectionEpisode } from '../../lib/api-contracts'
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '../../components/ui/accordion'
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card'
import { formatCondition, formatContextualReason, formatDateTime, formatNumber, formatRegime } from '../../lib/presentation'

type EpisodeListProps = { episodes: InspectionEpisode[] }

function EpisodeList({ episodes }: EpisodeListProps) {
  return (
    <section aria-labelledby="episodes-heading">
      <Card>
        <CardHeader><CardTitle id="episodes-heading">Episódios observados nos últimos 30 dias</CardTitle></CardHeader>
        <CardContent>
          {episodes.length === 0 ? <p className="muted">Nenhum episódio observado no fechamento atual.</p> : (
            <Accordion type="multiple">
              {episodes.map((episode) => (
                <AccordionItem key={episode.id} value={episode.id}>
                  <AccordionTrigger>
                    <span>Missão {episode.mission_index} · {formatDateTime(episode.started_at_utc)}</span>
                  </AccordionTrigger>
                  <AccordionContent>
                    <dl className="detail-list">
                      <dt>Início</dt><dd><time dateTime={episode.started_at_utc}>{formatDateTime(episode.started_at_utc)} UTC</time></dd>
                      <dt>Fim</dt><dd><time dateTime={episode.ended_at_utc}>{formatDateTime(episode.ended_at_utc)} UTC</time></dd>
                      <dt>Segundos alertados</dt><dd>{formatNumber(episode.alerted_seconds)} s</dd>
                      <dt>Exposição física</dt><dd>{formatNumber(episode.physical_exposure_seconds)} s</dd>
                      <dt>Condições</dt><dd>{episode.conditions.map(formatCondition).join(', ') || 'Não informado'}</dd>
                      <dt>Regimes</dt><dd>{episode.operational_regimes.map(formatRegime).join(', ') || 'Não informado'}</dd>
                      <dt>Maior raridade contextual</dt><dd>{formatNumber(episode.maximum_contextual_rarity_score, 3)}</dd>
                      <dt>Razões contextuais</dt><dd>{episode.contextual_reasons.map(formatContextualReason).join(' · ') || 'Não informado'}</dd>
                    </dl>
                  </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          )}
        </CardContent>
      </Card>
    </section>
  )
}

export { EpisodeList }
