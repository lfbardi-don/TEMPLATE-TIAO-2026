import { useState, useEffect, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { getCatalog, intakeError, sourceLabel, type CatalogMachine } from './intake-client'
import { MachineNavigation } from './MachineNavigation'

function MachineDataLayout({ tractorId, children, refreshKey = 0 }: { tractorId: string; children: ReactNode; refreshKey?: number }) {
  const [machine, setMachine] = useState<CatalogMachine | null>(null)
  const [fleet, setFleet] = useState('')
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    void getCatalog(controller.signal).then((catalog) => {
      const parent = catalog.fleets.find((item) => item.tractors.some((tractor) => tractor.id === tractorId))
      setFleet(parent?.name ?? '')
      setMachine(parent?.tractors.find((item) => item.id === tractorId) ?? null)
    }).catch((reason) => { if (!controller.signal.aborted) setError(intakeError(reason)) })
    return () => controller.abort()
  }, [tractorId, refreshKey])
  return <main className="page machine-data-page">
    <Link className="back-link" to="/">← Máquinas</Link>
    <div className="page-heading"><div><p className="eyebrow">{fleet || 'Máquina'}</p><h1>{machine?.display_name || machine?.external_id || 'Dados da máquina'}</h1><div className="inline"><span className="muted">{machine?.model_name}</span>{machine ? <span className={`source-tag ${machine.source_kind === 'simulated_csv' ? 'source-simulated' : ''}`}>{sourceLabel(machine.source_kind)}</span> : null}</div></div></div>
    <MachineNavigation tractorId={tractorId} />
    {error ? <p role="alert">{error}</p> : null}
    {children}
  </main>
}
export { MachineDataLayout }
