import { useState } from 'react'
import type { EpisodeDetail } from '../../lib/api-contracts'
import { SignalChart, type NumericSignal } from './SignalChart'
import { charts, previewCharts, thresholdsFor } from './signal-definitions'

function EpisodeSignals({ detail, conditions = detail.episode.conditions }: { detail: EpisodeDetail; conditions?: string[] }) {
  const [selected, setSelected] = useState<NumericSignal[]>(() => previewCharts(conditions).map((chart) => chart.signal))
  const activeCharts = charts.filter((chart) => selected.includes(chart.signal))
  return <div className="stack">
    <div className="wf-filters" aria-label="Selecionar sinais">{charts.map((chart) => <button type="button" key={chart.signal} aria-pressed={selected.includes(chart.signal)} onClick={() => setSelected((current) => current.includes(chart.signal) ? current.filter((signal) => signal !== chart.signal) : [...current, chart.signal])}>{chart.label}</button>)}</div>
    {activeCharts.length === 0 ? <p className="muted">Selecione um sinal para ver o gráfico.</p> : <div className="wf-signal-grid">{activeCharts.map((chart) => <SignalChart key={chart.signal} samples={detail.samples} signal={chart.signal} label={chart.label} unit={chart.unit} scale={chart.scale} thresholds={thresholdsFor(chart, conditions)} activeConditions={conditions} />)}</div>}
    <p className="wf-caption">Faixas: condições selecionadas. Linhas tracejadas: limites da sinalização.</p>
  </div>
}
export { EpisodeSignals }
