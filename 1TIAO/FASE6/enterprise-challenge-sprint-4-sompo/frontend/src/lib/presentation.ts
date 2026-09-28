import type { ExposureBand, FindingStatus, InspectionCase, Regimes } from './api-contracts'

export function formatDateTime(timestamp: string): string {
  return new Intl.DateTimeFormat('pt-BR', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'UTC' }).format(new Date(timestamp))
}

export function formatDate(timestamp: string): string {
  return new Intl.DateTimeFormat('pt-BR', { day: '2-digit', month: '2-digit', timeZone: 'UTC' }).format(new Date(timestamp))
}

export function formatNumber(value: number | null, digits = 2): string {
  if (value === null) return 'Sem dados'
  return new Intl.NumberFormat('pt-BR', { maximumFractionDigits: digits }).format(value)
}

export function formatScore(value: number | null): string {
  if (value === null) return 'Sem dados'
  return `${formatNumber(value, 1)} / 100`
}

export function formatTrend(value: number | null): string {
  if (value === null) return 'Sem dados'
  const sign = value > 0 ? '+' : ''
  return `${sign}${formatNumber(value, 1)} pontos`
}

export function formatDuration(seconds: number): string {
  const rounded = Math.round(seconds)
  if (rounded < 60) return `${rounded} s`
  const hours = Math.floor(rounded / 3600)
  const minutes = Math.floor((rounded % 3600) / 60)
  const rest = rounded % 60
  if (hours > 0) return minutes === 0 ? `${hours} h` : `${hours} h ${minutes} min`
  return rest === 0 ? `${minutes} min` : `${minutes} min ${rest} s`
}

export function tractorLabel(externalId: string, displayName: string | null): string {
  return displayName === null ? externalId : `${displayName} (${externalId})`
}

const signalNames: Record<string, string> = {
  engine_rpm: 'rotação do motor',
  actual_engine_torque_pct: 'torque do motor',
  engine_load_pct: 'carga do motor',
  accelerator_pct: 'acelerador',
  front_axle_speed_kph: 'velocidade do eixo dianteiro',
  speed_over_ground_mps: 'velocidade sobre o solo',
  ground_implement_speed_mmps: 'velocidade do implemento',
  wheel_vehicle_speed_kph: 'velocidade pelas rodas',
  rear_pto_rpm: 'rotação da TDP traseira',
  rear_hitch_position: 'posição do levante traseiro',
  rear_hitch_in_work: 'levante em trabalho',
  rear_link_force_pct: 'força nos braços do levante',
  rear_draft_n: 'esforço de tração no levante',
  ground_machine_speed_mps: 'velocidade real da máquina',
  machine_selected_speed_mps: 'velocidade selecionada',
  wheel_machine_speed_mps: 'velocidade das rodas',
  traction_slip_pct: 'patinagem',
  torque_rise_1s: 'subida de torque em 1 s',
  rpm_change_1s: 'variação de rotação em 1 s',
  speed_change_1s: 'variação de velocidade em 1 s',
}

const statisticNames: Record<string, string> = { mean: 'média', std: 'oscilação', max: 'pico' }

const metricNames: Record<string, string> = {
  physical_exposure_seconds_per_hour: 'exposição física por hora',
  alert_exposure_seconds_per_hour: 'exposição em alertas por hora',
  episodes_per_hour: 'episódios por hora',
}

export function formatMetricName(value: string): string {
  const known = metricNames[value]
  if (known !== undefined) return known
  const [signal, statistic] = value.split('__')
  const signalName = signal === undefined ? undefined : signalNames[signal]
  const statisticName = statistic === undefined ? undefined : statisticNames[statistic]
  if (signalName !== undefined && statisticName !== undefined) return `${statisticName} de ${signalName}`
  return value.replaceAll('__', ' · ').replaceAll('_', ' ')
}

