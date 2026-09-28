import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { Alert, AlertDescription, AlertTitle } from '../../components/ui/alert'
import { Button } from '../../components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card'
import { Input } from '../../components/ui/input'
import { Label } from '../../components/ui/label'
import { usePrincipal } from '../../app/session-context'
import { ApiHttpError, createAdminUser, getAdminCatalog, getAdminUserEvents, getAdminUsers, resetAdminUserPassword, updateAdminUser } from '../../lib/api-client'
import type { AdminCatalog, AdminUser, AdminUserEvent, AdminUserEvents, AdminUsers, CreateAdminUserRequest, Principal, UpdateAdminUserRequest } from '../../lib/api-contracts'
import { formatDateTime, tractorLabel } from '../../lib/presentation'
import { LoadingView, ResourceError } from '../common/ResourceViews'

type AdminData = { accounts: AdminUsers; history: AdminUserEvents; catalog: AdminCatalog }
type FleetOption = { id: string; name: string }
type TemporaryPassword = { workerId: string; password: string }

const roleLabels: Record<Principal['role'], string> = {
  ADMIN: 'Administrador', INSURER: 'Especialista da seguradora', INSPECTOR: 'Vistoriador', FLEET_MANAGER: 'Gestor da frota',
}

function fleetOptions(data: AdminData): FleetOption[] {
  return data.catalog.fleets.map(({ id, name }) => ({ id, name }))
}

function FleetSelect({ id, value, onChange, fleets, disabled }: { id: string; value: string; onChange: (value: string) => void; fleets: FleetOption[]; disabled: boolean }) {
  return <select id={id} value={value} onChange={(event) => onChange(event.target.value)} disabled={disabled} required>
    <option value="">Selecione a frota</option>
    {fleets.map((fleet) => <option key={fleet.id} value={fleet.id}>{fleet.name}</option>)}
  </select>
}

