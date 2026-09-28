import { NavLink, Outlet } from 'react-router-dom'
import { Button } from '../components/ui/button'
import { useState } from 'react'
import { usePrincipal, useSession } from './session-context'

const roleLabels = { ADMIN: 'Administrador', INSURER: 'Especialista da seguradora', INSPECTOR: 'Vistoriador', FLEET_MANAGER: 'Gestor da frota' }

function AppShell() {
  const principal = usePrincipal()
  const { signOut } = useSession()
  const [logoutError, setLogoutError] = useState(false)
  const [busy, setBusy] = useState(false)

  async function logout() {
    setBusy(true)
    setLogoutError(false)
    try { await signOut() }
    catch { setLogoutError(true) }
    finally { setBusy(false) }
  }

  return (
    <div className="shell">
      <header className="site-header"><div className="header-inner">
        <NavLink className="brand" to="/" end>Inspeção preventiva</NavLink>
        <div className="inline header-actions"><nav className="nav" aria-label="Navegação principal"><NavLink to="/" end>Máquinas</NavLink>{principal.role !== 'FLEET_MANAGER' ? <NavLink to="/vistorias">Vistorias</NavLink> : null}{principal.role === 'ADMIN' ? <NavLink to="/admin">Administração</NavLink> : null}</nav><span className="account-label">{roleLabels[principal.role]} · {principal.worker_id}</span><Button type="button" size="sm" variant="secondary" onClick={() => void logout()} disabled={busy}>Sair</Button></div>
      </div></header>
      {logoutError ? <div className="page" role="alert">Não foi possível encerrar a sessão. Tente novamente.</div> : null}
      <Outlet />
    </div>
  )
}

export { AppShell }
