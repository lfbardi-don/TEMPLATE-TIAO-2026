import { NavLink } from 'react-router-dom'
import { usePrincipal } from '../../app/session-context'
import './catalog.css'

function MachineNavigation({ tractorId }: { tractorId: string }) {
  const principal = usePrincipal()
  const base = `/tratores/${tractorId}`
  return <nav className="machine-navigation" aria-label="Seções da máquina">
    <NavLink to={base} end>Visão geral</NavLink>
    <NavLink to={`${base}/telemetria`}>Telemetria</NavLink>
    {principal.role === 'INSURER' || principal.role === 'ADMIN' ? <NavLink to={`${base}/importacoes`}>Importações</NavLink> : null}
  </nav>
}
export { MachineNavigation }
