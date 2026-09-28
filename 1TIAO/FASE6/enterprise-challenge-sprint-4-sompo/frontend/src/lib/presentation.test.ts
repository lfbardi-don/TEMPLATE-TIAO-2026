import { describe, expect, it } from 'vitest'
import {
  formatCondition,
  formatConfidence,
  formatContextualReason,
  formatCoverage,
  formatDuration,
  formatExposureBand,
  formatMetricName,
  formatRegime,
  formatScore,
  formatTrend,
} from './presentation'

describe('presentation of the model scale and evidence', () => {
  it('formats score points and trends', () => {
    expect(formatScore(40.4)).toBe('40,4 / 100')
    expect(formatTrend(3.2)).toBe('+3,2 pontos')
  })

  it('translates stable evidence keys without changing their values', () => {
    expect(formatConfidence('LOW')).toBe('Baixa')
    expect(formatCondition('lugging')).toBe('baixa rotação sob carga')
    expect(formatMetricName('episodes_per_hour')).toBe('episódios por hora')
    expect(formatMetricName('rear_hitch_position__std')).toBe('oscilação de posição do levante traseiro')
    expect(formatContextualReason({ feature: 'rpm_change_1s__mean', robust_deviation: 11.8 }))
      .toBe('média de variação de rotação em 1 s: desvio de 11,8× a faixa habitual')
  })

  it('names what the operator and the inspector recognise', () => {
    const regimes = { version: 'regime-labels-v1' as const, labels: [{ id: 2, kind: 'road_transport' as const }] }
    expect(formatRegime(2, regimes)).toBe('Deslocamento')
    expect(formatRegime(7, regimes)).toBe('Regime 7')
    expect(formatExposureBand('ABOVE_TYPICAL')).toBe('Acima do típico')
    expect(formatExposureBand(null)).toBe('Sem dados')
    expect(formatCoverage(13, 30)).toBe('13 de 30 dias com operação')
    expect(formatDuration(45)).toBe('45 s')
    expect(formatDuration(180)).toBe('3 min')
    expect(formatDuration(3_725)).toBe('1 h 2 min')
  })
})
