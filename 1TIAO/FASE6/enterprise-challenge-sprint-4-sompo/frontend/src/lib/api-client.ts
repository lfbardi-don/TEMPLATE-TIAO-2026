import { z, type ZodType } from 'zod'
import {
  adminCatalogSchema,
  adminUserEventsSchema,
  adminUsersSchema,
  createInspectionCaseRequestSchema,
  createAdminUserRequestSchema,
  createdAdminUserSchema,
  episodeDetailSchema,
  exposureTimelineSchema,
  resetAdminPasswordSchema,
  tractorOverviewSchema,
  inspectionCaseSchema,
  inspectionCaseEventsSchema,
  inspectionCasesSchema,
  inspectorsSchema,
  loginRequestSchema,
  principalSchema,
  updateInspectionCaseRequestSchema,
  updateAdminUserRequestSchema,
  updatedAdminUserSchema,
  type AdminUserEvents,
  type AdminUsers,
  type AdminCatalog,
  type CreateAdminUserRequest,
  type CreatedAdminUser,
  type CreateInspectionCaseRequest,
  type EpisodeDetail,
  type ExposureTimeline,
  type InspectionCase,
  type InspectionCaseEvents,
  type InspectionCases,
  type Inspectors,
  type LoginRequest,
  type Principal,
  type TractorOverview,
  type UpdateInspectionCaseRequest,
  type UpdateAdminUserRequest,
  type UpdatedAdminUser,
  type ResetAdminPassword,
} from './api-contracts'

type ApiErrorKind = 'network' | 'http' | 'invalid_response'

const AUTH_UNAUTHORIZED_EVENT = 'auth:unauthorized'

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
    response = await fetch(`/api${path}`, { credentials: 'same-origin', ...init, signal })
  } catch (error: unknown) {
    if (signal.aborted) throw error
    const message = error instanceof Error ? error.message : 'O serviço não respondeu.'
    throw new ApiHttpError('network', 'Não foi possível conectar ao serviço.', null, message)
  }

  let body: unknown
  try {
    body = response.status === 204 ? null : await response.json()
  } catch (error: unknown) {
    if (!response.ok) {
      body = null
    } else {
      if (error instanceof Error) {
        throw new ApiHttpError('invalid_response', 'Não foi possível ler a resposta do serviço.', response.status, error.message)
      }
      throw new ApiHttpError('invalid_response', 'Não foi possível ler a resposta do serviço.', response.status)
    }
  }

  if (!response.ok) {
    if (response.status === 401 && path !== '/v1/auth/login' && path !== '/v1/auth/me') {
      window.dispatchEvent(new Event(AUTH_UNAUTHORIZED_EVENT))
    }
    throw new ApiHttpError('http', 'Não foi possível concluir a solicitação.', response.status, safeDetail(body), safeCode(body))
  }

  const parsed = schema.safeParse(body)
  if (!parsed.success) {
    throw new ApiHttpError('invalid_response', 'O serviço retornou dados em um formato inesperado.', response.status, parsed.error.issues[0]?.message ?? null)
  }
  return parsed.data
}

function getCurrentUser(signal: AbortSignal): Promise<Principal> {
  return requestJson('/v1/auth/me', principalSchema, signal)
}

function loginUser(payload: LoginRequest, signal: AbortSignal): Promise<Principal> {
  return requestJson('/v1/auth/login', principalSchema, signal, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(loginRequestSchema.parse(payload)),
  })
}

async function logoutUser(signal: AbortSignal): Promise<void> {
  await requestJson('/v1/auth/logout', z.null(), signal, { method: 'POST' })
}

function getTractorOverview(tractorId: string, signal: AbortSignal): Promise<TractorOverview> {
  return requestJson(`/v1/tractors/${encodeURIComponent(tractorId)}/overview`, tractorOverviewSchema, signal)
}

