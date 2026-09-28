import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { AUTH_UNAUTHORIZED_EVENT, ApiHttpError, getCurrentUser, loginUser, logoutUser } from '../lib/api-client'
import type { LoginRequest, Principal } from '../lib/api-contracts'
import { LoadingView, ResourceError } from '../features/common/ResourceViews'
import { SessionContext, usePrincipal, useSession, type SessionState } from './session-context'

function SessionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<SessionState>({ kind: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    const onUnauthorized = () => setState({ kind: 'anonymous' })
    window.addEventListener(AUTH_UNAUTHORIZED_EVENT, onUnauthorized)
    void getCurrentUser(controller.signal)
      .then((principal) => { if (!controller.signal.aborted) setState({ kind: 'authenticated', principal }) })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        if (error instanceof ApiHttpError && error.status === 401) setState({ kind: 'anonymous' })
        else if (error instanceof ApiHttpError) setState({ kind: 'error', error })
        else setState({ kind: 'error', error: new ApiHttpError('network', 'Não foi possível verificar a sessão.') })
      })
    return () => {
      controller.abort()
      window.removeEventListener(AUTH_UNAUTHORIZED_EVENT, onUnauthorized)
    }
  }, [attempt])

  const signIn = useCallback(async (credentials: LoginRequest) => {
    const principal = await loginUser(credentials, new AbortController().signal)
    setState({ kind: 'authenticated', principal })
  }, [])

  const signOut = useCallback(async () => {
    await logoutUser(new AbortController().signal)
    setState({ kind: 'anonymous' })
  }, [])

  const retry = useCallback(() => {
    setState({ kind: 'loading' })
    setAttempt((current) => current + 1)
  }, [])

  return <SessionContext.Provider value={{ state, signIn, signOut, retry }}>{children}</SessionContext.Provider>
}

function RequireSession() {
  const { state, retry } = useSession()
  const location = useLocation()
  if (state.kind === 'loading') return <main className="page"><LoadingView /></main>
  if (state.kind === 'error') return <main className="page"><ResourceError error={state.error} onRetry={retry} /></main>
  if (state.kind === 'anonymous') return <Navigate to="/login" state={{ from: location.pathname + location.search + location.hash }} replace />
  return <Outlet />
}

function RequireRole({ role, children }: { role: Principal['role'] | readonly Principal['role'][]; children: ReactNode }) {
  const principal = usePrincipal()
  const allowed = typeof role === 'string' ? principal.role === role : role.includes(principal.role)
  if (!allowed) {
    return <main className="page"><p className="eyebrow">Acesso restrito</p><h1>Você não tem acesso a esta página</h1><p>Entre com uma conta autorizada para abrir esta página.</p></main>
  }
  return children
}

export { RequireRole, RequireSession, SessionProvider }
