import { NavLink, Outlet } from 'react-router-dom'
import { Badge } from '../components/ui/badge'
import { usePollingResource } from '../hooks/usePollingResource'
import { getReadiness } from '../lib/api-client'

function AppShell() {
  const readiness = usePollingResource(getReadiness, { successDelayMs: 10000, retryDelayMs: 10000 })
  const availability = readiness.state.kind === 'success' && readiness.state.data.status === 'ready' ? 'API pronta' : readiness.state.kind === 'loading' ? 'Verificando API' : 'API indisponível'
  const variant = readiness.state.kind === 'success' && readiness.state.data.status === 'ready' ? 'secondary' : 'warning'

  return (
    <div className="shell">
      <header className="site-header"><div className="header-inner">
        <NavLink className="brand" to="/" end>Inspeção preventiva<small>Fendt 314 · dados observados</small></NavLink>
        <div className="inline"><nav className="nav" aria-label="Navegação principal"><NavLink to="/" end>Demonstração</NavLink><NavLink to="/prioridades">Operação local</NavLink><NavLink to="/frotas/nova">Nova frota</NavLink></nav><Badge aria-live="polite" role="status" variant={variant}>{availability}</Badge></div>
      </div></header>
      <Outlet />
    </div>
  )
}

export { AppShell }
