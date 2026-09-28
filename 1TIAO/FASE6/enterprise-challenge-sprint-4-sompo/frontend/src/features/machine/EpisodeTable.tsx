import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '../../components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card'
import type { InspectionEpisode, Regimes } from '../../lib/api-contracts'
import { formatCondition, formatDateTime, formatDuration, formatRegime } from '../../lib/presentation'

function EpisodeTable({ tractorId, episodes, regimes, asOf, condition = '', episodeIds, onClearAgenda, newEpisodeIds }: { tractorId: string; episodes: InspectionEpisode[]; regimes: Regimes; asOf?: string; condition?: string; episodeIds?: string[]; onClearAgenda?: () => void; newEpisodeIds?: string[] }) {
  const [expanded, setExpanded] = useState(false)
  const ordered = [...episodes].filter((episode) => (!condition || episode.conditions.includes(condition)) && (episodeIds === undefined || episodeIds.includes(episode.id))).sort((left, right) => right.started_at_utc.localeCompare(left.started_at_utc))
  const visible = expanded ? ordered : ordered.slice(0, 6)
  return <Card role="region" aria-labelledby="episodes-heading" id="machine-episodes"><CardHeader><div className="spread"><CardTitle id="episodes-heading">Episódios sinalizados nos últimos 30 dias</CardTitle><span>{ordered.length} episódios</span></div></CardHeader><CardContent className="stack">
    {episodeIds === undefined ? null : <div className="spread"><span className="muted">Episódios relacionados ao componente selecionado</span><button type="button" className="wf-text-button" onClick={onClearAgenda}>Limpar componente</button></div>}
    {ordered.length === 0 ? <p className="muted">{condition || episodeIds !== undefined ? 'Nenhum episódio corresponde aos filtros.' : 'Nenhum episódio começou nos últimos 30 dias.'}</p> : <div className="wf-episode-list">{visible.map((episode) => <Link className="wf-episode-row" key={episode.id} to={`/tratores/${tractorId}/episodios/${episode.id}${asOf === undefined ? '' : `?as_of_utc=${encodeURIComponent(asOf)}`}`}>
      <div><time dateTime={episode.started_at_utc}>{formatDateTime(episode.started_at_utc)} UTC</time><strong>{episode.conditions.map(formatCondition).join(', ')}</strong>{newEpisodeIds === undefined ? null : <small className={newEpisodeIds.includes(episode.id) ? 'wf-new-episode' : 'muted'}>{newEpisodeIds.includes(episode.id) ? 'Novo · ainda não revisado' : 'Já incluído em revisão anterior'}</small>}<small>{episode.operational_regimes.map((regime) => formatRegime(regime, regimes)).join(', ')}</small></div><div><strong>{formatDuration(episode.physical_exposure_seconds)}</strong><small>em condição física</small></div><span aria-hidden="true">→</span>
    </Link>)}</div>}
    {ordered.length > 6 ? <div><Button type="button" variant="secondary" onClick={() => setExpanded(!expanded)}>{expanded ? 'Mostrar recentes' : `Ver todos (${ordered.length})`}</Button></div> : null}
  </CardContent></Card>
}
export { EpisodeTable }