function AccountRow({ account, fleets, busy, self, onUpdate, onReset }: {
  account: AdminUser; fleets: FleetOption[]; busy: boolean; self: boolean
  onUpdate: (id: string, payload: UpdateAdminUserRequest) => Promise<void>
  onReset: (account: AdminUser) => Promise<void>
}) {
  const [role, setRole] = useState<Principal['role']>(account.role)
  const [fleetId, setFleetId] = useState(account.fleet_id ?? '')
  const [active, setActive] = useState(account.active)
  const selectedFleet = role === 'FLEET_MANAGER' ? fleetId || null : null
  const changed = role !== account.role || selectedFleet !== account.fleet_id || active !== account.active
  const valid = role !== 'FLEET_MANAGER' || selectedFleet !== null

  return <tr>
    <th scope="row"><strong>{account.worker_id}</strong><span className="muted account-created">Desde {formatDateTime(account.created_at_utc)} UTC</span></th>
    <td><select aria-label={`Perfil de ${account.worker_id}`} value={role} onChange={(event) => setRole(event.target.value as Principal['role'])} disabled={busy || self}>{Object.entries(roleLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></td>
    <td>{role === 'FLEET_MANAGER' ? <><label className="visually-hidden" htmlFor={`account-fleet-${account.id}`}>Frota de {account.worker_id}</label><FleetSelect id={`account-fleet-${account.id}`} value={fleetId} onChange={setFleetId} fleets={fleets} disabled={busy} /></> : <span className="muted">Todas as frotas</span>}</td>
    <td><label className="inline"><input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} disabled={busy || self} />Ativa</label></td>
    <td><div className="inline"><Button type="button" size="sm" disabled={busy || self || !changed || !valid} onClick={() => void onUpdate(account.id, { role, fleet_id: selectedFleet, active })}>Salvar alterações</Button><Button type="button" size="sm" variant="secondary" disabled={busy} onClick={() => void onReset(account)}>Redefinir senha</Button></div></td>
  </tr>
}

function accountEventDetails(event: AdminUserEvent): string | null {
  if (event.action === 'CREATE') return `Perfil: ${roleLabels[event.details.role]} · ${event.details.active ? 'conta ativa' : 'conta inativa'}${event.details.fleet_id === null ? '' : ` · frota ${event.details.fleet_id}`}`
  if (event.action === 'UPDATE') {
    const { role, fleet_id: fleetId, active } = event.details.changes
    const changes = [
      role === undefined ? null : `Perfil: ${roleLabels[role.from]} → ${roleLabels[role.to]}`,
      fleetId === undefined ? null : `Frota: ${fleetId.from ?? 'nenhuma'} → ${fleetId.to ?? 'nenhuma'}`,
      active === undefined ? null : `Conta: ${active.from ? 'ativa' : 'inativa'} → ${active.to ? 'ativa' : 'inativa'}`,
    ].filter((change) => change !== null)
    return changes.length === 0 ? null : changes.join(' · ')
  }
  return null
}

function AdminPage() {
  const principal = usePrincipal()
  const [data, setData] = useState<AdminData | null>(null)
  const [loadError, setLoadError] = useState<ApiHttpError | null>(null)
  const [revision, setRevision] = useState(0)
  const [workerId, setWorkerId] = useState('')
  const [role, setRole] = useState<Principal['role']>('INSPECTOR')
  const [fleetId, setFleetId] = useState('')
  const [temporaryPassword, setTemporaryPassword] = useState<TemporaryPassword | null>(null)
  const [mutationError, setMutationError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    void Promise.all([getAdminUsers(controller.signal), getAdminUserEvents(controller.signal), getAdminCatalog(controller.signal)])
      .then(([accounts, history, catalog]) => {
        if (!controller.signal.aborted) { setData({ accounts, history, catalog }); setLoadError(null) }
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setLoadError(error instanceof ApiHttpError ? error : new ApiHttpError('network', 'Não foi possível consultar a administração.'))
      })
    return () => controller.abort()
  }, [revision])

  function refresh() { setRevision((value) => value + 1) }

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true); setMutationError(null)
    const payload: CreateAdminUserRequest = { worker_id: workerId, role, fleet_id: role === 'FLEET_MANAGER' ? fleetId || null : null }
    try {
      const response = await createAdminUser(payload, new AbortController().signal)
      setTemporaryPassword({ workerId: response.user.worker_id, password: response.temporary_password })
      setWorkerId(''); setRole('INSPECTOR'); setFleetId('')
      refresh()
    } catch (error: unknown) { setMutationError(mutationMessage(error)) } finally { setBusy(false) }
  }

  async function update(id: string, payload: UpdateAdminUserRequest) {
    setBusy(true); setMutationError(null)
    try { await updateAdminUser(id, payload, new AbortController().signal); refresh() }
    catch (error: unknown) { setMutationError(mutationMessage(error)) }
    finally { setBusy(false) }
  }

  async function reset(account: AdminUser) {
    setBusy(true); setMutationError(null)
    try {
      const response = await resetAdminUserPassword(account.id, new AbortController().signal)
      setTemporaryPassword({ workerId: account.worker_id, password: response.temporary_password })
      if (account.id !== principal.id) refresh()
    } catch (error: unknown) { setMutationError(mutationMessage(error)) } finally { setBusy(false) }
  }

  if (data === null && loadError === null) return <main className="page"><LoadingView /></main>
  if (data === null && loadError !== null) return <main className="page"><ResourceError error={loadError} onRetry={refresh} /></main>
  if (data === null) return null
  const fleets = fleetOptions(data)
  const activeAccounts = [...data.accounts.users].sort((left, right) => left.worker_id.localeCompare(right.worker_id))
  const events = [...data.history.events].sort((left, right) => right.occurred_at_utc.localeCompare(left.occurred_at_utc))

  return <main className="page stack">
    <div className="page-heading"><div><p className="eyebrow">Administração</p><h1>Contas e acesso</h1><p className="muted">Administre os trabalhadores e consulte o histórico de alterações das contas.</p></div></div>
    {loadError === null ? null : <ResourceError error={loadError} onRetry={refresh} />}
    {mutationError === null ? null : <Alert variant="destructive"><AlertTitle>Operação não concluída</AlertTitle><AlertDescription>{mutationError}</AlertDescription></Alert>}
    {temporaryPassword === null ? null : <Alert><AlertTitle>Senha temporária de {temporaryPassword.workerId}</AlertTitle><AlertDescription><strong><code>{temporaryPassword.password}</code></strong><p>Copie a senha agora. Ela é exibida uma única vez e não aparece no histórico.{temporaryPassword.workerId === principal.worker_id ? ' Sua sessão foi encerrada; entre novamente com a nova senha depois de copiá-la.' : ''}</p><Button type="button" size="sm" variant="secondary" onClick={() => setTemporaryPassword(null)}>Dispensar senha</Button></AlertDescription></Alert>}
    <Card><CardHeader><CardTitle>Criar conta</CardTitle></CardHeader><CardContent>
      <form className="grid three" onSubmit={(event) => void create(event)}>
        <div className="field"><Label htmlFor="new-worker-id">Número do trabalhador</Label><Input id="new-worker-id" inputMode="numeric" pattern="[0-9]{1,20}" maxLength={20} required value={workerId} onChange={(event) => setWorkerId(event.target.value.replace(/[^0-9]/g, '').slice(0, 20))} disabled={busy} /></div>
        <div className="field"><Label htmlFor="new-role">Perfil</Label><select id="new-role" value={role} onChange={(event) => setRole(event.target.value as Principal['role'])} disabled={busy}>{Object.entries(roleLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
        {role === 'FLEET_MANAGER' ? <div className="field"><Label htmlFor="new-fleet">Frota</Label><FleetSelect id="new-fleet" value={fleetId} onChange={setFleetId} fleets={fleets} disabled={busy} /></div> : null}
        <div className="field-action"><Button type="submit" disabled={busy || (role === 'FLEET_MANAGER' && fleetId === '')}>Criar conta</Button></div>
      </form>
      {fleets.length === 0 ? <p className="muted">Nenhuma frota cadastrada está disponível para o perfil de gestor.</p> : null}
    </CardContent></Card>
    <Card><CardHeader><CardTitle>Trabalhadores</CardTitle></CardHeader><CardContent>
      {activeAccounts.length === 0 ? <p>Nenhuma conta cadastrada.</p> : <div className="table-wrap"><table className="ui-table admin-accounts"><thead><tr><th scope="col">Número</th><th scope="col">Perfil</th><th scope="col">Frota</th><th scope="col">Acesso</th><th scope="col">Ações</th></tr></thead><tbody>{activeAccounts.map((account) => <AccountRow key={`${account.id}:${account.role}:${account.fleet_id}:${account.active}`} account={account} fleets={fleets} busy={busy} self={account.id === principal.id} onUpdate={update} onReset={reset} />)}</tbody></table></div>}
      <p className="muted">Desativar uma conta impede novos acessos. A própria conta de administrador não pode ter perfil ou acesso alterados aqui. A redefinição entrega uma nova senha temporária uma única vez.</p>
    </CardContent></Card>
    <Card><CardHeader><CardTitle>Frotas e máquinas cadastradas</CardTitle></CardHeader><CardContent>
      {data.catalog.fleets.length === 0 ? <p>Nenhuma frota cadastrada.</p> : <ul className="admin-fleets">{data.catalog.fleets.map((fleet) => <li key={fleet.id}><strong>{fleet.name}</strong>{fleet.tractors.length === 0 ? <p className="muted">Nenhuma máquina cadastrada nesta frota.</p> : <ul className="admin-machines">{fleet.tractors.map((tractor) => <li key={tractor.id}><Link to={`/tratores/${tractor.id}`}>{tractorLabel(tractor.external_id, tractor.display_name)}</Link><span className="muted">{tractor.model_name}</span></li>)}</ul>}</li>)}</ul>}
    </CardContent></Card>
    <Card><CardHeader><CardTitle>Histórico de contas</CardTitle></CardHeader><CardContent>
      {events.length === 0 ? <p>Nenhuma alteração de conta registrada.</p> : <ol className="case-events admin-events">{events.map((event) => <li key={event.id}><div className="spread"><strong>{event.action === 'CREATE' ? 'Conta criada' : event.action === 'UPDATE' ? 'Conta atualizada' : 'Senha redefinida'}</strong><time dateTime={event.occurred_at_utc}>{formatDateTime(event.occurred_at_utc)} UTC</time></div><p>Trabalhador {event.actor_worker_id} → conta {event.target_worker_id}</p>{accountEventDetails(event) === null ? null : <p className="muted">{accountEventDetails(event)}</p>}</li>)}</ol>}
      <p className="muted">Este histórico registra alterações de contas; ações nos casos de vistoria aparecem no histórico de cada caso.</p>
    </CardContent></Card>
    <p className="muted">Sessão atual: administrador {principal.worker_id}. <Link to="/">Ver máquinas</Link>.</p>
  </main>
}

function mutationMessage(error: unknown): string {
  if (error instanceof ApiHttpError && error.status === 409) return 'O número do trabalhador já existe ou esta alteração entrou em conflito. Atualize a lista e tente novamente.'
  if (error instanceof ApiHttpError && error.status === 400) return 'Revise o perfil, a frota e o estado da conta antes de tentar novamente.'
  return 'Não foi possível salvar a alteração. Verifique a conexão e tente novamente.'
}

export { AdminPage }
