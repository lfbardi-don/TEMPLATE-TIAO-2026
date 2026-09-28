import { episodeDetailSchema, exposureTimelineSchema, inspectionCaseSchema, tractorOverviewSchema } from '../lib/api-contracts'

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
    physical_exposure_seconds_per_hour: 70,
    alert_exposure_seconds_per_hour: 80,
    episodes_per_hour: 90,
  },
  relative_exposure_score: 80,
  exposure_band: 'ABOVE_TYPICAL',
  exposure_band_version: 'exposure-bands-v1',
}

const scores = { '7_days': score, '15_days': score, '30_days': score }
const regimes = { version: 'regime-labels-v1', labels: [{ id: 0, kind: 'field_hitch_work' }, { id: 1, kind: 'field_pto_variable' }, { id: 2, kind: 'road_transport' }] }
const provenance = [{ source_kind: 'observed_dataset_replay', dataset_split: 'validation', source_reference: 'doi:10.5281/zenodo.14619787#file=fendt314-stress-1s.csv.gz' }]
const episodeId = 'a1b2c3d4e5f6a7b8c9d0'
const episode = {
  id: episodeId, mission_index: 277, started_at_utc: '2024-06-03T09:00:00+00:00', ended_at_utc: '2024-06-03T09:01:00+00:00', alerted_seconds: 60, physical_exposure_seconds: 12, conditions: ['lugging'], operational_regimes: [1], maximum_contextual_rarity_score: 0.62, contextual_reasons: [{ feature: 'rpm_change_1s__mean', robust_deviation: 11.8 }],
}
const agendaItems = [
  { id: 'engine', component: 'Motor', check: 'Verificar vazamentos, ruídos e registros de falha do motor.', conditions: ['lugging'], episode_ids: [episodeId] },
  { id: 'clutch_transmission', component: 'Embreagem e transmissão', check: 'Verificar patinação da embreagem e trocas de marcha.', conditions: ['lugging'], episode_ids: [episodeId] },
]
const inspectionAgenda = { version: 'inspection-checklist-v1', validation_status: 'engineering_hypothesis', items: agendaItems }
const tractorOverviewFixture = tractorOverviewSchema.parse({ evidence_role: 'operational_output_only', fleet, tractor, as_of_utc: score.as_of_utc, scores, previous_30_day_score: 40, trend_30_day: 10, confidence: 'HIGH', observed_hours: 3.5, episodes_last_30_days: [episode], provenance, regimes, inspection_agenda: inspectionAgenda })

const durations = { lugging: 12, overload_torque: 0, loaded_high_slip: 0, thermal_under_load: 0, harsh_torque_rise: 0, severe_exposure: 12 }
const samples = Array.from({ length: 60 }, (_, second) => {
  const lugging = second >= 20 && second < 32
  return {
    observed_at_utc: new Date(Date.parse(episode.started_at_utc) + second * 1000).toISOString(),
    window_index: 0,
    engine_rpm: lugging ? 1200 : 1800,
    engine_load_pct: lugging ? 85 : 40,
    actual_engine_torque_pct: lugging ? 70 : 35,
    coolant_temp_c: 82,
    traction_slip_pct: second === 0 ? null : 6,
    torque_rise_1s: second === 0 ? null : 2,
    ground_machine_speed_mps: 1.7,
    conditions: lugging ? ['lugging'] : [],
  }
})
const episodeDetailFixture = episodeDetailSchema.parse({
  evidence_role: 'operational_output_only', fleet, tractor, as_of_utc: score.as_of_utc, episode, regimes,
  condition_seconds: { lugging: 12, overload_torque: 0, loaded_high_slip: 0, thermal_under_load: 0, harsh_torque_rise: 0 },
  windows: [{ window_index: 0, observed_at_utc: episode.started_at_utc, sample_count: 60, physical_durations: durations, decision: { operational_regime: 1, contextual_rarity_score: 0.62, contextual_rarity_threshold: 0.55, physical_eligible: true, physical_reasons: ['lugging'], hybrid_alert: true, contextual_reasons: episode.contextual_reasons } }],
  samples,
  inspection_agenda: inspectionAgenda,
})

const exposureTimelineFixture = exposureTimelineSchema.parse({
  evidence_role: 'operational_output_only', tractor, as_of_utc: score.as_of_utc,
  weeks: [
    { week_start_utc: '2024-05-20T00:00:00+00:00', status: 'OK', observed_hours: 2, active_days: 1, physical_exposure_seconds: 20, physical_exposure_seconds_per_hour: 10, alert_windows: 0, episode_count: 0, conditions: [] },
    { week_start_utc: '2024-05-27T00:00:00+00:00', status: 'NO_DATA', observed_hours: 0, active_days: 0, physical_exposure_seconds: 0, physical_exposure_seconds_per_hour: null, alert_windows: 0, episode_count: 0, conditions: [] },
    { week_start_utc: '2024-06-03T00:00:00+00:00', status: 'OK', observed_hours: 1.5, active_days: 1, physical_exposure_seconds: 12, physical_exposure_seconds_per_hour: 8, alert_windows: 1, episode_count: 1, conditions: ['lugging'] },
  ],
})

const caseBase = {
  evidence_role: 'operational_output_only',
  id: '44444444-4444-4444-8444-444444444444',
  tractor_id: tractor.id,
  version: 2,
  assignee: 'Ana',
  due_date: null,
  evidence_as_of_utc: score.as_of_utc,
  evidence_sha256: 'c'.repeat(64),
  result: null,
  result_notes: null,
  created_at_utc: '2024-06-03T10:05:00+00:00',
  updated_at_utc: '2024-06-03T10:06:00+00:00',
  started_at_utc: '2024-06-03T10:06:00+00:00',
  completed_at_utc: null,
  cancelled_at_utc: null,
  findings: null,
}
const snapshotBase = { evidence_as_of_utc: score.as_of_utc, model_version: 'fendt314-hybrid-v2.0.1', interpretation_limit: 'Preventive review only.' }

const inProgressCaseFixture = inspectionCaseSchema.parse({
  ...caseBase,
  status: 'IN_PROGRESS',
  snapshot_schema_version: 'inspection-evidence-v2',
  evidence_snapshot: { ...snapshotBase, schema_version: 'inspection-evidence-v2', inspection_agenda: inspectionAgenda },
})

const completedCaseFixture = inspectionCaseSchema.parse({
  ...caseBase,
  status: 'COMPLETED',
  version: 3,
  result: 'MONITOR',
  result_notes: 'Acompanhar na próxima revisão.',
  completed_at_utc: '2024-06-03T11:00:00+00:00',
  snapshot_schema_version: 'inspection-evidence-v2',
  evidence_snapshot: { ...snapshotBase, schema_version: 'inspection-evidence-v2', inspection_agenda: inspectionAgenda },
  findings: [
    { item_id: 'engine', status: 'OK', notes: null },
    { item_id: 'clutch_transmission', status: 'ATTENTION', notes: 'Embreagem com folga no pedal.' },
  ],
})

const legacyCaseFixture = inspectionCaseSchema.parse({
  ...caseBase,
  status: 'IN_PROGRESS',
  snapshot_schema_version: 'inspection-evidence-v1',
  evidence_snapshot: { ...snapshotBase, schema_version: 'inspection-evidence-v1' },
})

export {
  completedCaseFixture,
  episodeDetailFixture,
  episodeId,
  exposureTimelineFixture,
  inProgressCaseFixture,
  legacyCaseFixture,
  tractorOverviewFixture,
}
