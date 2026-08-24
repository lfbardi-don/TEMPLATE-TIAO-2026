export function formatDateTime(timestamp: string): string {
  return new Intl.DateTimeFormat('pt-BR', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'UTC' }).format(new Date(timestamp))
}

export function formatNumber(value: number | null, digits = 2): string {
  if (value === null) return 'Sem dados'
  return new Intl.NumberFormat('pt-BR', { maximumFractionDigits: digits }).format(value)
}

export function formatPercent(value: number | null): string {
  if (value === null) return 'Sem dados'
  return new Intl.NumberFormat('pt-BR', { style: 'percent', maximumFractionDigits: 1 }).format(value)
}

export function formatScore(value: number | null): string {
  if (value === null) return 'Sem dados'
  return `${formatNumber(value, 1)} / 100`
}

export function formatPercentile(value: number): string {
  return `${formatNumber(value, 1)}º percentil`
}

export function formatTrend(value: number | null): string {
  if (value === null) return 'Sem dados'
  const sign = value > 0 ? '+' : ''
  return `${sign}${formatNumber(value, 1)} pontos`
}

export function tractorLabel(externalId: string, displayName: string | null): string {
  return displayName === null ? externalId : `${displayName} (${externalId})`
}

export function formatContextualReason(reason: Record<string, string | number | boolean | null>): string {
  const feature = reason.feature
  const deviation = reason.robust_deviation
  if (typeof feature === 'string' && typeof deviation === 'number') {
    return `${formatMetricName(feature)}: desvio robusto ${formatNumber(deviation, 1)}`
  }
  return Object.entries(reason).map(([key, value]) => `${key}: ${value === null ? 'nulo' : String(value)}`).join(' · ')
}

const metricNames: Record<string, string> = {
  physical_exposure_seconds_per_hour: 'exposição física por hora',
  alert_exposure_seconds_per_hour: 'exposição em alertas por hora',
  episodes_per_hour: 'episódios por hora',
  rear_hitch_position__std: 'variação da posição do levante traseiro',
  speed_change_1s__mean: 'variação média de velocidade por segundo',
  rpm_change_1s__mean: 'variação média de RPM por segundo',
}

const conditionNames: Record<string, string> = {
  lugging: 'baixa rotação sob carga',
  overload_torque: 'torque e carga elevados',
  loaded_high_slip: 'patinagem sob carga',
  thermal_under_load: 'temperatura elevada sob carga',
  harsh_torque_rise: 'aumento brusco de torque',
  severe_exposure: 'exposição severa combinada',
}

export function formatMetricName(value: string): string {
  return metricNames[value] ?? value.replaceAll('__', ' · ').replaceAll('_', ' ')
}

export function formatCondition(value: string): string {
  return conditionNames[value] ?? value.replaceAll('_', ' ')
}

export function formatConfidence(value: 'HIGH' | 'MEDIUM' | 'LOW'): string {
  return value === 'HIGH' ? 'Alta' : value === 'MEDIUM' ? 'Média' : 'Baixa'
}

export function formatScoreStatus(value: 'OK' | 'NO_DATA'): string {
  return value === 'OK' ? 'Com dados' : 'Sem dados'
}

export function formatRegime(value: number): string {
  return `Regime ${value}`
}
