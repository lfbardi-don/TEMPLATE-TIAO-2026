import { useCallback, useState } from 'react'
import { Alert, AlertDescription, AlertTitle } from '../../components/ui/alert'
import { Button } from '../../components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card'
import { usePollingResource } from '../../hooks/usePollingResource'
import { usePrincipal } from '../../app/session-context'
import { getTractorOverview } from '../../lib/api-client'
import type { TractorOverview } from '../../lib/api-contracts'
import { formatCondition, formatDateTime, tractorLabel } from '../../lib/presentation'
import { LoadingView, ResourceError } from '../common/ResourceViews'
import { InspectionAgendaCard } from '../presentation/InspectionAgendaCard'
import { EpisodeTable } from './EpisodeTable'
import { ExposureSummary } from './ExposureSummary'
import { ExposureTimelineCard } from './ExposureTimelineCard'
import { InspectionCasesPanel } from './InspectionCasesPanel'
import { MachineNavigation } from '../catalog/MachineNavigation'
import '../inspection/workflow.css'

function MachineDetails({ overview }: { overview: TractorOverview }) {
  const principal = usePrincipal()
  const [condition, setCondition] = useState('')
  const [selectedAgenda, setSelectedAgenda] = useState<string | null>(null)
  const agenda = overview.workflow?.last_completed_case == null ? overview.inspection_agenda : { ...overview.inspection_agenda, items: overview.inspection_agenda.items.map((entry) => ({ ...entry, episode_ids: entry.episode_ids.filter((id) => overview.workflow!.new_episode_ids.includes(id)) })).filter((entry) => entry.episode_ids.length > 0) }
  const item = agenda.items.find((candidate) => candidate.id === selectedAgenda)
  const conditions = [...new Set(overview.episodes_last_30_days.flatMap((episode) => episode.conditions))]
  function selectAgenda(id: string) { setSelectedAgenda(id); setCondition(''); document.getElementById('machine-episodes')?.scrollIntoView?.({ behavior: 'smooth', block: 'start' }) }
  return <div className="stack">
    <div className={principal.role === 'FLEET_MANAGER' ? undefined : 'wf-machine-hero'}><ExposureSummary overview={overview} />
    {principal.role === 'FLEET_MANAGER' ? null : <InspectionCasesPanel tractorId={overview.tractor.id} workflow={overview.workflow} />}</div>
    <section className="stack" aria-label="Explorar episódios">
      <div className="wf-filters" aria-label="Filtrar condição física"><button type="button" aria-pressed={condition === ''} onClick={() => setCondition('')}>Todas as condições</button>{conditions.map((value) => <button type="button" key={value} aria-pressed={condition === value} onClick={() => setCondition(value)}>{formatCondition(value)}</button>)}</div>
      <ExposureTimelineCard tractorId={overview.tractor.id} asOf={overview.as_of_utc} condition={condition} />
      <EpisodeTable tractorId={overview.tractor.id} episodes={overview.episodes_last_30_days} regimes={overview.regimes} asOf={overview.as_of_utc} condition={condition} episodeIds={item?.episode_ids} onClearAgenda={() => setSelectedAgenda(null)} newEpisodeIds={overview.workflow?.last_completed_case == null ? undefined : overview.workflow.new_episode_ids} />
    </section>
    <InspectionAgendaCard agenda={agenda} onSelect={selectAgenda} emptyText="Nenhum componente pendente sugerido pelos episódios atuais." />
  </div>
}

function MachineView({ tractorId }: { tractorId: string }) {
  const loader = useCallback((signal: AbortSignal) => getTractorOverview(tractorId, signal), [tractorId])
  const resource = usePollingResource(loader, { successDelayMs: 5000 })
  const overview = resource.state.kind === 'success' ? resource.state.data : resource.state.kind === 'error' ? resource.state.data : null

  function content() {
    if (resource.state.kind === 'loading') return <LoadingView />
    if (resource.state.kind === 'empty') return <Card className="empty"><CardHeader><CardTitle>Aguardando dados de operação</CardTitle></CardHeader><CardContent><p>O resumo fica disponível após o processamento da telemetria. Esta página se atualiza automaticamente.</p></CardContent></Card>
    if (resource.state.kind === 'error') return <ResourceError error={resource.state.error} onRetry={resource.refresh}>{resource.state.data === null ? null : <><Alert variant="destructive"><AlertTitle>Dados possivelmente desatualizados</AlertTitle><AlertDescription>A última resposta válida continua visível, mas a atualização falhou.</AlertDescription></Alert><MachineDetails overview={resource.state.data} /></>}</ResourceError>
    return <MachineDetails overview={resource.state.data} />
  }

  return (
    <main className="page wf-machine-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">Máquina</p>
          <h1>{overview === null ? 'Trator' : tractorLabel(overview.tractor.external_id, overview.tractor.display_name)}</h1>
          {overview === null ? null : <p className="muted">{overview.fleet.name} · {overview.tractor.model_name} · dados até <time dateTime={overview.as_of_utc}>{formatDateTime(overview.as_of_utc)} UTC</time></p>}
          {overview?.provenance.some((item) => item.source_kind === 'simulated_csv') ? <span className="wf-synthetic">Dados simulados</span> : null}
        </div>
        <div className="stack"><Button type="button" variant="secondary" onClick={resource.refresh}>Atualizar agora</Button><span aria-live="polite" className="muted">{resource.isRefreshing ? 'Atualizando…' : ''}</span></div>
      </div>
      <MachineNavigation tractorId={tractorId} />
      <div className="stack">
        {content()}
      </div>
    </main>
  )
}

export { MachineView }
