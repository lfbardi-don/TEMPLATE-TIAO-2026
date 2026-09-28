import { useState, type FormEvent } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { Alert, AlertDescription, AlertTitle } from '../components/ui/alert'
import { Button } from '../components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card'
import { Input } from '../components/ui/input'
import { Label } from '../components/ui/label'
import { LoadingView, ResourceError } from '../features/common/ResourceViews'
import { ApiHttpError } from '../lib/api-client'
import { useSession } from './session-context'

function LoginPage() {
  const { state, signIn, retry } = useSession()
  const location = useLocation()
  const [workerId, setWorkerId] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const requestedPath = (location.state as { from?: unknown } | null)?.from
  const destination = typeof requestedPath === 'string' && requestedPath.startsWith('/') && !requestedPath.startsWith('//') ? requestedPath : '/'

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setMessage(null)
    try {
      await signIn({ worker_id: workerId, password })
    } catch (error: unknown) {
      setMessage(error instanceof ApiHttpError && error.status === 401
        ? 'Número do trabalhador ou senha inválidos.'
        : 'Não foi possível entrar. Verifique a conexão e tente novamente.')
    } finally {
      setBusy(false)
    }
  }

  if (state.kind === 'loading') return <main className="page"><LoadingView /></main>
  if (state.kind === 'error') return <main className="page"><ResourceError error={state.error} onRetry={retry} /></main>
  if (state.kind === 'authenticated') return <Navigate to={destination} replace />

  return <main className="page"><div className="page-heading"><div><p className="eyebrow">Inspeção preventiva</p><h1>Entrar</h1><p className="muted">Acesse a máquina e a pauta de vistoria com sua conta.</p></div></div>
    <Card><CardHeader><CardTitle>Conta de acesso</CardTitle></CardHeader><CardContent className="stack">
      {message === null ? null : <Alert variant="destructive"><AlertTitle>Entrada não concluída</AlertTitle><AlertDescription>{message}</AlertDescription></Alert>}
      <form className="stack" onSubmit={(event) => void submit(event)}>
        <div className="field"><Label htmlFor="login-worker-id">Número do trabalhador</Label><Input id="login-worker-id" type="text" inputMode="numeric" pattern="[0-9]{1,20}" minLength={1} maxLength={20} autoComplete="username" required value={workerId} onChange={(event) => setWorkerId(event.target.value.replace(/[^0-9]/g, '').slice(0, 20))} disabled={busy} /></div>
        <div className="field"><Label htmlFor="login-password">Senha</Label><Input id="login-password" type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} disabled={busy} /></div>
        <div><Button type="submit" disabled={busy}>{busy ? 'Entrando…' : 'Entrar'}</Button></div>
      </form>
    </CardContent></Card>
  </main>
}

export { LoginPage }
