import { useCallback, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { usePollingResource } from '../../hooks/usePollingResource'
import { formatDateTime, formatNumber } from '../../lib/presentation'
import { ResourceError } from '../common/ResourceViews'
import { MachineDataLayout } from './MachineDataLayout'
import { getTelemetryChart, sourceLabel, type TelemetrySample } from './intake-client'

const signals = [
  { key: 'engine_rpm', label: 'Rotação do motor', unit: 'rpm', scale: 1 },
  { key: 'actual_engine_torque_pct', label: 'Torque do motor', unit: '%', scale: 1 },
  { key: 'engine_load_pct', label: 'Carga do motor', unit: '%', scale: 1 },
  { key: 'ground_machine_speed_mps', label: 'Velocidade', unit: 'km/h', scale: 3.6 },
  { key: 'coolant_temp_c', label: 'Arrefecimento', unit: '°C', scale: 1 },
  { key: 'traction_slip_pct', label: 'Patinagem', unit: '%', scale: 1 },
  { key: 'rear_pto_rpm', label: 'Rotação da TDP', unit: 'rpm', scale: 1 },
] as const
type SignalKey = typeof signals[number]['key']
const timeLabel = (value: string) => new Date(value).toLocaleTimeString('pt-BR', { timeZone: 'UTC', hour: '2-digit', minute: '2-digit', second: '2-digit' })

function TelemetryPlot({ samples, initialSignal }: { samples: TelemetrySample[]; initialSignal: SignalKey }) {
  const [signal, setSignal] = useState<SignalKey>(initialSignal)
  const [selected, setSelected] = useState<number | null>(null)
  const definition = signals.find((item) => item.key === signal)!
  const values = samples.flatMap((sample) => sample[signal] === null ? [] : [sample[signal]! * definition.scale])
  const first = Date.parse(samples[0]?.observed_at_utc ?? '')
  const last = Date.parse(samples.at(-1)?.observed_at_utc ?? '')
  const low = Math.min(...values), high = Math.max(...values)
  const pad = Math.max(1, (high - low) * .08)
  const min = low >= 0 ? Math.max(0, low - pad) : low - pad, max = high + pad
  const x = (sample: TelemetrySample) => 58 + (Date.parse(sample.observed_at_utc) - first) / Math.max(1, last - first) * 510
  const y = (value: number) => 20 + (1 - (value - min) / (max - min)) * 150
  let path = '', drawing = false
  for (const sample of samples) {
    const value = sample[signal]
    if (value === null) { drawing = false; continue }
    path += `${drawing ? 'L' : 'M'}${x(sample).toFixed(2)},${y(value * definition.scale).toFixed(2)}`
    drawing = true
  }
  const point = selected === null ? null : samples[selected]
  const selectedValue = point?.[signal]
  return <section className="telemetry-plot ui-card"><div className="ui-card-content stack">
    <label className="field"><span className="visually-hidden">Sinal</span><select aria-label={`Sinal do gráfico ${initialSignal}`} value={signal} onChange={(event) => { setSignal(event.target.value as SignalKey); setSelected(null) }}>{signals.map((item) => <option value={item.key} key={item.key}>{item.label} ({item.unit})</option>)}</select></label>
    {values.length === 0 ? <p className="muted">Sinal indisponível nesta operação.</p> : <>
      <div className="spread"><strong>{formatNumber(low, 1)}–{formatNumber(high, 1)} {definition.unit}</strong><span className="muted">Faixa observada</span></div>
      <svg viewBox="0 0 600 214" role="img" aria-label={`${definition.label}, ${formatNumber(low, 1)} a ${formatNumber(high, 1)} ${definition.unit}`} onMouseLeave={() => setSelected(null)} onMouseMove={(event) => {
        const rect = event.currentTarget.getBoundingClientRect()
        const target = first + Math.max(0, Math.min(1, ((event.clientX - rect.left) / rect.width * 600 - 58) / 510)) * (last - first)
        let nearest = 0
        samples.forEach((sample, index) => { if (Math.abs(Date.parse(sample.observed_at_utc) - target) < Math.abs(Date.parse(samples[nearest]!.observed_at_utc) - target)) nearest = index })
        setSelected(nearest)
      }}>
        {[min, (min + max) / 2, max].map((value) => <g key={value}><line className="chart-axis" x1={58} x2={568} y1={y(value)} y2={y(value)} /><text className="chart-tick" x={50} y={y(value) + 4} textAnchor="end">{formatNumber(value, 0)}</text></g>)}
        <path className="chart-line" d={path} />
        {point && selectedValue !== null && selectedValue !== undefined ? <><line className="chart-threshold" x1={x(point)} x2={x(point)} y1={20} y2={170} /><circle className="chart-bar" cx={x(point)} cy={y(selectedValue * definition.scale)} r={4} /></> : null}
        <text className="chart-tick" x={58} y={190}>{timeLabel(samples[0]!.observed_at_utc)}</text><text className="chart-tick" x={568} y={190} textAnchor="end">{timeLabel(samples.at(-1)!.observed_at_utc)}</text><text className="chart-tick" x={313} y={210} textAnchor="middle">Horário UTC</text>
      </svg>
      <label className="chart-scrubber"><span>{point ? `${timeLabel(point.observed_at_utc)} UTC · ${selectedValue == null ? 'sem leitura' : `${formatNumber(selectedValue * definition.scale, 1)} ${definition.unit}`}` : 'Explore as amostras no gráfico ou pela barra'}</span><input type="range" aria-label={`Explorar ${definition.label}`} min={0} max={Math.max(0, samples.length - 1)} value={selected ?? 0} onChange={(event) => setSelected(Number(event.target.value))} /></label>
    </>}
  </div></section>
}

function TelemetryPage() {
  const { tractorId } = useParams()
  const [query, setQuery] = useSearchParams()
  const importId = query.get('import') ?? '', mission = query.get('mission') ?? ''
  const load = useCallback((signal: AbortSignal) => getTelemetryChart(tractorId!, importId, mission, signal), [tractorId, importId, mission])
  const resource = usePollingResource(load, { successDelayMs: 30000 })
  if (!tractorId) return null
  const data = resource.state.kind === 'success' || resource.state.kind === 'error' ? resource.state.data : null
  return <MachineDataLayout tractorId={tractorId}><div className="stack">
    <div className="spread"><h2>Telemetria da operação</h2><Link to={`/tratores/${tractorId}`}>Ver episódios sinalizados</Link></div>
    {resource.state.kind === 'loading' ? <p role="status">Carregando sinais…</p> : null}
    {resource.state.kind === 'empty' || data?.samples.length === 0 ? <div className="catalog-empty"><h3>Sem telemetria disponível</h3><p>A primeira importação habilita os gráficos desta máquina.</p></div> : null}
    {resource.state.kind === 'error' ? <ResourceError error={resource.state.error} onRetry={resource.refresh} /> : null}
    {data && data.samples.length ? <>
      <div className="telemetry-toolbar"><label className="field">Operação<select value={`${data.import_id}:${data.mission_index}`} onChange={(event) => { const [id, selectedMission] = event.target.value.split(':'); setQuery({ import: id!, mission: selectedMission! }) }}>{data.periods.map((period) => <option key={`${period.import_id}:${period.mission_index}`} value={`${period.import_id}:${period.mission_index}`}>{formatDateTime(period.started_at_utc)} → {timeLabel(period.ended_at_utc)} UTC</option>)}</select></label><span className="source-tag">{sourceLabel(data.source_kind)}</span><span className="muted">{formatNumber(data.samples.length, 0)} pontos de {formatNumber(data.total_samples, 0)} registros</span></div>
      <div className="grid two"><TelemetryPlot samples={data.samples} initialSignal="engine_rpm" /><TelemetryPlot samples={data.samples} initialSignal="actual_engine_torque_pct" /></div>
      <p className="muted">Visualização resumida. Os episódios permitem examinar os sinais segundo a segundo e as condições detectadas.</p>
    </> : null}
  </div></MachineDataLayout>
}
export { TelemetryPage }
