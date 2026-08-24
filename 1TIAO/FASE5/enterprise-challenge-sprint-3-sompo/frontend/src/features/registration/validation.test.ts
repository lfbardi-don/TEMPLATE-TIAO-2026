import { describe, expect, it } from 'vitest'
import { hasRegistrationErrors, toCreateFleetRequest, validateRegistration } from './validation'

describe('validateRegistration', () => {
  it('aplica trim e recusa identificadores duplicados', () => {
    const draft = { name: '  Frota A  ', tractors: [{ formId: 'one', externalId: '  T-1 ', displayName: ' Norte ' }, { formId: 'two', externalId: 'T-1', displayName: '' }] }
    const errors = validateRegistration(draft)

    expect(hasRegistrationErrors(errors)).toBe(true)
    expect(errors.tractors.two?.externalId).toContain('não podem se repetir')
    expect(toCreateFleetRequest({ name: '  Frota A  ', tractors: [draft.tractors[0]] })).toEqual({ name: 'Frota A', tractors: [{ external_id: 'T-1', display_name: 'Norte' }] })
  })
})
