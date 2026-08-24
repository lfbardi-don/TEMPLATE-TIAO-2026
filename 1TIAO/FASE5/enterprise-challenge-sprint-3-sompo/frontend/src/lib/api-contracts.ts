import { z } from 'zod'

const evidenceRoleSchema = z.literal('operational_output_only')
const timestampSchema = z.string().datetime({ offset: true })
const uuidSchema = z.string().uuid()

const fleetSchema = z.object({
  id: uuidSchema,
  name: z.string().min(1).max(120),
  created_at_utc: timestampSchema,
})

const tractorSchema = z.object({
  id: uuidSchema,
  fleet_id: uuidSchema,
  external_id: z.string().min(1).max(128),
  display_name: z.string().min(1).max(120).nullable(),
  model_name: z.literal('Fendt 314'),
  created_at_utc: timestampSchema,
})

const scoreBaseSchema = z.object({
  as_of_utc: timestampSchema,
  observed_hours: z.number().nonnegative(),
  active_days: z.number().int().nonnegative(),
  calendar_coverage: z.number().min(0).max(1),
  confidence: z.enum(['HIGH', 'MEDIUM', 'LOW']),
  episode_count: z.number().int().nonnegative(),
  represented_conditions: z.array(z.string()),
  predominant_regimes: z.array(z.number().int()),
})

const componentPercentilesSchema = z.object({
  physical_exposure_seconds_per_hour: z.number().min(0).max(100),
  alert_exposure_seconds_per_hour: z.number().min(0).max(100),
  episodes_per_hour: z.number().min(0).max(100),
}).strict()

const scoreSchema = z.discriminatedUnion('status', [
  scoreBaseSchema.extend({
    status: z.literal('OK'),
    physical_exposure_seconds_per_hour: z.number().nonnegative(),
    alert_exposure_seconds_per_hour: z.number().nonnegative(),
    episodes_per_hour: z.number().nonnegative(),
    component_percentiles: componentPercentilesSchema,
    relative_exposure_score: z.number().min(0).max(100),
  }),
  scoreBaseSchema.extend({
    status: z.literal('NO_DATA'),
    physical_exposure_seconds_per_hour: z.null(),
    alert_exposure_seconds_per_hour: z.null(),
    episodes_per_hour: z.null(),
    component_percentiles: z.object({}).strict(),
    relative_exposure_score: z.null(),
  }),
])

const scoresSchema = z.object({
  '7_days': scoreSchema,
  '15_days': scoreSchema,
  '30_days': scoreSchema,
})

const contextualReasonSchema = z.record(z.string(), z.union([z.string(), z.number(), z.boolean(), z.null()]))

const episodeSchema = z.object({
  id: z.string().min(1),
  mission_index: z.number().int().nonnegative(),
  started_at_utc: timestampSchema,
  ended_at_utc: timestampSchema,
  alerted_seconds: z.number().nonnegative(),
  physical_exposure_seconds: z.number().nonnegative(),
  conditions: z.array(z.string()),
  operational_regimes: z.array(z.number().int()),
  maximum_contextual_rarity_score: z.number(),
  contextual_reasons: z.array(contextualReasonSchema),
})

const provenanceSchema = z.object({
  source_kind: z.literal('observed_dataset_replay'),
  dataset_split: z.enum(['train', 'validation']),
  source_reference: z.string().min(1).max(512),
})

const prioritySchema = z.object({
  rank: z.number().int().positive().nullable(),
  fleet: fleetSchema,
  tractor: tractorSchema,
  as_of_utc: timestampSchema,
  scores: scoresSchema,
  previous_30_day_score: z.number().min(0).max(100).nullable(),
  trend_30_day: z.number().min(-100).max(100).nullable(),
  confidence: z.enum(['HIGH', 'MEDIUM', 'LOW']),
  observed_hours: z.number().nonnegative(),
  episode_count: z.number().int().nonnegative(),
  predominant_conditions: z.array(z.string()),
  episodes_last_30_days: z.array(episodeSchema),
  provenance: z.array(provenanceSchema),
})

const registrationTractorSchema = tractorSchema

export const fleetRegistrationSchema = z.object({
  evidence_role: evidenceRoleSchema,
  fleet: fleetSchema,
  tractors: z.array(registrationTractorSchema).min(1),
})

