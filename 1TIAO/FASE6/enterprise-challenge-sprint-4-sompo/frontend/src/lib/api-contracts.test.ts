import { describe, expect, it } from 'vitest'
import { inProgressCaseFixture, tractorOverviewFixture } from '../test/fixtures'
import { inspectionCaseSchema, tractorOverviewSchema } from './api-contracts'

describe('inspectionCaseSchema', () => {
  it('exige a pauta congelada em snapshots v2', () => {
    const { inspection_agenda: _agenda, ...snapshot } = inProgressCaseFixture.evidence_snapshot

    expect(inspectionCaseSchema.safeParse({ ...inProgressCaseFixture, evidence_snapshot: snapshot }).success).toBe(false)
  })
})

describe('tractorOverviewSchema', () => {
  it('rejects a renamed score component from the API', () => {
    const response = structuredClone(tractorOverviewFixture)
    const score = response.scores['30_days']

    if (score.status !== 'OK') {
      throw new Error('fixture must contain an OK score')
    }

    const invalidResponse = {
      ...response,
      scores: {
        ...response.scores,
        '30_days': {
          ...score,
          component_percentiles: {
            ...score.component_percentiles,
            episodes: score.component_percentiles.episodes_per_hour,
          },
        },
      },
    }
    delete (invalidResponse.scores['30_days'].component_percentiles as Partial<Record<string, number>>).episodes_per_hour

    expect(tractorOverviewSchema.safeParse(invalidResponse).success).toBe(false)
  })
})
