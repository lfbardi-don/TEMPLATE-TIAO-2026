import { createContext, useContext } from 'react'
import type { ApiHttpError } from '../lib/api-client'
import type { LoginRequest, Principal } from '../lib/api-contracts'

type SessionState =
  | { kind: 'loading' }
  | { kind: 'anonymous' }
  | { kind: 'authenticated'; principal: Principal }
  | { kind: 'error'; error: ApiHttpError }

type SessionContextValue = {
  state: SessionState
  signIn: (credentials: LoginRequest) => Promise<void>
  signOut: () => Promise<void>
  retry: () => void
}

const SessionContext = createContext<SessionContextValue | null>(null)

function useSession(): SessionContextValue {
  const context = useContext(SessionContext)
  if (context === null) throw new Error('Sessão indisponível fora do provedor.')
  return context
}

function usePrincipal(): Principal {
  const { state } = useSession()
  if (state.kind !== 'authenticated') throw new Error('Usuário não autenticado.')
  return state.principal
}

export { SessionContext, usePrincipal, useSession }
export type { SessionState }
