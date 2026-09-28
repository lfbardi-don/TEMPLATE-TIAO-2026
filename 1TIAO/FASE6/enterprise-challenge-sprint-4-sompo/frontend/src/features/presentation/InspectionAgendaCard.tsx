import { Link } from 'react-router-dom'
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card'
import type { InspectionAgenda } from '../../lib/api-contracts'
import { formatCondition } from '../../lib/presentation'

function InspectionAgendaCard({ agenda, title = 'O que olhar na vistoria', emptyText, tractorId, asOf, onSelect }: { agenda: InspectionAgenda; title?: string; emptyText: string; tractorId?: string; asOf?: string; onSelect?: (itemId: string) => void }) {
  return <Card role="region" aria-labelledby="agenda-heading">
    <CardHeader><CardTitle id="agenda-heading">{title}</CardTitle></CardHeader>
    <CardContent>{agenda.items.length === 0 ? <p className="muted">{emptyText}</p> : <div className="wf-agenda-grid">{agenda.items.map((item) => <article className="wf-agenda-item" key={item.id}>
      <strong>{item.component}</strong><p>{item.check}</p><small className="muted">{item.conditions.map(formatCondition).join(', ')}</small>
      {onSelect !== undefined ? <button className="wf-text-button" type="button" onClick={() => onSelect(item.id)}>Ver {item.episode_ids.length} episódios relacionados →</button> : tractorId !== undefined ? <div className="wf-episode-links">{item.episode_ids.map((id, index) => <Link key={id} to={`/tratores/${tractorId}/episodios/${id}${asOf === undefined ? '' : `?as_of_utc=${encodeURIComponent(asOf)}`}`}>Episódio {index + 1} →</Link>)}</div> : null}
    </article>)}</div>}</CardContent>
  </Card>
}
export { InspectionAgendaCard }
