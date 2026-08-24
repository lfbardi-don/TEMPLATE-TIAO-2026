import { useCallback } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Alert, AlertDescription, AlertTitle } from '../../components/ui/alert'
import { Button } from '../../components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card'
import { usePollingResource } from '../../hooks/usePollingResource'
import { getFleetOverview } from '../../lib/api-client'
import { formatDateTime } from '../../lib/presentation'
import { LoadingView, ResourceError } from '../common/ResourceViews'
import { PriorityTable } from '../presentation/PriorityTable'

function FleetOverviewPage() {
  const { fleetId } = useParams()
  const loader = useCallback((signal: AbortSignal) => fleetId === undefined ? Promise.reject(new Error('Identificador de frota ausente.')) : getFleetOverview(fleetId, signal), [fleetId])
  const resource = usePollingResource(loader)

  function content() {
    if (resource.state.kind === 'loading') return <LoadingView />
    if (resource.state.kind === 'empty') return <Card className="empty"><CardHeader><CardTitle>Frota não encontrada ou sem histórico</CardTitle></CardHeader><CardContent><p>A consulta será refeita automaticamente. Você também pode cadastrar uma nova frota.</p><Link to="/frotas/nova">Cadastrar frota</Link></CardContent></Card>
    if (resource.state.kind === 'error') return <ResourceError error={resource.state.error} onRetry={resource.refresh}>{resource.state.data === null ? null : <PriorityTable priorities={resource.state.data.priorities} />}</ResourceError>
    const overview = resource.state.data
    return <div className="stack"><div className="grid three"><Card><CardHeader><CardTitle>Tratores</CardTitle></CardHeader><CardContent><strong>{overview.totals.tractors}</strong></CardContent></Card><Card><CardHeader><CardTitle>Com dados</CardTitle></CardHeader><CardContent><strong>{overview.status_counts.OK ?? 0}</strong></CardContent></Card><Card><CardHeader><CardTitle>Sem dados</CardTitle></CardHeader><CardContent><strong>{overview.status_counts.NO_DATA ?? 0}</strong></CardContent></Card></div>{overview.priorities.length === 0 ? <Card><CardContent><p>Esta frota ainda não possui janelas observadas.</p></CardContent></Card> : <PriorityTable priorities={overview.priorities} />}</div>
  }

  const overview = resource.state.kind === 'success' ? resource.state.data : resource.state.kind === 'error' ? resource.state.data : null
  return <main className="page"><div className="page-heading"><div><p className="eyebrow">Visão da frota</p><h1>{overview === null ? 'Frota' : overview.fleet.name}</h1><p className="muted">Prioridade e totais são fornecidos sem recálculo pelo navegador.</p></div><div className="stack"><Button type="button" variant="secondary" onClick={resource.refresh}>Atualizar agora</Button><span aria-live="polite" className="muted">{resource.isRefreshing ? 'Atualizando…' : ''}</span></div></div>{overview === null ? null : <Alert><AlertTitle>Fechamento histórico</AlertTitle><AlertDescription><time dateTime={overview.as_of_utc}>{formatDateTime(overview.as_of_utc)} UTC</time> · evidência operacional.</AlertDescription></Alert>}<div style={{ marginTop: '18px' }}>{content()}</div></main>
}

export { FleetOverviewPage }
