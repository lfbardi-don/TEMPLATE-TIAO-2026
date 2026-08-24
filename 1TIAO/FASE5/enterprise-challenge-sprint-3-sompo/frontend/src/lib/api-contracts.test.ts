import { describe, expect, it } from 'vitest'
import { tractorOverviewFixture } from '../test/fixtures'
import { tractorOverviewSchema } from './api-contracts'

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
