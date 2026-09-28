import { useCallback } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card'
import { usePollingResource } from '../../hooks/usePollingResource'
import { getExposureTimeline } from '../../lib/api-client'
import type { Condition, ExposureTimeline } from '../../lib/api-contracts'
import { formatDate, formatDuration, formatNumber } from '../../lib/presentation'
import { LoadingView, ResourceError } from '../common/ResourceViews'

const LOW_OPERATION_HOURS = 1
const WIDTH = 720
const HEIGHT = 220
const MARGIN = { top: 24, right: 12, bottom: 44, left: 44 }

type Week = ExposureTimeline['weeks'][number]

function isLowOperation(week: Week): boolean {
  return week.status === 'OK' && week.observed_hours < LOW_OPERATION_HOURS
}

function formatObservedTime(hours: number): string {
  return hours < 1 ? formatDuration(hours * 3600) : `${formatNumber(hours, 1)} h`
}

function ExposureTimelineChart({ weeks }: { weeks: Week[] }) {
  const plotWidth = WIDTH - MARGIN.left - MARGIN.right
  const plotHeight = HEIGHT - MARGIN.top - MARGIN.bottom
  const representative = weeks.filter((week) => week.status === 'OK' && !isLowOperation(week))
  const maximum = Math.max(1, ...(representative.length > 0 ? representative : weeks).map((week) => week.physical_exposure_seconds_per_hour ?? 0))
  const slot = plotWidth / weeks.length
  const barWidth = Math.min(56, slot * 0.64)
  const summary = weeks.map((week) => `${formatDate(week.week_start_utc)}: ${week.status === 'NO_DATA' ? 'sem operação' : `${formatNumber(week.physical_exposure_seconds_per_hour, 0)} s/h${isLowOperation(week) ? ' com pouca operação' : ''}`}`).join('; ')

  return (
    <svg className="timeline-chart" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label={`Exposição física por semana. ${summary}`}>
      <line className="chart-axis" x1={MARGIN.left} x2={WIDTH - MARGIN.right} y1={MARGIN.top + plotHeight} y2={MARGIN.top + plotHeight} />
      <text className="chart-tick" x={MARGIN.left - 6} y={MARGIN.top + 4} textAnchor="end">{formatNumber(maximum, 0)}</text>
      <text className="chart-tick" x={MARGIN.left - 6} y={MARGIN.top + plotHeight} textAnchor="end">0</text>
      {weeks.map((week, index) => {
        const center = MARGIN.left + slot * index + slot / 2
        const rate = week.physical_exposure_seconds_per_hour ?? 0
        const height = week.status === 'NO_DATA' ? 0 : Math.max(2, Math.min(1, rate / maximum) * plotHeight)
        const lowOperation = isLowOperation(week)
        return (
          <g key={week.week_start_utc}>
            {week.status === 'NO_DATA'
              ? <text className="chart-empty" x={center} y={MARGIN.top + plotHeight - 8} textAnchor="middle">sem operação</text>
              : <rect className={lowOperation ? 'chart-bar chart-bar-low' : 'chart-bar'} x={center - barWidth / 2} y={MARGIN.top + plotHeight - height} width={barWidth} height={height} rx={3} />}
            {week.episode_count > 0 ? <text className="chart-count" x={center} y={MARGIN.top + plotHeight - height - 6} textAnchor="middle">{week.episode_count}</text> : null}
            <text className="chart-tick" x={center} y={HEIGHT - MARGIN.bottom + 16} textAnchor="middle">{formatDate(week.week_start_utc)}</text>
            <text className="chart-subtick" x={center} y={HEIGHT - MARGIN.bottom + 31} textAnchor="middle">{week.status === 'NO_DATA' ? '—' : formatObservedTime(week.observed_hours)}</text>
          </g>
        )
      })}
    </svg>
  )
}

function ExposureTimelineCard({ tractorId, asOf, condition = '' }: { tractorId: string; asOf?: string; condition?: string }) {
  const loader = useCallback((signal: AbortSignal) => getExposureTimeline(tractorId, signal, asOf), [tractorId, asOf])
  const resource = usePollingResource(loader, { successDelayMs: 5000 })

  if (resource.state.kind === 'loading') return <LoadingView />
  if (resource.state.kind === 'error' && resource.state.data === null) return <ResourceError error={resource.state.error} onRetry={resource.refresh} />
  const timeline = resource.state.kind === 'success' || resource.state.kind === 'error' ? resource.state.data : null
  if (timeline === null || timeline.weeks.length === 0) return null

  const filtered = condition === '' ? timeline.weeks : timeline.weeks.map((week) => ({ ...week, physical_exposure_seconds_per_hour: week.status === 'NO_DATA' || week.condition_seconds === undefined ? null : (week.condition_seconds[condition as Condition] ?? 0) / week.observed_hours, episode_count: week.condition_episode_counts?.[condition as Condition] ?? 0 }))

  return (
    <Card role="region" aria-labelledby="timeline-heading">
      <CardHeader><CardTitle id="timeline-heading">Semana a semana</CardTitle></CardHeader>
      <CardContent className="stack">
        <p className="muted">Exposição por hora de operação. Acima de cada barra: episódios; abaixo: horas observadas.</p>
        <ExposureTimelineChart weeks={filtered} />
        <p className="chart-legend"><span className="legend-swatch" /> semana com operação <span className="legend-swatch legend-swatch-low" /> menos de {LOW_OPERATION_HOURS} h de operação: a taxa é pouco representativa</p>
      </CardContent>
    </Card>
  )
}

export { ExposureTimelineCard }
