import { z } from 'zod'

const evidenceRoleSchema = z.literal('operational_output_only')
const timestampSchema = z.string().datetime({ offset: true })
const uuidSchema = z.string().uuid()
const accessRoleSchema = z.enum(['ADMIN', 'INSURER', 'INSPECTOR', 'FLEET_MANAGER'])
const workerIdSchema = z.string().regex(/^[0-9]{1,20}$/)

export const principalSchema = z.object({
  id: uuidSchema,
  worker_id: workerIdSchema,
  role: accessRoleSchema,
  fleet_id: uuidSchema.nullable(),
}).strict()

export const loginRequestSchema = z.object({
  worker_id: workerIdSchema,
  password: z.string().min(1).max(4096),
})

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

const exposureBandSchema = z.enum(['BELOW_TYPICAL', 'TYPICAL', 'ABOVE_TYPICAL'])

const scoreSchema = z.discriminatedUnion('status', [
  scoreBaseSchema.extend({
    status: z.literal('OK'),
    physical_exposure_seconds_per_hour: z.number().nonnegative(),
    alert_exposure_seconds_per_hour: z.number().nonnegative(),
    episodes_per_hour: z.number().nonnegative(),
    component_percentiles: componentPercentilesSchema,
    relative_exposure_score: z.number().min(0).max(100),
    exposure_band: exposureBandSchema,
    exposure_band_version: z.literal('exposure-bands-v1'),
  }),
  scoreBaseSchema.extend({
    status: z.literal('NO_DATA'),
    physical_exposure_seconds_per_hour: z.null(),
    alert_exposure_seconds_per_hour: z.null(),
    episodes_per_hour: z.null(),
    component_percentiles: z.object({}).strict(),
    relative_exposure_score: z.null(),
    exposure_band: z.null(),
    exposure_band_version: z.literal('exposure-bands-v1'),
  }),
])

const regimeKindSchema = z.enum(['field_hitch_work', 'field_pto_variable', 'road_transport'])

const regimesSchema = z.object({
  version: z.literal('regime-labels-v1'),
  labels: z.array(z.object({ id: z.number().int().nonnegative(), kind: regimeKindSchema })),
})

const conditionSchema = z.enum(['lugging', 'overload_torque', 'loaded_high_slip', 'thermal_under_load', 'harsh_torque_rise'])

const agendaItemSchema = z.object({
  id: z.string().min(1).max(64),
  component: z.string().min(1),
  check: z.string().min(1),
  conditions: z.array(conditionSchema).min(1),
  episode_ids: z.array(z.string().min(1)),
})

const inspectionAgendaSchema = z.object({
  version: z.literal('inspection-checklist-v1'),
  validation_status: z.literal('engineering_hypothesis'),
  items: z.array(agendaItemSchema),
})

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
  source_kind: z.enum(['observed_dataset_replay', 'simulated_csv', 'operational_csv']),
  dataset_split: z.enum(['train', 'validation', 'operational']),
  source_reference: z.string().min(1).max(512),
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
  regimes: regimesSchema,
  inspection_agenda: inspectionAgendaSchema,
  previous_30_days: scoreSchema.nullable().optional(),
  reference_30_day_medians: z.object({
    physical_exposure_seconds_per_hour: z.number().nonnegative().optional(),
    alert_exposure_seconds_per_hour: z.number().nonnegative().optional(),
    episodes_per_hour: z.number().nonnegative().optional(),
  }).optional(),
  workflow: z.object({
    active_case: z.object({ id: uuidSchema, status: z.enum(['OPEN', 'IN_PROGRESS']) }).nullable(),
    last_completed_case: z.object({ id: uuidSchema, evidence_as_of_utc: timestampSchema, completed_at_utc: timestampSchema, result: z.enum(['NO_ACTION', 'MONITOR', 'MAINTENANCE_RECOMMENDED']) }).nullable(),
    new_episode_ids: z.array(z.string()),
    can_open_case: z.boolean(),
  }).nullable().optional(),
})

const conditionDurationsSchema = z.object({
  lugging: z.number().min(0).max(60),
  overload_torque: z.number().min(0).max(60),
  loaded_high_slip: z.number().min(0).max(60),
  thermal_under_load: z.number().min(0).max(60),
  harsh_torque_rise: z.number().min(0).max(60),
  severe_exposure: z.number().min(0).max(60),
})

