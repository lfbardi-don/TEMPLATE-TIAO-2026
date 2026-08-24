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
  if (error.kind === 'network') return 'A API local não respondeu. Confirme que o comando da demonstração ainda está ativo.'
  if (error.status === 503) return 'A API local ainda não está pronta porque uma dependência está indisponível.'
  if (error.status !== null && error.status >= 500) return 'A API local encontrou uma indisponibilidade temporária.'
  return 'A consulta não pôde ser concluída. Tente novamente manualmente.'
}

function ResourceError({ error, onRetry, children }: { error: ApiHttpError; onRetry: () => void; children?: ReactNode }) {
  return <div className="stack"><Alert variant="destructive"><AlertTitle>Atualização não concluída</AlertTitle><AlertDescription>{errorText(error)} {error.detail === null ? '' : `Detalhe: ${error.detail}`}</AlertDescription></Alert><Button type="button" variant="secondary" onClick={onRetry}>Tentar novamente</Button>{children}</div>
}

export { LoadingView, ResourceError }
