import type { Condition } from '../../lib/api-contracts'
import type { NumericSignal, Threshold } from './SignalChart'

type ChartDefinition = { signal: NumericSignal; label: string; unit: string; scale?: number; thresholds: Partial<Record<Condition, Threshold[]>> }

const charts: ChartDefinition[] = [
  { signal: 'engine_rpm', label: 'Rotação do motor', unit: 'rpm', thresholds: { lugging: [{ value: 600, label: '600' }, { value: 1400, label: '1.400' }] } },
  { signal: 'engine_load_pct', label: 'Carga do motor', unit: '%', thresholds: { lugging: [{ value: 70, label: '70%' }], thermal_under_load: [{ value: 70, label: '70%' }], harsh_torque_rise: [{ value: 70, label: '70%' }], overload_torque: [{ value: 90, label: '90%' }], loaded_high_slip: [{ value: 50, label: '50%' }] } },
  { signal: 'actual_engine_torque_pct', label: 'Torque do motor', unit: '%', thresholds: { overload_torque: [{ value: 85, label: '85%' }] } },
  { signal: 'torque_rise_1s', label: 'Subida de torque em 1 s', unit: 'pontos', thresholds: { harsh_torque_rise: [{ value: 35, label: '+35' }] } },
  { signal: 'traction_slip_pct', label: 'Patinagem', unit: '%', thresholds: { loaded_high_slip: [{ value: 20, label: '20%' }] } },
  { signal: 'coolant_temp_c', label: 'Temperatura do arrefecimento', unit: '°C', thresholds: { thermal_under_load: [{ value: 95, label: '95 °C' }] } },
  { signal: 'ground_machine_speed_mps', label: 'Velocidade real', unit: 'km/h', scale: 3.6, thresholds: { loaded_high_slip: [{ value: 1.8, label: '1,8' }] } },
]

const signalsByCondition: Record<Condition, NumericSignal[]> = {
  lugging: ['engine_rpm', 'engine_load_pct'],
  overload_torque: ['engine_load_pct', 'actual_engine_torque_pct'],
  loaded_high_slip: ['traction_slip_pct', 'ground_machine_speed_mps', 'engine_load_pct'],
  thermal_under_load: ['coolant_temp_c', 'engine_load_pct'],
  harsh_torque_rise: ['torque_rise_1s', 'engine_load_pct'],
}

function thresholdsFor(definition: ChartDefinition, conditions: string[]): Threshold[] {
  const unique = new Map<number, Threshold>()
  for (const condition of conditions) {
    for (const threshold of definition.thresholds[condition as Condition] ?? []) unique.set(threshold.value, threshold)
  }
  return [...unique.values()]
}

function previewCharts(conditions: string[]): ChartDefinition[] {
  const selected = new Set(conditions.flatMap((condition) => signalsByCondition[condition as Condition] ?? []))
  if (selected.size === 0) {
    selected.add('engine_rpm')
    selected.add('engine_load_pct')
  }
  return charts.filter((chart) => selected.has(chart.signal)).slice(0, 3)
}

export { charts, previewCharts, thresholdsFor }
