import { useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { usePrincipal } from '../../app/session-context'
import { Button } from '../../components/ui/button'
import { Input } from '../../components/ui/input'
import { usePollingResource } from '../../hooks/usePollingResource'
import { LoadingView, ResourceError } from '../common/ResourceViews'
import { formatDateTime } from '../../lib/presentation'
import { addTractor, createFleet, getCatalog, intakeError, sourceLabel, type Catalog } from './intake-client'
import './catalog.css'

function RegisterMachine({ catalog }: { catalog: Catalog }) {
  const navigate = useNavigate()
  const [fleetId, setFleetId] = useState(catalog.fleets[0]?.id ?? 'new')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const lock = useRef(false)
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (lock.current) return
    const data = new FormData(event.currentTarget)
    const tractor = { external_id: String(data.get('external_id')).trim(), display_name: String(data.get('display_name')).trim() || null }
    if (!tractor.external_id) { setError('Informe o identificador da máquina.'); return }
    lock.current = true
    setBusy(true); setError(null)
    try {
      const signal = new AbortController().signal
      const id = fleetId === 'new'
        ? (await createFleet(String(data.get('fleet_name')).trim(), tractor, signal)).tractors[0]!.id
        : (await addTractor(fleetId, tractor, signal)).id
      navigate(`/tratores/${id}/importacoes`)
    } catch (reason) { setError(intakeError(reason)) }
    finally { lock.current = false; setBusy(false) }
  }
  return <details className="registration-panel ui-card">
    <summary>Cadastrar máquina</summary>
    <form className="stack" onSubmit={(event) => void save(event)}>
      <div className="grid two">
        <label className="field">Frota<select value={fleetId} onChange={(event) => setFleetId(event.target.value)} disabled={busy}>{catalog.fleets.map((fleet) => <option key={fleet.id} value={fleet.id}>{fleet.name}</option>)}<option value="new">Criar nova frota</option></select></label>
        {fleetId === 'new' ? <label className="field">Nome da nova frota<Input name="fleet_name" required maxLength={120} disabled={busy} /></label> : null}
        <label className="field">Identificador da máquina<Input name="external_id" placeholder="Ex.: AURORA-02" required maxLength={128} disabled={busy} /></label>
        <label className="field">Nome de exibição (opcional)<Input name="display_name" placeholder="Ex.: Trator do talhão norte" maxLength={120} disabled={busy} /></label>
      </div>
      <div className="spread"><span className="muted">Equipamento suportado: Fendt 314</span><Button type="submit" disabled={busy}>{busy ? 'Cadastrando…' : 'Cadastrar e importar dados'}</Button></div>
      {error ? <p role="alert" className="field-error">{error}</p> : null}
    </form>
  </details>
}

function CatalogPage() {
  const resource = usePollingResource(getCatalog, { successDelayMs: 15000 })
  const principal = usePrincipal()
  const [fleetFilter, setFleetFilter] = useState('')
  const data = resource.state.kind === 'success' || resource.state.kind === 'error' ? resource.state.data : null
  const fleets = data?.fleets.filter((fleet) => !fleetFilter || fleet.id === fleetFilter) ?? []
  const total = data?.fleets.reduce((sum, fleet) => sum + fleet.tractors.length, 0) ?? 0
  return <main className="page">
    <div className="page-heading"><div><p className="eyebrow">Operação</p><h1>Máquinas</h1><p className="muted">Selecione uma máquina para analisar a operação e acompanhar a vistoria.</p></div><Button variant="secondary" onClick={resource.refresh}>Atualizar</Button></div>
    <div className="stack">
      {resource.state.kind === 'loading' ? <LoadingView /> : null}
      {resource.state.kind === 'error' ? <ResourceError error={resource.state.error} onRetry={resource.refresh} /> : null}
      {data && principal.role === 'INSURER' ? <RegisterMachine catalog={data} /> : null}
      {data && data.fleets.length > 1 ? <label className="field fleet-filter">Filtrar por frota<select value={fleetFilter} onChange={(event) => setFleetFilter(event.target.value)}><option value="">Todas as frotas ({data.fleets.length})</option>{data.fleets.map((fleet) => <option key={fleet.id} value={fleet.id}>{fleet.name}</option>)}</select></label> : null}
      {data && total === 0 ? <div className="catalog-empty"><h2>Nenhuma máquina cadastrada</h2><p>{principal.role === 'INSURER' ? 'Cadastre a primeira máquina e importe os dados de operação.' : 'As máquinas aparecerão aqui quando forem cadastradas para o seu acesso.'}</p></div> : null}
      {fleets.map((fleet) => <section className="stack" key={fleet.id} aria-label={fleet.name}>
        <div className="spread"><h2>{fleet.name}</h2><span className="muted">{fleet.tractors.length} {fleet.tractors.length === 1 ? 'máquina' : 'máquinas'}</span></div>
        <div className="machine-grid">{fleet.tractors.map((machine) => <article className="machine-tile" key={machine.id}>
          <div className="spread"><span className="eyebrow">{machine.model_name}</span><span className={`source-tag ${machine.source_kind === 'simulated_csv' ? 'source-simulated' : ''}`}>{sourceLabel(machine.source_kind)}</span></div>
          <h3>{machine.display_name || machine.external_id}</h3><span className="muted">{machine.external_id}</span>
          <div className="machine-data-status"><span className={`data-dot ${machine.window_count ? 'has-data' : ''}`} /><span>{machine.latest_observed_at_utc ? `Dados até ${formatDateTime(machine.latest_observed_at_utc)} UTC` : 'Aguardando primeira importação'}</span></div>
          <Link className="ui-button ui-button-primary ui-button-default" to={machine.window_count || principal.role !== 'INSURER' ? `/tratores/${machine.id}` : `/tratores/${machine.id}/importacoes`}>{machine.window_count ? 'Ver análise' : principal.role === 'INSURER' ? 'Importar dados' : 'Ver máquina'}</Link>
        </article>)}</div>
      </section>)}
    </div>
  </main>
}
export { CatalogPage }