export const portfolioSchema = z.object({
  evidence_role: evidenceRoleSchema,
  as_of_utc: timestampSchema,
  priorities: z.array(prioritySchema),
})

export const fleetOverviewSchema = z.object({
  evidence_role: evidenceRoleSchema,
  fleet: fleetSchema,
  as_of_utc: timestampSchema,
  totals: z.object({ tractors: z.number().int().nonnegative() }),
  status_counts: z.object({ OK: z.number().int().nonnegative(), NO_DATA: z.number().int().nonnegative() }),
  priorities: z.array(prioritySchema),
})

export const tractorOverviewSchema = z.object({
  evidence_role: evidenceRoleSchema,
  fleet: fleetSchema,
  tractor: tractorSchema,
  as_of_utc: timestampSchema,
  scores: scoresSchema,
  previous_30_day_score: z.number().min(0).max(100).nullable(),
  trend_30_day: z.number().min(-100).max(100).nullable(),
  confidence: z.enum(['HIGH', 'MEDIUM', 'LOW']),
  observed_hours: z.number().nonnegative(),
  episodes_last_30_days: z.array(episodeSchema),
  provenance: z.array(provenanceSchema),
})

const telemetryMissionSchema = z.object({
  mission_index: z.number().int().nonnegative(),
  started_at_utc: timestampSchema,
  ended_at_utc: timestampSchema,
  sample_count: z.number().int().positive(),
  observed_duration_seconds: z.number().nonnegative(),
  replay_status: z.literal('ELIGIBLE'),
})

const telemetryImportPeriodSchema = z.object({
  id: uuidSchema,
  dataset_split: z.enum(['train', 'validation']),
  source_format: z.enum(['canonical_csv', 'canonical_csv_gz', 'fendt314_zip']),
  source_file_name: z.string().min(1).max(255),
  source_member: z.string().min(1).nullable(),
  semantic_sha256: z.string().regex(/^[a-f0-9]{64}$/),
  source_sha256: z.string().regex(/^[a-f0-9]{64}$/),
  transform_version: z.enum(['canonical-pass-through-v1', 'fendt314-original-to-1hz-v1']),
  started_at_utc: timestampSchema,
  ended_at_utc: timestampSchema,
  sample_count: z.number().int().positive(),
  mission_count: z.number().int().positive(),
  missions: z.array(telemetryMissionSchema),
})

export const telemetryPeriodsSchema = z.object({
  evidence_role: evidenceRoleSchema,
  tractor: tractorSchema,
  fleet: fleetSchema,
  imports: z.array(telemetryImportPeriodSchema),
})

