import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { TelemetryPeriodsPanel } from './TelemetryPeriodsPanel'

describe('TelemetryPeriodsPanel', () => {
  it('mostra importações e missões elegíveis sem depender do overview pontuado', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      evidence_role: 'operational_output_only',
      tractor: { id: '22222222-2222-4222-8222-222222222222', fleet_id: '11111111-1111-4111-8111-111111111111', external_id: 'F314', display_name: null, model_name: 'Fendt 314', created_at_utc: '2024-06-01T10:00:00+00:00' },
      fleet: { id: '11111111-1111-4111-8111-111111111111', name: 'Fazenda', created_at_utc: '2024-06-01T10:00:00+00:00' },
      imports: [{ id: '33333333-3333-4333-8333-333333333333', dataset_split: 'validation', source_format: 'fendt314_zip', source_file_name: 'Fendt 314.zip', source_member: 'Fendt 314.csv', source_sha256: 'a'.repeat(64), semantic_sha256: 'b'.repeat(64), transform_version: 'fendt314-original-to-1hz-v1', started_at_utc: '2024-09-07T10:18:16+00:00', ended_at_utc: '2024-09-07T10:19:16+00:00', sample_count: 61, mission_count: 1, missions: [{ mission_index: 277, started_at_utc: '2024-09-07T10:18:16+00:00', ended_at_utc: '2024-09-07T10:19:16+00:00', sample_count: 61, observed_duration_seconds: 60, replay_status: 'ELIGIBLE' }] }],
    }), { status: 200 })))

    render(<TelemetryPeriodsPanel tractorId="22222222-2222-4222-8222-222222222222" />)

    expect(await screen.findByText('Períodos de telemetria')).toBeInTheDocument()
    expect(screen.getByText('ELIGIBLE')).toBeInTheDocument()
    expect(screen.getByText(/Fendt 314.zip/)).toBeInTheDocument()
  })
})