function getEpisodeDetail(tractorId: string, episodeId: string, signal: AbortSignal, asOf?: string): Promise<EpisodeDetail> {
  const query = asOf === undefined ? '' : `?as_of_utc=${encodeURIComponent(asOf)}`
  return requestJson(`/v1/tractors/${encodeURIComponent(tractorId)}/episodes/${encodeURIComponent(episodeId)}${query}`, episodeDetailSchema, signal)
}

function getInspectionCaseEpisode(caseId: string, episodeId: string, signal: AbortSignal): Promise<EpisodeDetail> {
  return requestJson(`/v1/inspection-cases/${encodeURIComponent(caseId)}/episodes/${encodeURIComponent(episodeId)}`, episodeDetailSchema, signal)
}

function getInspectionCase(caseId: string, signal: AbortSignal): Promise<InspectionCase> {
  return requestJson(`/v1/inspection-cases/${encodeURIComponent(caseId)}`, inspectionCaseSchema, signal)
}

function getAllInspectionCases(signal: AbortSignal): Promise<InspectionCases> {
  return requestJson('/v1/inspection-cases', inspectionCasesSchema, signal)
}

function getExposureTimeline(tractorId: string, signal: AbortSignal, asOf?: string): Promise<ExposureTimeline> {
  const query = asOf === undefined ? '' : `?as_of_utc=${encodeURIComponent(asOf)}`
  return requestJson(`/v1/tractors/${encodeURIComponent(tractorId)}/exposure-timeline${query}`, exposureTimelineSchema, signal)
}

function getInspectionCases(tractorId: string, signal: AbortSignal): Promise<InspectionCases> {
  return requestJson(`/v1/tractors/${encodeURIComponent(tractorId)}/inspection-cases`, inspectionCasesSchema, signal)
}

function getInspectors(signal: AbortSignal): Promise<Inspectors> {
  return requestJson('/v1/inspectors', inspectorsSchema, signal)
}

function getInspectionCaseEvents(caseId: string, signal: AbortSignal): Promise<InspectionCaseEvents> {
  return requestJson(`/v1/inspection-cases/${encodeURIComponent(caseId)}/events`, inspectionCaseEventsSchema, signal)
}

function getAdminUsers(signal: AbortSignal): Promise<AdminUsers> {
  return requestJson('/v1/admin/users', adminUsersSchema, signal)
}

function getAdminCatalog(signal: AbortSignal): Promise<AdminCatalog> {
  return requestJson('/v1/admin/catalog', adminCatalogSchema, signal)
}

function createAdminUser(payload: CreateAdminUserRequest, signal: AbortSignal): Promise<CreatedAdminUser> {
  return requestJson('/v1/admin/users', createdAdminUserSchema, signal, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(createAdminUserRequestSchema.parse(payload)),
  })
}

function updateAdminUser(userId: string, payload: UpdateAdminUserRequest, signal: AbortSignal): Promise<UpdatedAdminUser> {
  return requestJson(`/v1/admin/users/${encodeURIComponent(userId)}`, updatedAdminUserSchema, signal, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(updateAdminUserRequestSchema.parse(payload)),
  })
}

function resetAdminUserPassword(userId: string, signal: AbortSignal): Promise<ResetAdminPassword> {
  return requestJson(`/v1/admin/users/${encodeURIComponent(userId)}/reset-password`, resetAdminPasswordSchema, signal, { method: 'POST' })
}

function getAdminUserEvents(signal: AbortSignal): Promise<AdminUserEvents> {
  return requestJson('/v1/admin/user-events', adminUserEventsSchema, signal)
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

export { requestJson, getInspectionCase, getAllInspectionCases, getInspectionCaseEpisode, AUTH_UNAUTHORIZED_EVENT, ApiHttpError, createAdminUser, createInspectionCase, getAdminCatalog, getAdminUserEvents, getAdminUsers, getCurrentUser, getEpisodeDetail, getExposureTimeline, getInspectionCaseEvents, getInspectionCases, getInspectors, getTractorOverview, loginUser, logoutUser, resetAdminUserPassword, updateAdminUser, updateInspectionCase }