export function formatContextualReason(reason: Record<string, string | number | boolean | null>): string {
  const feature = reason.feature
  const deviation = reason.robust_deviation
  if (typeof feature === 'string' && typeof deviation === 'number') {
    return `${formatMetricName(feature)}: desvio de ${formatNumber(deviation, 1)}× a faixa habitual`
  }
  return Object.entries(reason).map(([key, value]) => `${key}: ${value === null ? 'nulo' : String(value)}`).join(' · ')
}

const conditionNames: Record<string, string> = {
  lugging: 'baixa rotação sob carga',
  overload_torque: 'torque e carga elevados',
  loaded_high_slip: 'patinagem sob carga',
  thermal_under_load: 'temperatura elevada sob carga',
  harsh_torque_rise: 'aumento brusco de torque',
  severe_exposure: 'qualquer condição física',
}

const conditionRules: Record<string, string> = {
  lugging: 'rotação entre 600 e 1.400 rpm com carga acima de 70%',
  overload_torque: 'carga acima de 90% com torque acima de 85%',
  loaded_high_slip: 'patinagem acima de 20% com carga acima de 50% e máquina em movimento',
  thermal_under_load: 'arrefecimento a 95 °C ou mais com carga acima de 70%',
  harsh_torque_rise: 'torque subindo 35 pontos ou mais em 1 s com carga acima de 70%',
}

export function formatCondition(value: string): string {
  return conditionNames[value] ?? value.replaceAll('_', ' ')
}

export function formatConditionRule(value: string): string {
  return conditionRules[value] ?? ''
}

export function formatConfidence(value: 'HIGH' | 'MEDIUM' | 'LOW'): string {
  return value === 'HIGH' ? 'Alta' : value === 'MEDIUM' ? 'Média' : 'Baixa'
}

export function formatCoverage(activeDays: number, horizonDays: number): string {
  return `${activeDays} de ${horizonDays} dias com operação`
}

const regimeNames: Record<Regimes['labels'][number]['kind'], string> = {
  field_hitch_work: 'Campo com levante trabalhando',
  field_pto_variable: 'Campo com TDP em carga variável',
  road_transport: 'Deslocamento',
}

export function formatRegime(value: number, regimes?: Regimes): string {
  const label = regimes?.labels.find((item) => item.id === value)
  return label === undefined ? `Regime ${value}` : regimeNames[label.kind]
}

export function formatExposureBand(value: ExposureBand | null): string {
  if (value === 'ABOVE_TYPICAL') return 'Acima do típico'
  if (value === 'TYPICAL') return 'Dentro do típico'
  if (value === 'BELOW_TYPICAL') return 'Abaixo do típico'
  return 'Sem dados'
}

export function explainExposureBand(value: ExposureBand | null): string {
  if (value === 'ABOVE_TYPICAL') return 'O índice combinado de exposição ficou acima da faixa típica da referência Fendt 314.'
  if (value === 'TYPICAL') return 'O índice combinado de exposição ficou dentro da faixa típica da referência Fendt 314.'
  if (value === 'BELOW_TYPICAL') return 'O índice combinado de exposição ficou abaixo da faixa típica da referência Fendt 314.'
  return 'Não houve operação observada no período.'
}

const findingStatusNames: Record<FindingStatus, string> = {
  OK: 'Sem anomalia',
  ATTENTION: 'Atenção',
  PROBLEM: 'Problema encontrado',
  NOT_CHECKED: 'Não verificado',
}

export function formatFindingStatus(value: FindingStatus): string {
  return findingStatusNames[value]
}

export function findingNeedsNotes(value: FindingStatus): boolean {
  return value === 'ATTENTION' || value === 'PROBLEM'
}

export function formatCaseStatus(value: InspectionCase['status']): string {
  if (value === 'OPEN') return 'Aberto'
  if (value === 'IN_PROGRESS') return 'Em vistoria'
  if (value === 'COMPLETED') return 'Concluído'
  return 'Cancelado'
}

export function formatCaseResult(value: NonNullable<InspectionCase['result']>): string {
  if (value === 'NO_ACTION') return 'Nenhuma ação'
  if (value === 'MONITOR') return 'Monitorar'
  return 'Manutenção recomendada'
}
