import type { ZodType } from 'zod'
import {
  createFleetRequestSchema,
  createInspectionCaseRequestSchema,
  fleetOverviewSchema,
  fleetRegistrationSchema,
  portfolioSchema,
  replayProgressSchema,
  readinessSchema,
  telemetryPeriodsSchema,
  tractorOverviewSchema,
  inspectionCaseSchema,
  inspectionCasesSchema,
  updateInspectionCaseRequestSchema,
  type CreateFleetRequest,
  type FleetOverview,
  type FleetRegistration,
  type CreateInspectionCaseRequest,
  type InspectionCase,
  type InspectionCases,
  type Portfolio,
  type ReplayProgress,
  type TractorOverview,
  type TelemetryPeriods,
  type UpdateInspectionCaseRequest,
} from './api-contracts'

type ApiErrorKind = 'network' | 'http' | 'invalid_response'

class ApiHttpError extends Error {
  readonly kind: ApiErrorKind
  readonly status: number | null
  readonly detail: string | null
  readonly code: string | null

  constructor(kind: ApiErrorKind, message: string, status: number | null = null, detail: string | null = null, code: string | null = null) {
    super(message)
    this.name = 'ApiHttpError'
    this.kind = kind
    this.status = status
    this.detail = detail
    this.code = code
  }
}

function safeDetail(value: unknown): string | null {
  if (typeof value === 'string') return value
  if (value !== null && typeof value === 'object' && 'detail' in value && typeof value.detail === 'string') return value.detail
  return null
}

function safeCode(value: unknown): string | null {
  if (value !== null && typeof value === 'object' && 'code' in value && typeof value.code === 'string') return value.code
  return null
}

async function requestJson<T>(
  path: string,
  schema: ZodType<T>,
  signal: AbortSignal,
  init?: RequestInit,
): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api${path}`, { ...init, signal })
  } catch (error: unknown) {
    if (signal.aborted) throw error
    const message = error instanceof Error ? error.message : 'A conexão local não respondeu.'
    throw new ApiHttpError('network', 'Não foi possível alcançar a API local.', null, message)
  }

  let body: unknown
  try {
    body = await response.json()
  } catch (error: unknown) {
    if (error instanceof Error) {
      throw new ApiHttpError('invalid_response', 'A API retornou uma resposta que não pôde ser lida.', response.status, error.message)
    }
    throw new ApiHttpError('invalid_response', 'A API retornou uma resposta que não pôde ser lida.', response.status)
  }

  if (!response.ok) {
    throw new ApiHttpError('http', `A API respondeu com status ${response.status}.`, response.status, safeDetail(body), safeCode(body))
  }

  const parsed = schema.safeParse(body)
  if (!parsed.success) {
    throw new ApiHttpError('invalid_response', 'A resposta da API não corresponde ao contrato local.', response.status, parsed.error.issues[0]?.message ?? null)
  }
  return parsed.data
}

function getPortfolio(signal: AbortSignal): Promise<Portfolio> {
  return requestJson('/v1/portfolio/inspection-priorities', portfolioSchema, signal)
}

function getDemoReplayProgress(signal: AbortSignal): Promise<ReplayProgress> {
  return requestJson('/v1/demo/replay-progress', replayProgressSchema, signal)
}

function getFleetOverview(fleetId: string, signal: AbortSignal): Promise<FleetOverview> {
  return requestJson(`/v1/fleets/${encodeURIComponent(fleetId)}/overview`, fleetOverviewSchema, signal)
}

function getTractorOverview(tractorId: string, signal: AbortSignal): Promise<TractorOverview> {
  return requestJson(`/v1/tractors/${encodeURIComponent(tractorId)}/overview`, tractorOverviewSchema, signal)
}

function getReadiness(signal: AbortSignal) {
  return requestJson('/health/ready', readinessSchema, signal)
}

function getTelemetryPeriods(tractorId: string, signal: AbortSignal): Promise<TelemetryPeriods> {
  return requestJson(`/v1/tractors/${encodeURIComponent(tractorId)}/telemetry-periods`, telemetryPeriodsSchema, signal)
}

function getInspectionCases(tractorId: string, signal: AbortSignal): Promise<InspectionCases> {
  return requestJson(`/v1/tractors/${encodeURIComponent(tractorId)}/inspection-cases`, inspectionCasesSchema, signal)
}

function createInspectionCase(tractorId: string, payload: CreateInspectionCaseRequest, signal: AbortSignal): Promise<InspectionCase> {
  return requestJson(`/v1/tractors/${encodeURIComponent(tractorId)}/inspection-cases`, inspectionCaseSchema, signal, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(createInspectionCaseRequestSchema.parse(payload)),
  })
}

function updateInspectionCase(caseId: string, payload: UpdateInspectionCaseRequest, signal: AbortSignal): Promise<InspectionCase> {
  return requestJson(`/v1/inspection-cases/${encodeURIComponent(caseId)}`, inspectionCaseSchema, signal, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(updateInspectionCaseRequestSchema.parse(payload)),
  })
}

function createFleet(payload: CreateFleetRequest, signal: AbortSignal): Promise<FleetRegistration> {
  const validatedPayload = createFleetRequestSchema.parse(payload)
  return requestJson('/v1/fleets', fleetRegistrationSchema, signal, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(validatedPayload),
  })
}

export { ApiHttpError, createFleet, createInspectionCase, getDemoReplayProgress, getFleetOverview, getInspectionCases, getPortfolio, getReadiness, getTelemetryPeriods, getTractorOverview, requestJson, updateInspectionCase }
