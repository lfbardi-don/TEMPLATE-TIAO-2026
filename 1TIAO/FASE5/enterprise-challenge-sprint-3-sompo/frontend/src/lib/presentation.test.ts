import { describe, expect, it } from 'vitest'
import {
  formatCondition,
  formatConfidence,
  formatContextualReason,
  formatMetricName,
  formatPercent,
  formatPercentile,
  formatScore,
  formatTrend,
} from './presentation'

describe('presentation of the model scale and evidence', () => {
  it('keeps score points distinct from fractional coverage', () => {
    expect(formatScore(40.4)).toBe('40,4 / 100')
    expect(formatPercentile(66.7)).toBe('66,7º percentil')
    expect(formatTrend(3.2)).toBe('+3,2 pontos')
    expect(formatPercent(0.033)).toBe('3,3%')
  })

  it('translates stable evidence keys without changing their values', () => {
    expect(formatConfidence('LOW')).toBe('Baixa')
    expect(formatCondition('lugging')).toBe('baixa rotação sob carga')
    expect(formatMetricName('episodes_per_hour')).toBe('episódios por hora')
    expect(formatContextualReason({ feature: 'rpm_change_1s__mean', robust_deviation: 11.8 }))
      .toBe('variação média de RPM por segundo: desvio robusto 11,8')
  })
})
