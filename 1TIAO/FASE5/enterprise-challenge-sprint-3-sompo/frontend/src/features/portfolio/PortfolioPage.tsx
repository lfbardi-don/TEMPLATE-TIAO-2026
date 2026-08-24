import { Link } from 'react-router-dom'
import { Alert, AlertDescription, AlertTitle } from '../../components/ui/alert'
import { Button } from '../../components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card'
import { usePollingResource } from '../../hooks/usePollingResource'
import { getPortfolio } from '../../lib/api-client'
import { formatDateTime } from '../../lib/presentation'
import { LoadingView, ResourceError } from '../common/ResourceViews'
import { PriorityTable } from '../presentation/PriorityTable'

function PortfolioPage() {
  const resource = usePollingResource(getPortfolio)

  function content() {
    if (resource.state.kind === 'loading') return <LoadingView />
    if (resource.state.kind === 'empty') return <Card className="empty"><CardHeader><CardTitle>Fila ainda sem histórico</CardTitle></CardHeader><CardContent className="stack"><p>Cadastre uma frota e execute o replay observado no terminal para formar a fila local.</p><Button type="button" onClick={resource.refresh}>Atualizar</Button><Link to="/frotas/nova">Cadastrar frota</Link></CardContent></Card>
    if (resource.state.kind === 'error') return <ResourceError error={resource.state.error} onRetry={resource.refresh}>{resource.state.data === null ? null : <PriorityTable priorities={resource.state.data.priorities} />}</ResourceError>
    if (resource.state.data.priorities.length === 0) return <Card className="empty"><CardHeader><CardTitle>Fila vazia</CardTitle></CardHeader><CardContent className="stack"><p>Nenhum trator possui janelas observadas no fechamento atual.</p><Link to="/frotas/nova">Cadastrar uma frota e obter o comando de replay</Link></CardContent></Card>
    return <PriorityTable priorities={resource.state.data.priorities} />
  }

  const asOf = resource.state.kind === 'success' ? resource.state.data.as_of_utc : resource.state.kind === 'error' && resource.state.data !== null ? resource.state.data.as_of_utc : null
  return <main className="page"><div className="page-heading"><div><p className="eyebrow">Operação local · fila da API</p><h1>Prioridades de revisão preventiva</h1><p className="muted">A API local define a ordem e devolve as evidências. A fila orienta revisão preventiva; não diagnostica falha.</p></div><div className="stack"><Button type="button" variant="secondary" onClick={resource.refresh}>Atualizar agora</Button><span aria-live="polite" className="muted">{resource.isRefreshing ? 'Atualizando…' : ''}</span></div></div>{asOf === null ? null : <Alert><AlertTitle>Fechamento histórico</AlertTitle><AlertDescription><time dateTime={asOf}>{formatDateTime(asOf)} UTC</time> · evidência operacional.</AlertDescription></Alert>}<div style={{ marginTop: '18px' }}>{content()}</div></main>
}

export { PortfolioPage }
