import type { ReactNode } from 'react'
import { SessionContext } from '../app/session-context'
import type { Principal } from '../lib/api-contracts'
import { insurerFixture } from './session-fixtures'

function SessionFixture({ children, principal = insurerFixture }: { children: ReactNode; principal?: Principal }) {
  return <SessionContext.Provider value={{ state: { kind: 'authenticated', principal }, signIn: async () => undefined, signOut: async () => undefined, retry: () => undefined }}>{children}</SessionContext.Provider>
}

export { SessionFixture }
