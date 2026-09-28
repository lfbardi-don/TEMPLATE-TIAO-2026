import { z } from 'zod'
import { requestJson, ApiHttpError } from '../../lib/api-client'

const sourceKind = z.enum(['observed_dataset_replay', 'simulated_csv', 'operational_csv'])
const machineSchema = z.object({
  id: z.string(), fleet_id: z.string(), external_id: z.string(), display_name: z.string().nullable(), model_name: z.string(),
  source_kind: sourceKind.nullable(), latest_observed_at_utc: z.string().nullable(),
  import_count: z.number(), window_count: z.number(), alert_count: z.number(),
})
const catalogSchema = z.object({ fleets: z.array(z.object({ id: z.string(), name: z.string(), tractors: z.array(machineSchema) })) })
const previewSchema = z.object({
  sample_count: z.number(), mission_count: z.number(), started_at_utc: z.string(), ended_at_utc: z.string(),
  ready_window_count: z.number(), skipped_window_count: z.number().nullable(), source_kind: sourceKind, reference_label: z.string(),
})
const importedSchema = previewSchema.extend({
  id: z.string(), duplicate: z.boolean(), window_count: z.number(), physical_candidate_count: z.number(), alert_count: z.number(), model_version: z.string(),
})
const importRecordSchema = importedSchema.extend({ file_name: z.string(), created_at_utc: z.string(), imported_by_worker_id: z.string().nullable() })
const scenariosSchema = z.object({ scenarios: z.array(z.object({
  id: z.string(), label: z.string(), fleet_name: z.string(), machine_name: z.string(), file_name: z.string(), description: z.string(), download_url: z.string(), followup_for: z.string().nullable(),
})) })
const sampleSchema = z.object({
  observed_at_utc: z.string(), engine_rpm: z.number().nullable(), actual_engine_torque_pct: z.number().nullable(),
  engine_load_pct: z.number().nullable(), coolant_temp_c: z.number().nullable(), ground_machine_speed_mps: z.number().nullable(),
  rear_pto_rpm: z.number().nullable(), traction_slip_pct: z.number().nullable(),
})
const chartSchema = z.object({
  import_id: z.string().nullable(), mission_index: z.number().nullable(), source_kind: sourceKind.nullable(), total_samples: z.number(), samples: z.array(sampleSchema),
  periods: z.array(z.object({ import_id: z.string(), mission_index: z.number(), started_at_utc: z.string(), ended_at_utc: z.string(), source_kind: sourceKind })),
})
type Catalog = z.infer<typeof catalogSchema>
type CatalogMachine = z.infer<typeof machineSchema>
type ImportPreview = z.infer<typeof previewSchema>
type ImportResult = z.infer<typeof importedSchema>
type CsvScenario = z.infer<typeof scenariosSchema>['scenarios'][number]
type TelemetrySample = z.infer<typeof sampleSchema>
type CsvUpload = { file_name: string; csv_text: string; source_kind: 'simulated_csv' | 'operational_csv' }

function post<T>(path: string, schema: z.ZodType<T>, payload: unknown, signal: AbortSignal): Promise<T> {
  return requestJson(path, schema, signal, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
}
const getCatalog = (signal: AbortSignal) => requestJson('/v1/catalog', catalogSchema, signal)
const getCsvScenarios = (signal: AbortSignal) => requestJson('/v1/demo/csv-scenarios', scenariosSchema, signal)
const getImports = (id: string, signal: AbortSignal) => requestJson(`/v1/tractors/${encodeURIComponent(id)}/imports`, z.object({ imports: z.array(importRecordSchema) }), signal)
const previewCsv = (id: string, payload: CsvUpload, signal: AbortSignal) => post(`/v1/tractors/${encodeURIComponent(id)}/imports/preview`, previewSchema, payload, signal)
const importCsv = (id: string, payload: CsvUpload, signal: AbortSignal) => post(`/v1/tractors/${encodeURIComponent(id)}/imports`, importedSchema, payload, signal)
const registrationSchema = z.object({ fleet: z.object({ id: z.string() }), tractors: z.array(z.object({ id: z.string() })) })
const createFleet = (name: string, tractor: { external_id: string; display_name: string | null }, signal: AbortSignal) => post('/v1/fleets', registrationSchema, { name, tractors: [tractor] }, signal)
const addTractor = (fleetId: string, tractor: { external_id: string; display_name: string | null }, signal: AbortSignal) => post(`/v1/fleets/${encodeURIComponent(fleetId)}/tractors`, z.object({ id: z.string() }), tractor, signal)

function getTelemetryChart(id: string, importId: string, mission: string, signal: AbortSignal) {
  const query = new URLSearchParams({ limit: '300' })
  if (importId) query.set('import_id', importId)
  if (mission) query.set('mission_index', mission)
  return requestJson(`/v1/tractors/${encodeURIComponent(id)}/telemetry-chart?${query}`, chartSchema, signal)
}

function intakeError(error: unknown): string {
  if (error instanceof ApiHttpError) {
    if (error.status === 403) return 'Seu cargo não permite esta ação.'
    if (error.status === 409) return error.detail && !error.detail.includes('persistent state') ? error.detail : 'Já existe um cadastro ou uma importação com esses dados. Confira o identificador e o período.'
    if (error.status === 413) return 'O arquivo excede o tamanho permitido. Divida os dados em períodos menores.'
    if (error.status === 422 && error.detail) return error.detail
    if (error.status === 401) return 'Sua sessão expirou. Entre novamente.'
    return error.message
  }
  return 'Não foi possível concluir. Tente novamente.'
}

function sourceLabel(source: CatalogMachine['source_kind']) {
  if (source === 'simulated_csv') return 'Dados simulados'
  if (source === 'observed_dataset_replay') return 'Telemetria de referência'
  if (source === 'operational_csv') return 'Telemetria operacional'
  return 'Sem dados'
}

export { getCatalog, getCsvScenarios, getImports, previewCsv, importCsv, createFleet, addTractor, getTelemetryChart, intakeError, sourceLabel }
export type { Catalog, CatalogMachine, CsvUpload, ImportPreview, ImportResult, CsvScenario, TelemetrySample }
