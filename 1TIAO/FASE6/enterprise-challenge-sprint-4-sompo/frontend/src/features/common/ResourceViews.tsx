import type { ReactNode } from 'react'
import { Alert, AlertDescription, AlertTitle } from '../../components/ui/alert'
import { Button } from '../../components/ui/button'
import { Card, CardContent } from '../../components/ui/card'
import { Skeleton } from '../../components/ui/skeleton'
import type { ApiHttpError } from '../../lib/api-client'

function LoadingView() {
  return <Card><CardContent className="stack"><Skeleton style={{ width: '38%', height: '24px' }} /><Skeleton style={{ width: '100%', height: '144px' }} /><Skeleton style={{ width: '70%', height: '20px' }} /></CardContent></Card>
}

function errorText(error: ApiHttpError): string {
  if (error.kind === 'network') return 'Não foi possível conectar ao serviço. Verifique sua conexão e tente novamente.'
  if (error.status === 401) return 'Sua sessão terminou. Entre novamente para continuar.'
  if (error.status === 403) return 'Você não tem acesso a estes dados com esta conta.'
  if (error.status !== null && error.status >= 500) return 'O serviço está temporariamente indisponível. Tente novamente em instantes.'
  return 'Não foi possível carregar os dados. Tente novamente.'
}

function ResourceError({ error, onRetry, children }: { error: ApiHttpError; onRetry: () => void; children?: ReactNode }) {
  return <div className="stack"><Alert variant="destructive"><AlertTitle>{error.status === 403 ? 'Acesso negado' : 'Atualização não concluída'}</AlertTitle><AlertDescription>{errorText(error)}</AlertDescription></Alert><Button type="button" variant="secondary" onClick={onRetry}>Tentar novamente</Button>{children}</div>
}

export { LoadingView, ResourceError }
