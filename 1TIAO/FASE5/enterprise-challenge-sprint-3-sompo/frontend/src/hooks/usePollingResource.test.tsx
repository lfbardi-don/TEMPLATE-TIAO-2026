import { act, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiHttpError } from '../lib/api-client'
import { usePollingResource } from './usePollingResource'

function ResourceProbe({ loader }: { loader: (signal: AbortSignal) => Promise<string> }) {
  const resource = usePollingResource(loader)
  if (resource.state.kind === 'success') return <p>success:{resource.state.data}</p>
  if (resource.state.kind === 'empty') return <p>empty</p>
  if (resource.state.kind === 'error') return <p>error:{resource.state.data ?? 'none'}</p>
  return <p>loading</p>
}

afterEach(() => {
  vi.useRealTimers()
  Object.defineProperty(document, 'hidden', { configurable: true, value: false })
})

describe('usePollingResource', () => {
  it('trata 404 como vazio e continua o polling', async () => {
    vi.useFakeTimers()
    const loader = vi.fn(async () => { throw new ApiHttpError('http', 'not found', 404) })
    render(<ResourceProbe loader={loader} />)

    await act(async () => {})
    expect(screen.getByText('empty')).toBeInTheDocument()
    expect(loader).toHaveBeenCalledTimes(1)
    await act(async () => { await vi.advanceTimersByTimeAsync(2000) })
    expect(loader).toHaveBeenCalledTimes(2)
  })

  it('não inicia GET sobreposto', async () => {
    vi.useFakeTimers()
    let firstResolver: (value: string) => void = () => undefined
    let secondResolver: (value: string) => void = () => undefined
    let callNumber = 0
    const loader = vi.fn(() => new Promise<string>((resolve) => {
      callNumber += 1
      if (callNumber === 1) firstResolver = resolve
      else secondResolver = resolve
    }))
    render(<ResourceProbe loader={loader} />)

    expect(loader).toHaveBeenCalledTimes(1)
    await act(async () => { firstResolver('primeiro') })
    await act(async () => { await vi.advanceTimersByTimeAsync(1999) })
    expect(loader).toHaveBeenCalledTimes(1)
    await act(async () => { await vi.advanceTimersByTimeAsync(1) })
    expect(loader).toHaveBeenCalledTimes(2)
    await act(async () => { secondResolver('segundo') })
  })

  it('aborta na aba oculta e consulta ao voltar', async () => {
    const signals: AbortSignal[] = []
    const loader = vi.fn((signal: AbortSignal) => new Promise<string>((_resolve, reject) => {
      signals.push(signal)
      signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
    }))
    render(<ResourceProbe loader={loader} />)

    expect(signals).toHaveLength(1)
    Object.defineProperty(document, 'hidden', { configurable: true, value: true })
    await act(async () => { document.dispatchEvent(new Event('visibilitychange')) })
    expect(signals[0]?.aborted).toBe(true)
    Object.defineProperty(document, 'hidden', { configurable: true, value: false })
    await act(async () => { document.dispatchEvent(new Event('visibilitychange')) })
    expect(signals).toHaveLength(2)
  })

  it('preserva o último valor em uma falha recuperável', async () => {
    vi.useFakeTimers()
    let callNumber = 0
    const loader = vi.fn(async () => {
      callNumber += 1
      if (callNumber === 1) return 'válido'
      throw new ApiHttpError('network', 'offline')
    })
    render(<ResourceProbe loader={loader} />)

    await act(async () => {})
    expect(screen.getByText('success:válido')).toBeInTheDocument()
    await act(async () => { await vi.advanceTimersByTimeAsync(2000) })
    expect(screen.getByText('error:válido')).toBeInTheDocument()
  })
})
