import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiHttpError } from '../lib/api-client'

type ResourceState<T> =
  | { kind: 'loading' }
  | { kind: 'empty' }
  | { kind: 'success'; data: T }
  | { kind: 'error'; error: ApiHttpError; data: T | null }

type PollingPolicy = {
  successDelayMs?: number
  retryDelayMs?: number
}

type PollingResource<T> = {
  state: ResourceState<T>
  isRefreshing: boolean
  refresh: () => void
}

type ResourceLoader<T> = (signal: AbortSignal) => Promise<T>

function usePollingResource<T>(loader: ResourceLoader<T>, policy: PollingPolicy = {}): PollingResource<T> {
  const successDelayMs = policy.successDelayMs ?? 2000
  const retryDelayMs = policy.retryDelayMs ?? 5000
  const [state, setState] = useState<ResourceState<T>>({ kind: 'loading' })
  const [isRefreshing, setIsRefreshing] = useState(false)
  const refreshRef = useRef<() => void>(() => undefined)

  useEffect(() => {
    let isActive = true
    let inFlight = false
    let rerunRequested = false
    let timer: number | null = null
    let controller: AbortController | null = null
    let lastValue: T | null = null

    const clearTimer = () => {
      if (timer !== null) {
        window.clearTimeout(timer)
        timer = null
      }
    }

    const schedule = (delayMs: number, run: () => void) => {
      clearTimer()
      if (isActive && !document.hidden) timer = window.setTimeout(run, delayMs)
    }

    const shouldRetry = (error: ApiHttpError) => error.kind === 'network' || error.status === 500 || error.status === 503

    const run = () => {
      if (!isActive || document.hidden || inFlight) return
      inFlight = true
      controller = new AbortController()
      setIsRefreshing(lastValue !== null)

      void loader(controller.signal)
        .then((value) => {
          if (!isActive) return
          lastValue = value
          setState({ kind: 'success', data: value })
          schedule(successDelayMs, run)
        })
        .catch((error: unknown) => {
          if (!isActive || controller?.signal.aborted) return
          if (error instanceof ApiHttpError) {
            if (error.status === 404) {
              setState({ kind: 'empty' })
              schedule(successDelayMs, run)
              return
            }
            setState({ kind: 'error', error, data: lastValue })
            if (shouldRetry(error)) schedule(retryDelayMs, run)
            return
          }
          throw error
        })
        .finally(() => {
          inFlight = false
          if (isActive) setIsRefreshing(false)
          if (rerunRequested && isActive && !document.hidden) {
            rerunRequested = false
            schedule(0, run)
          }
        })
    }

    const requestRefresh = () => {
      clearTimer()
      if (inFlight) {
        rerunRequested = true
        controller?.abort()
        return
      }
      run()
    }

    const onVisibilityChange = () => {
      clearTimer()
      if (document.hidden) {
        if (inFlight) {
          rerunRequested = false
          controller?.abort()
        }
        return
      }
      requestRefresh()
    }

    refreshRef.current = requestRefresh
    queueMicrotask(() => {
      if (!isActive) return
      setState({ kind: 'loading' })
      setIsRefreshing(false)
    })
    document.addEventListener('visibilitychange', onVisibilityChange)
    run()

    return () => {
      isActive = false
      clearTimer()
      controller?.abort()
      document.removeEventListener('visibilitychange', onVisibilityChange)
    }
  }, [loader, retryDelayMs, successDelayMs])

  const refresh = useCallback(() => refreshRef.current(), [])
  return { state, isRefreshing, refresh }
}

export { usePollingResource }
export type { PollingResource, ResourceState }