const nullableSignal = z.number().nullable()

const episodeSampleSchema = z.object({
  observed_at_utc: timestampSchema,
  window_index: z.number().int().nonnegative(),
  engine_rpm: nullableSignal,
  engine_load_pct: nullableSignal,
  actual_engine_torque_pct: nullableSignal,
  coolant_temp_c: nullableSignal,
  traction_slip_pct: nullableSignal,
  torque_rise_1s: nullableSignal,
  ground_machine_speed_mps: nullableSignal,
  conditions: z.array(conditionSchema),
})

export const episodeDetailSchema = z.object({
  evidence_role: evidenceRoleSchema,
  fleet: fleetSchema,
  tractor: tractorSchema,
  as_of_utc: timestampSchema,
  episode: episodeSchema,
  provenance: z.array(provenanceSchema).optional(),
  regimes: regimesSchema,
  condition_seconds: z.record(conditionSchema, z.number().nonnegative()),
  windows: z.array(z.object({
    window_index: z.number().int().nonnegative(),
    observed_at_utc: timestampSchema,
    sample_count: z.number().int().positive(),
    physical_durations: conditionDurationsSchema,
    decision: z.object({
      operational_regime: z.number().int().nonnegative(),
      contextual_rarity_score: z.number(),
      contextual_rarity_threshold: z.number(),
      physical_eligible: z.boolean(),
      physical_reasons: z.array(conditionSchema),
      hybrid_alert: z.boolean(),
      contextual_reasons: z.array(contextualReasonSchema),
    }),
  })).min(1),
  samples: z.array(episodeSampleSchema),
  inspection_agenda: inspectionAgendaSchema,
})

export const exposureTimelineSchema = z.object({
  evidence_role: evidenceRoleSchema,
  tractor: tractorSchema,
  as_of_utc: timestampSchema,
  weeks: z.array(z.object({
    week_start_utc: timestampSchema,
    status: z.enum(['OK', 'NO_DATA']),
    observed_hours: z.number().nonnegative(),
    active_days: z.number().int().min(0).max(7),
    physical_exposure_seconds: z.number().nonnegative(),
    physical_exposure_seconds_per_hour: z.number().nonnegative().nullable(),
    alert_windows: z.number().int().nonnegative(),
    episode_count: z.number().int().nonnegative(),
    conditions: z.array(conditionSchema),
    condition_seconds: z.record(conditionSchema, z.number().nonnegative()).optional(),
    condition_episode_counts: z.record(conditionSchema, z.number().int().nonnegative()).optional(),
  })),
})

