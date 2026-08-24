import { Link } from 'react-router-dom'
import type { Priority } from '../../lib/api-contracts'
import { Badge } from '../../components/ui/badge'
import { Card, CardContent } from '../../components/ui/card'
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from '../../components/ui/table'
import { formatCondition, formatConfidence, formatNumber, formatPercent, formatScore, formatTrend, tractorLabel } from '../../lib/presentation'

type PriorityTableProps = { priorities: Priority[] }

function confidenceVariant(confidence: Priority['confidence']): 'secondary' | 'warning' | 'outline' {
  if (confidence === 'HIGH') return 'secondary'
  if (confidence === 'MEDIUM') return 'warning'
  return 'outline'
}

function confidenceLabel(confidence: Priority['confidence']): string {
  return confidence === 'LOW' ? 'Baixa confiança da evidência' : `Confiança ${formatConfidence(confidence).toLowerCase()}`
}

function ExposureSummary({ priority }: { priority: Priority }) {
  const score = priority.scores['30_days']
  if (score.status === 'NO_DATA') return <span>Sem base observada para triagem.</span>
  return <span>{formatScore(score.relative_exposure_score)} · {formatTrend(priority.trend_30_day)}</span>
}

function ObservedBase({ priority }: { priority: Priority }) {
  const score = priority.scores['30_days']
  return <span>{confidenceLabel(priority.confidence)} · {formatNumber(priority.observed_hours)} h · {score.active_days} dias · {formatPercent(score.calendar_coverage)}</span>
}

function EvidenceSummary({ priority }: { priority: Priority }) {
  const score = priority.scores['30_days']
  if (score.status === 'NO_DATA') return <span>Sem evidências pontuadas no fechamento atual.</span>
  return <span>{priority.episode_count} episódios · {priority.predominant_conditions.map(formatCondition).join(', ') || 'Condições não informadas'}</span>
}

function PriorityAction({ priority }: { priority: Priority }) {
  return <Link to={`/tratores/${priority.tractor.id}`}>Abrir evidências</Link>
}

function PriorityTable({ priorities }: PriorityTableProps) {
  return (
    <>
      <div className="table-wrap desktop-priority-table">
          <Table>
          <TableCaption>Ordem devolvida pela API. A fila orienta revisão preventiva e não diagnostica falha.</TableCaption>
          <TableHeader><TableRow><TableHead>Prioridade</TableHead><TableHead>Máquina e frota</TableHead><TableHead>Exposição relativa</TableHead><TableHead>Base observada</TableHead><TableHead>Evidências</TableHead><TableHead>Ação</TableHead></TableRow></TableHeader>
          <TableBody>{priorities.map((priority) => (
            <TableRow key={priority.tractor.id}>
              <TableCell>{priority.rank ?? 'Sem posição'}</TableCell>
              <TableCell><Link to={`/tratores/${priority.tractor.id}`}>{tractorLabel(priority.tractor.external_id, priority.tractor.display_name)}</Link><br /><Link to={`/frotas/${priority.fleet.id}`}>{priority.fleet.name}</Link></TableCell>
              <TableCell><ExposureSummary priority={priority} /></TableCell>
              <TableCell><ObservedBase priority={priority} /></TableCell>
              <TableCell><EvidenceSummary priority={priority} /></TableCell>
              <TableCell><PriorityAction priority={priority} /></TableCell>
            </TableRow>
          ))}</TableBody>
        </Table>
      </div>
      <div className="priority-card-list">
        {priorities.map((priority) => (
          <Card key={priority.tractor.id} className="priority-card"><CardContent className="stack">
            <div className="spread"><strong>Prioridade {priority.rank ?? 'indisponível'}</strong><Badge variant={confidenceVariant(priority.confidence)}>{confidenceLabel(priority.confidence)}</Badge></div>
            <dl className="detail-list">
              <dt>Máquina e frota</dt><dd><Link to={`/tratores/${priority.tractor.id}`}>{tractorLabel(priority.tractor.external_id, priority.tractor.display_name)}</Link><br /><Link to={`/frotas/${priority.fleet.id}`}>{priority.fleet.name}</Link></dd>
              <dt>Exposição relativa</dt><dd><ExposureSummary priority={priority} /></dd>
              <dt>Base observada</dt><dd><ObservedBase priority={priority} /></dd>
              <dt>Evidências</dt><dd><EvidenceSummary priority={priority} /></dd>
              <dt>Ação</dt><dd><PriorityAction priority={priority} /></dd>
            </dl>
          </CardContent></Card>
        ))}
      </div>
    </>
  )
}

export { PriorityTable }