const inspectionCaseStatusSchema = z.enum(['OPEN', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED'])
const inspectionCaseResultSchema = z.enum(['NO_ACTION', 'MONITOR', 'MAINTENANCE_RECOMMENDED'])

export const inspectionCaseSchema = z.object({
  evidence_role: evidenceRoleSchema,
  id: uuidSchema,
  tractor_id: uuidSchema,
  status: inspectionCaseStatusSchema,
  version: z.number().int().positive(),
  assignee: z.string().min(1).max(120).nullable(),
  due_date: z.string().date().nullable(),
  evidence_as_of_utc: timestampSchema,
  snapshot_schema_version: z.literal('inspection-evidence-v1'),
  evidence_snapshot: z.object({
    schema_version: z.literal('inspection-evidence-v1'),
    evidence_as_of_utc: timestampSchema,
    model_version: z.literal('fendt314-hybrid-v2.0.1'),
    interpretation_limit: z.string().min(1),
  }).passthrough(),
  evidence_sha256: z.string().regex(/^[a-f0-9]{64}$/),
  result: inspectionCaseResultSchema.nullable(),
  result_notes: z.string().min(1).max(4000).nullable(),
  created_at_utc: timestampSchema,
  updated_at_utc: timestampSchema,
  started_at_utc: timestampSchema.nullable(),
  completed_at_utc: timestampSchema.nullable(),
  cancelled_at_utc: timestampSchema.nullable(),
})

export const inspectionCasesSchema = z.object({
  evidence_role: evidenceRoleSchema,
  cases: z.array(inspectionCaseSchema),
})

const recentInferenceSchema = z.object({
  mission_index: z.number().int().nonnegative(),
  window_index: z.number().int().nonnegative(),
  model_version: z.literal('fendt314-hybrid-v2.0.1'),
  hybrid_alert: z.boolean(),
}).strict()

const replayProgressBaseSchema = z.object({
  evidence_role: evidenceRoleSchema,
  tractor_id: uuidSchema,
  telemetry_import_id: uuidSchema,
  dataset_split: z.literal('validation'),
  source_doi: z.literal('10.5281/zenodo.14619787'),
  source_license: z.literal('CC-BY-4.0'),
  semantic_sha256: z.string().regex(/^[a-f0-9]{64}$/),
  total_samples: z.number().int().positive(),
  samples_replayed: z.number().int().nonnegative(),
  ready_windows: z.number().int().nonnegative(),
  created_windows: z.number().int().nonnegative(),
  duplicate_windows: z.number().int().nonnegative(),
  alert_windows: z.number().int().nonnegative(),
  no_data_windows: z.number().int().nonnegative(),
  failures: z.number().int().nonnegative(),
  recent_inferences: z.array(recentInferenceSchema).max(8),
}).strict()

export const replayProgressSchema = z.discriminatedUnion('status', [
  replayProgressBaseSchema.extend({ status: z.literal('waiting'), error_code: z.null() }),
  replayProgressBaseSchema.extend({ status: z.literal('running'), error_code: z.null() }),
  replayProgressBaseSchema.extend({ status: z.literal('complete'), error_code: z.null() }),
  replayProgressBaseSchema.extend({ status: z.literal('failed'), error_code: z.literal('DEMO_REPLAY_FAILED') }),
]).superRefine((progress, context) => {
  if (progress.samples_replayed > progress.total_samples) {
    context.addIssue({ code: 'custom', path: ['samples_replayed'], message: 'samples_replayed cannot exceed total_samples' })
  }
  if (progress.created_windows + progress.duplicate_windows > progress.ready_windows) {
    context.addIssue({ code: 'custom', path: ['created_windows'], message: 'accepted windows cannot exceed ready_windows' })
  }
  if (progress.alert_windows > progress.created_windows) {
    context.addIssue({ code: 'custom', path: ['alert_windows'], message: 'alert_windows cannot exceed created_windows' })
  }
})

export const readinessSchema = z.object({ status: z.enum(['ready', 'not_ready']) })

export const createFleetRequestSchema = z.object({
  name: z.string().min(1).max(120),
  tractors: z.array(z.object({
    external_id: z.string().min(1).max(128),
    display_name: z.string().min(1).max(120).nullable(),
  })).min(1),
})

export const createInspectionCaseRequestSchema = z.object({
  assignee: z.string().min(1).max(120).nullable(),
  due_date: z.string().date().nullable(),
})

export const updateInspectionCaseRequestSchema = z.object({
  version: z.number().int().positive(),
  action: z.enum(['UPDATE', 'START', 'COMPLETE', 'CANCEL']),
  assignee: z.string().min(1).max(120).nullable(),
  due_date: z.string().date().nullable(),
  result: inspectionCaseResultSchema.nullable(),
  result_notes: z.string().max(4000).nullable(),
})

export type FleetRegistration = z.infer<typeof fleetRegistrationSchema>
export type Portfolio = z.infer<typeof portfolioSchema>
export type FleetOverview = z.infer<typeof fleetOverviewSchema>
export type TractorOverview = z.infer<typeof tractorOverviewSchema>
export type Priority = z.infer<typeof prioritySchema>
export type Score = z.infer<typeof scoreSchema>
export type InspectionEpisode = z.infer<typeof episodeSchema>
export type Provenance = z.infer<typeof provenanceSchema>
export type CreateFleetRequest = z.infer<typeof createFleetRequestSchema>
export type TelemetryPeriods = z.infer<typeof telemetryPeriodsSchema>
export type InspectionCase = z.infer<typeof inspectionCaseSchema>
export type InspectionCases = z.infer<typeof inspectionCasesSchema>
export type CreateInspectionCaseRequest = z.infer<typeof createInspectionCaseRequestSchema>
export type UpdateInspectionCaseRequest = z.infer<typeof updateInspectionCaseRequestSchema>
export type ReplayProgress = z.infer<typeof replayProgressSchema>
export type RecentInference = z.infer<typeof recentInferenceSchema>
