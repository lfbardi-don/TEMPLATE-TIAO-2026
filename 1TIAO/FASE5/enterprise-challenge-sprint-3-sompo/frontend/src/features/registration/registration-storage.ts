import { fleetRegistrationSchema, type FleetRegistration } from '../../lib/api-contracts'

const registrationStorageKey = 'tractor-usage:last-registration:v1'

function readLastRegistration(): FleetRegistration | null {
  try {
    const raw = window.localStorage.getItem(registrationStorageKey)
    if (raw === null) return null
    const parsed: unknown = JSON.parse(raw)
    const result = fleetRegistrationSchema.safeParse(parsed)
    return result.success ? result.data : null
  } catch (error: unknown) {
    if (error instanceof SyntaxError || error instanceof DOMException) return null
    throw error
  }
}

function writeLastRegistration(value: FleetRegistration): boolean {
  try {
    window.localStorage.setItem(registrationStorageKey, JSON.stringify(value))
    return true
  } catch (error: unknown) {
    if (error instanceof DOMException) return false
    throw error
  }
}

export { readLastRegistration, registrationStorageKey, writeLastRegistration }
