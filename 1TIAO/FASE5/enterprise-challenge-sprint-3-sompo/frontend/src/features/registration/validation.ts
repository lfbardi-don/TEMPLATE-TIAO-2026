import type { CreateFleetRequest } from '../../lib/api-contracts'

type TractorDraft = { formId: string; externalId: string; displayName: string }
type RegistrationDraft = { name: string; tractors: TractorDraft[] }
type TractorFieldErrors = { externalId?: string; displayName?: string }
type RegistrationErrors = { name?: string; tractors: Record<string, TractorFieldErrors>; form?: string }

function validateRegistration(draft: RegistrationDraft): RegistrationErrors {
  const errors: RegistrationErrors = { tractors: {} }
  const name = draft.name.trim()
  if (name.length === 0 || name.length > 120) errors.name = 'Informe um nome de frota entre 1 e 120 caracteres.'
  if (draft.tractors.length === 0) errors.form = 'Inclua ao menos um trator.'

  const normalizedIds = new Set<string>()
  for (const tractor of draft.tractors) {
    const tractorErrors: TractorFieldErrors = {}
    const externalId = tractor.externalId.trim()
    const displayName = tractor.displayName.trim()
    if (externalId.length === 0 || externalId.length > 128) tractorErrors.externalId = 'Informe um identificador externo entre 1 e 128 caracteres.'
    if (tractor.displayName.length > 0 && displayName.length === 0) tractorErrors.displayName = 'O nome de exibição não pode conter apenas espaços.'
    if (displayName.length > 120) tractorErrors.displayName = 'O nome de exibição pode ter no máximo 120 caracteres.'
    if (externalId.length > 0) {
      if (normalizedIds.has(externalId)) tractorErrors.externalId = 'Os identificadores externos não podem se repetir.'
      normalizedIds.add(externalId)
    }
    if (tractorErrors.externalId !== undefined || tractorErrors.displayName !== undefined) errors.tractors[tractor.formId] = tractorErrors
  }
  return errors
}

function hasRegistrationErrors(errors: RegistrationErrors): boolean {
  return errors.name !== undefined || errors.form !== undefined || Object.keys(errors.tractors).length > 0
}

function toCreateFleetRequest(draft: RegistrationDraft): CreateFleetRequest {
  return {
    name: draft.name.trim(),
    tractors: draft.tractors.map((tractor) => {
      const displayName = tractor.displayName.trim()
      return { external_id: tractor.externalId.trim(), display_name: displayName.length === 0 ? null : displayName }
    }),
  }
}

export { hasRegistrationErrors, toCreateFleetRequest, validateRegistration }
export type { RegistrationDraft, RegistrationErrors, TractorDraft }
