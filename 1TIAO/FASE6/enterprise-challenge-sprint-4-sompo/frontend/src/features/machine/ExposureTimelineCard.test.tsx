import { render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { jsonResponse, stubApi } from '../../test/api-stub'
import { exposureTimelineFixture, tractorOverviewFixture } from '../../test/fixtures'
import { ExposureTimelineCard } from './ExposureTimelineCard'
afterEach(() => vi.unstubAllGlobals())
it('usa segundos da condição selecionada, não a soma de todas as condições', async () => {
  const zeros = { lugging: 0, overload_torque: 0, loaded_high_slip: 0, thermal_under_load: 0, harsh_torque_rise: 0 }
  const week = exposureTimelineFixture.weeks[0]!
  const fetchMock = stubApi(() => jsonResponse({ ...exposureTimelineFixture, weeks: [{ ...week, observed_hours: 2, physical_exposure_seconds: 100, physical_exposure_seconds_per_hour: 50, condition_seconds: { ...zeros, lugging: 10, overload_torque: 90 }, condition_episode_counts: { ...zeros, lugging: 1, overload_torque: 4 } }] }))
  render(<ExposureTimelineCard tractorId={tractorOverviewFixture.tractor.id} asOf={tractorOverviewFixture.as_of_utc} condition="lugging" />)
  expect(await screen.findByRole('img', { name: /20\/05: 5 s\/h/ })).toBeInTheDocument()
  expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining(`as_of_utc=${encodeURIComponent(tractorOverviewFixture.as_of_utc)}`), expect.any(Object))
})
