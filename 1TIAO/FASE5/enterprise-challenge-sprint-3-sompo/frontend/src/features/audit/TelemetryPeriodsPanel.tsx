import { useCallback } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card'
import { usePollingResource } from '../../hooks/usePollingResource'
import { getTelemetryPeriods } from '../../lib/api-client'
import { formatDateTime, formatNumber } from '../../lib/presentation'
import { LoadingView, ResourceError } from '../common/ResourceViews'

function TelemetryPeriodsPanel({ tractorId }: { tractorId: string | undefined }) {
  const loader = useCallback(
    (signal: AbortSignal) => tractorId === undefined
      ? Promise.reject(new Error('Identificador de trator ausente.'))
      : getTelemetryPeriods(tractorId, signal),
    [tractorId],
  )
  const resource = usePollingResource(loader)

  if (resource.state.kind === 'loading') return <LoadingView />
  if (resource.state.kind === 'empty') return <Card><CardHeader><CardTitle>Períodos de telemetria</CardTitle></CardHeader><CardContent><p>Nenhuma importação persistida está disponível para este trator.</p></CardContent></Card>
  if (resource.state.kind === 'error') return <ResourceError error={resource.state.error} onRetry={resource.refresh} />
  const periods = resource.state.data
  if (periods.imports.length === 0) return <Card><CardHeader><CardTitle>Períodos de telemetria</CardTitle></CardHeader><CardContent><p>Nenhuma importação persistida está disponível para este trator. Os períodos podem ser consultados antes do replay e da pontuação.</p></CardContent></Card>

  return <Card><CardHeader><CardTitle>Períodos de telemetria</CardTitle></CardHeader><CardContent className="stack">
    <p className="muted">Amostras observadas importadas antes do replay. A disponibilidade não representa diagnóstico.</p>
    {periods.imports.map((item) => <section className="stack" key={item.id}>
      <dl className="detail-list"><dt>Importação</dt><dd><code>{item.id}</code></dd><dt>Partição</dt><dd>{item.dataset_split}</dd><dt>Fonte</dt><dd>{item.source_format} · {item.source_file_name}</dd><dt>Intervalo</dt><dd>{formatDateTime(item.started_at_utc)} — {formatDateTime(item.ended_at_utc)} UTC</dd><dt>Amostras</dt><dd>{formatNumber(item.sample_count)}</dd><dt>Digest</dt><dd><code>{item.semantic_sha256.slice(0, 12)}…</code></dd></dl>
      <div className="table-wrap"><table><thead><tr><th>Missão</th><th>Início</th><th>Fim</th><th>Amostras</th><th>Duração observada</th><th>Replay</th></tr></thead><tbody>{item.missions.map((mission) => <tr key={mission.mission_index}><td>{mission.mission_index}</td><td>{formatDateTime(mission.started_at_utc)}</td><td>{formatDateTime(mission.ended_at_utc)}</td><td>{formatNumber(mission.sample_count)}</td><td>{formatNumber(mission.observed_duration_seconds)} s</td><td>{mission.replay_status}</td></tr>)}</tbody></table></div>
    </section>)}
  </CardContent></Card>
}

export { TelemetryPeriodsPanel }