const inspectionCaseStatusSchema = z.enum(['OPEN', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED'])
const inspectionCaseResultSchema = z.enum(['NO_ACTION', 'MONITOR', 'MAINTENANCE_RECOMMENDED'])
const findingStatusSchema = z.enum(['OK', 'ATTENTION', 'PROBLEM', 'NOT_CHECKED'])
const snapshotVersionSchema = z.enum(['inspection-evidence-v1', 'inspection-evidence-v2'])

const findingSchema = z.object({
  item_id: z.string().min(1).max(64),
  status: findingStatusSchema,
  notes: z.string().min(1).max(1000).nullable(),
})

export const inspectionCaseSchema = z.object({
  evidence_role: evidenceRoleSchema,
  id: uuidSchema,
  tractor_id: uuidSchema,
  status: inspectionCaseStatusSchema,
  version: z.number().int().positive(),
  assignee: z.string().min(1).max(120).nullable(),
  due_date: z.string().date().nullable(),
  evidence_as_of_utc: timestampSchema,
  snapshot_schema_version: snapshotVersionSchema,
  evidence_snapshot: z.object({
    schema_version: snapshotVersionSchema,
    evidence_as_of_utc: timestampSchema,
    model_version: z.literal('fendt314-hybrid-v2.0.1'),
    interpretation_limit: z.string().min(1),
    inspection_agenda: inspectionAgendaSchema.optional(),
    tractor: z.object({ id: uuidSchema, external_id: z.string(), display_name: z.string().nullable(), model_name: z.string() }).optional(),
    fleet: z.object({ id: uuidSchema, name: z.string() }).optional(),
    episodes_last_30_days: z.array(episodeSchema.pick({ id: true, mission_index: true, started_at_utc: true, ended_at_utc: true, physical_exposure_seconds: true, conditions: true, operational_regimes: true })).optional(),
    provenance: z.array(provenanceSchema).optional(),
  }).passthrough(),
  evidence_sha256: z.string().regex(/^[a-f0-9]{64}$/),
  result: inspectionCaseResultSchema.nullable(),
  result_notes: z.string().min(1).max(4000).nullable(),
  created_at_utc: timestampSchema,
  updated_at_utc: timestampSchema,
  started_at_utc: timestampSchema.nullable(),
  completed_at_utc: timestampSchema.nullable(),
  cancelled_at_utc: timestampSchema.nullable(),
  findings: z.array(findingSchema).nullable(),
}).superRefine((value, context) => {
  if (value.snapshot_schema_version === 'inspection-evidence-v2' && value.evidence_snapshot.inspection_agenda === undefined) {
    context.addIssue({ code: 'custom', path: ['evidence_snapshot', 'inspection_agenda'], message: 'v2 snapshots must carry the inspection agenda' })
  }
})

export const inspectionCasesSchema = z.object({
  evidence_role: evidenceRoleSchema,
  cases: z.array(inspectionCaseSchema),
})

export const inspectorsSchema = z.object({
  inspectors: z.array(z.object({ id: uuidSchema, worker_id: workerIdSchema })),
})

const caseEventBaseSchema = z.object({
  id: uuidSchema,
  case_id: uuidSchema,
  actor_user_id: uuidSchema,
  actor_worker_id: workerIdSchema,
  actor_role: principalSchema.shape.role,
  occurred_at_utc: timestampSchema,
  prior_status: inspectionCaseStatusSchema.nullable(),
  new_status: inspectionCaseStatusSchema,
  case_version: z.number().int().positive(),
})

const caseEventSchema = z.discriminatedUnion('action', [
  caseEventBaseSchema.extend({ action: z.literal('CREATE'), details: z.object({ assignee: z.string().nullable(), due_date: z.string().date().nullable() }) }),
  caseEventBaseSchema.extend({ action: z.literal('UPDATE'), details: z.object({
    changes: z.object({
      assignee: z.object({ from: z.string().nullable(), to: z.string().nullable() }).optional(),
      due_date: z.object({ from: z.string().date().nullable(), to: z.string().date().nullable() }).optional(),
    }),
  }) }),
  caseEventBaseSchema.extend({ action: z.literal('START'), details: z.object({}) }),
  caseEventBaseSchema.extend({ action: z.literal('SAVE_DRAFT'), details: z.object({}).passthrough() }),
  caseEventBaseSchema.extend({ action: z.literal('COMPLETE'), details: z.object({
    result: inspectionCaseResultSchema,
    finding_status_counts: z.object({ OK: z.number().int().nonnegative(), ATTENTION: z.number().int().nonnegative(), PROBLEM: z.number().int().nonnegative(), NOT_CHECKED: z.number().int().nonnegative() }),
  }) }),
  caseEventBaseSchema.extend({ action: z.literal('CANCEL'), details: z.object({}) }),
])

export const inspectionCaseEventsSchema = z.object({ case_id: uuidSchema, events: z.array(caseEventSchema) })

const adminUserSchema = z.object({
  id: uuidSchema,
  worker_id: workerIdSchema,
  role: accessRoleSchema,
  fleet_id: uuidSchema.nullable(),
  active: z.boolean(),
  created_at_utc: timestampSchema,
})

export const adminUsersSchema = z.object({ users: z.array(adminUserSchema) })
export const adminCatalogSchema = z.object({ fleets: z.array(z.object({
  id: uuidSchema,
  name: z.string().min(1),
  tractors: z.array(z.object({
    id: uuidSchema,
    external_id: z.string().min(1),
    display_name: z.string().nullable(),
    model_name: z.string().min(1),
  })),
})) })
export const createAdminUserRequestSchema = z.object({ worker_id: workerIdSchema, role: accessRoleSchema, fleet_id: uuidSchema.nullable() })
export const updateAdminUserRequestSchema = z.object({ role: accessRoleSchema, fleet_id: uuidSchema.nullable(), active: z.boolean() })
export const createdAdminUserSchema = z.object({ user: adminUserSchema, temporary_password: z.string().min(1) })
export const updatedAdminUserSchema = z.object({ user: adminUserSchema })
export const resetAdminPasswordSchema = z.object({ temporary_password: z.string().min(1) })

const adminUserEventBaseSchema = z.object({
  id: uuidSchema,
  target_user_id: uuidSchema,
  target_worker_id: workerIdSchema,
  actor_user_id: uuidSchema,
  actor_worker_id: workerIdSchema,
  occurred_at_utc: timestampSchema,
})

const adminUserEventSchema = z.discriminatedUnion('action', [
  adminUserEventBaseSchema.extend({ action: z.literal('CREATE'), details: z.object({ role: accessRoleSchema, fleet_id: uuidSchema.nullable(), active: z.boolean() }) }),
  adminUserEventBaseSchema.extend({ action: z.literal('UPDATE'), details: z.object({ changes: z.object({
    role: z.object({ from: accessRoleSchema, to: accessRoleSchema }).optional(),
    fleet_id: z.object({ from: uuidSchema.nullable(), to: uuidSchema.nullable() }).optional(),
    active: z.object({ from: z.boolean(), to: z.boolean() }).optional(),
  }) }) }),
  adminUserEventBaseSchema.extend({ action: z.literal('RESET_PASSWORD'), details: z.object({}) }),
])

export const adminUserEventsSchema = z.object({ events: z.array(adminUserEventSchema) })

export const createInspectionCaseRequestSchema = z.object({
  assignee: workerIdSchema.nullable(),
  due_date: z.string().date().nullable(),
})

export const updateInspectionCaseRequestSchema = z.object({
  version: z.number().int().positive(),
  action: z.enum(['UPDATE', 'START', 'SAVE_DRAFT', 'COMPLETE', 'CANCEL']),
  assignee: workerIdSchema.nullable().optional(),
  due_date: z.string().date().nullable().optional(),
  result: inspectionCaseResultSchema.nullable().optional(),
  result_notes: z.string().max(4000).nullable().optional(),
  findings: z.array(z.object({
    item_id: z.string().min(1).max(64),
    status: findingStatusSchema,
    notes: z.string().max(1000).nullable(),
  })).nullable().optional(),
})

export type TractorOverview = z.infer<typeof tractorOverviewSchema>
export type ExposureBand = z.infer<typeof exposureBandSchema>
export type Regimes = z.infer<typeof regimesSchema>
export type Condition = z.infer<typeof conditionSchema>
export type InspectionAgenda = z.infer<typeof inspectionAgendaSchema>
export type InspectionAgendaItem = z.infer<typeof agendaItemSchema>
export type InspectionEpisode = z.infer<typeof episodeSchema>
export type EpisodeDetail = z.infer<typeof episodeDetailSchema>
export type EpisodeSample = z.infer<typeof episodeSampleSchema>
export type ExposureTimeline = z.infer<typeof exposureTimelineSchema>
export type FindingStatus = z.infer<typeof findingStatusSchema>
export type InspectionCase = z.infer<typeof inspectionCaseSchema>
export type InspectionCases = z.infer<typeof inspectionCasesSchema>
export type Inspectors = z.infer<typeof inspectorsSchema>
export type InspectionCaseEvent = z.infer<typeof caseEventSchema>
export type InspectionCaseEvents = z.infer<typeof inspectionCaseEventsSchema>
export type CreateInspectionCaseRequest = z.infer<typeof createInspectionCaseRequestSchema>
export type UpdateInspectionCaseRequest = z.infer<typeof updateInspectionCaseRequestSchema>
export type Principal = z.infer<typeof principalSchema>
export type LoginRequest = z.infer<typeof loginRequestSchema>
export type AdminUser = z.infer<typeof adminUserSchema>
export type AdminUsers = z.infer<typeof adminUsersSchema>
export type AdminCatalog = z.infer<typeof adminCatalogSchema>
export type AdminUserEvent = z.infer<typeof adminUserEventSchema>
export type AdminUserEvents = z.infer<typeof adminUserEventsSchema>
export type CreateAdminUserRequest = z.infer<typeof createAdminUserRequestSchema>
export type UpdateAdminUserRequest = z.infer<typeof updateAdminUserRequestSchema>
export type CreatedAdminUser = z.infer<typeof createdAdminUserSchema>
export type UpdatedAdminUser = z.infer<typeof updatedAdminUserSchema>
export type ResetAdminPassword = z.infer<typeof resetAdminPasswordSchema>
