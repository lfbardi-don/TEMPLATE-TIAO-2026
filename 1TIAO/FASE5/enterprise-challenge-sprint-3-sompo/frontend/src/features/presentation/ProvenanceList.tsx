import type { Provenance } from '../../lib/api-contracts'
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card'
import { Badge } from '../../components/ui/badge'

type ProvenanceListProps = { provenance: Provenance[] }

function ProvenanceList({ provenance }: ProvenanceListProps) {
  return (
    <section aria-labelledby="provenance-heading">
      <Card>
        <CardHeader><CardTitle id="provenance-heading">Proveniência observada</CardTitle></CardHeader>
        <CardContent className="stack">
          {provenance.length === 0 ? <p className="muted">Ainda não há proveniência para exibir.</p> : provenance.map((source) => (
            <div className="spread" key={`${source.source_kind}-${source.dataset_split}-${source.source_reference}`}>
              <div><strong>{source.source_reference}</strong><p className="muted">Origem: replay do conjunto observado · Partição: {source.dataset_split === 'validation' ? 'validação' : 'treino'}</p></div>
              <Badge variant="outline">replay observado</Badge>
            </div>
          ))}
        </CardContent>
      </Card>
    </section>
  )
}

export { ProvenanceList }
