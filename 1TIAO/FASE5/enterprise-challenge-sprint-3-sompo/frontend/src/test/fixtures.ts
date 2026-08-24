import { fleetRegistrationSchema, fleetOverviewSchema, portfolioSchema, tractorOverviewSchema } from '../lib/api-contracts'

const fleet = {
  id: '11111111-1111-4111-8111-111111111111',
  name: 'Fazenda Horizonte',
  created_at_utc: '2024-06-01T10:00:00+00:00',
}

const tractor = {
  id: '22222222-2222-4222-8222-222222222222',
  fleet_id: fleet.id,
  external_id: 'FENDT-314-01',
  display_name: 'Trator Norte',
  model_name: 'Fendt 314',
  created_at_utc: '2024-06-01T10:00:00+00:00',
}

const score = {
  status: 'OK',
  as_of_utc: '2024-06-03T10:00:00+00:00',
  observed_hours: 3.5,
  active_days: 2,
  calendar_coverage: 0.5,
  confidence: 'HIGH',
  physical_exposure_seconds_per_hour: 12.4,
  alert_exposure_seconds_per_hour: 3.1,
  episodes_per_hour: 0.2,
  episode_count: 1,
  represented_conditions: ['lugging'],
  predominant_regimes: [1],
  component_percentiles: {
    physical_exposure_seconds_per_hour: 40,
    alert_exposure_seconds_per_hour: 50,
    episodes_per_hour: 60,
  },
  relative_exposure_score: 50,
}

const scores = { '7_days': score, '15_days': score, '30_days': score }
const provenance = [{ source_kind: 'observed_dataset_replay', dataset_split: 'validation', source_reference: 'doi:10.5281/zenodo.14619787#file=fendt314-stress-1s.csv.gz' }]
const episode = {
  id: 'episode-1', mission_index: 277, started_at_utc: '2024-06-03T09:00:00+00:00', ended_at_utc: '2024-06-03T09:01:00+00:00', alerted_seconds: 8, physical_exposure_seconds: 12, conditions: ['lugging'], operational_regimes: [1], maximum_contextual_rarity_score: 0.98, contextual_reasons: [{ feature: 'engine_rpm', value: 900 }],
}
const priority = {
  rank: 1, fleet, tractor, as_of_utc: score.as_of_utc, scores, previous_30_day_score: 40, trend_30_day: 10, confidence: 'HIGH', observed_hours: 3.5, episode_count: 1, predominant_conditions: ['lugging'], episodes_last_30_days: [episode], provenance,
}

const portfolioFixture = portfolioSchema.parse({ evidence_role: 'operational_output_only', as_of_utc: score.as_of_utc, priorities: [priority] })
const fleetOverviewFixture = fleetOverviewSchema.parse({ evidence_role: 'operational_output_only', fleet, as_of_utc: score.as_of_utc, totals: { tractors: 1 }, status_counts: { OK: 1, NO_DATA: 0 }, priorities: [priority] })
const tractorOverviewFixture = tractorOverviewSchema.parse({ evidence_role: 'operational_output_only', fleet, tractor, as_of_utc: score.as_of_utc, scores, previous_30_day_score: 40, trend_30_day: 10, confidence: 'HIGH', observed_hours: 3.5, episodes_last_30_days: [episode], provenance })
const registrationFixture = fleetRegistrationSchema.parse({ evidence_role: 'operational_output_only', fleet, tractors: [tractor] })

export { fleetOverviewFixture, portfolioFixture, registrationFixture, tractorOverviewFixture }
