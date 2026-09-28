import type { EpisodeSample } from '../../lib/api-contracts'
import { formatNumber } from '../../lib/presentation'

type NumericSignal = 'engine_rpm' | 'engine_load_pct' | 'actual_engine_torque_pct' | 'coolant_temp_c' | 'traction_slip_pct' | 'torque_rise_1s' | 'ground_machine_speed_mps'
type Threshold = { value: number; label: string }

const WIDTH = 560
const HEIGHT = 170
const MARGIN = { top: 12, right: 56, bottom: 22, left: 44 }

function SignalChart({ samples, signal, label, unit, thresholds = [], scale = 1, activeConditions }: {
  samples: EpisodeSample[]; signal: NumericSignal; label: string; unit: string; thresholds?: Threshold[]; scale?: number; activeConditions?: string[]
}) {
  const start = Date.parse(samples[0]?.observed_at_utc ?? '')
  const points = samples.map((sample) => ({
    x: (Date.parse(sample.observed_at_utc) - start) / 1000,
    y: sample[signal] === null ? null : (sample[signal] as number) * scale,
    active: activeConditions === undefined ? sample.conditions.length > 0 : sample.conditions.some((condition) => activeConditions.includes(condition)),
  }))
  const values = points.flatMap((point) => point.y === null ? [] : [point.y])
  if (values.length === 0) {
    return <figure className="signal-chart"><figcaption>{label}</figcaption><p className="muted">Sinal indisponível neste trecho.</p></figure>
  }
  const duration = Math.max(1, points[points.length - 1]?.x ?? 1)
  const domain = [...values, ...thresholds.map((threshold) => threshold.value)]
  const low = Math.min(...domain)
  const high = Math.max(...domain)
  const padding = Math.max(1, (high - low) * 0.08)
  const yMin = low >= 0 ? Math.max(0, low - padding) : low - padding
  const yMax = high + padding
  const plotWidth = WIDTH - MARGIN.left - MARGIN.right
  const plotHeight = HEIGHT - MARGIN.top - MARGIN.bottom
  const x = (value: number) => MARGIN.left + (value / duration) * plotWidth
  const y = (value: number) => MARGIN.top + (1 - (value - yMin) / (yMax - yMin)) * plotHeight
  const secondWidth = Math.max(1, plotWidth / duration)

  let path = ''
  let drawing = false
  for (const point of points) {
    if (point.y === null) { drawing = false; continue }
    path += `${drawing ? 'L' : 'M'}${x(point.x).toFixed(1)},${y(point.y).toFixed(1)}`
    drawing = true
  }

  return (
    <figure className="signal-chart">
      <figcaption>{label} <span className="muted">({unit})</span></figcaption>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={`${label}: de ${formatNumber(Math.min(...values), 1)} a ${formatNumber(Math.max(...values), 1)} ${unit} em ${formatNumber(duration, 0)} segundos`}>
        {points.map((point) => point.active ? <rect key={point.x} className="chart-active" x={x(point.x)} y={MARGIN.top} width={secondWidth} height={plotHeight} /> : null)}
        {thresholds.map((threshold) => (
          <g key={`${threshold.label}-${threshold.value}`}>
            <line className="chart-threshold" x1={MARGIN.left} x2={MARGIN.left + plotWidth} y1={y(threshold.value)} y2={y(threshold.value)} />
            <text className="chart-threshold-label" x={MARGIN.left + plotWidth + 4} y={y(threshold.value) + 4}>{threshold.label}</text>
          </g>
        ))}
        <path className="chart-line" d={path} />
        <text className="chart-tick" x={MARGIN.left - 6} y={MARGIN.top + 8} textAnchor="end">{formatNumber(yMax, 0)}</text>
        <text className="chart-tick" x={MARGIN.left - 6} y={MARGIN.top + plotHeight} textAnchor="end">{formatNumber(yMin, 0)}</text>
        <text className="chart-tick" x={MARGIN.left} y={HEIGHT - 4}>0 s</text>
        <text className="chart-tick" x={MARGIN.left + plotWidth} y={HEIGHT - 4} textAnchor="end">{formatNumber(duration, 0)} s</text>
      </svg>
    </figure>
  )
}

export { SignalChart }
export type { NumericSignal, Threshold }
