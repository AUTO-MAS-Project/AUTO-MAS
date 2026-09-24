import { describe, expect, it } from 'vitest'
import { useSaveQueue } from './useSaveQueue'

const deferred = <T>() => {
  let resolve!: (_value: T) => void
  let reject!: (_reason: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

const flush = () => new Promise(resolve => setTimeout(resolve, 0))

describe('useSaveQueue', () => {
  it('runs saves strictly in enqueue order without dropping any', async () => {
    const { enqueue, isSaving } = useSaveQueue()
    const first = deferred<string>()
    const second = deferred<string>()
    const started: string[] = []

    const firstResult = enqueue(async () => {
      started.push('first')
      return first.promise
    })
    const secondResult = enqueue(async () => {
      started.push('second')
      return second.promise
    })

    expect(isSaving.value).toBe(true)
    expect(started).toEqual(['first'])

    first.resolve('a')
    await flush()
    expect(started).toEqual(['first', 'second'])

    second.resolve('b')
    await expect(firstResult).resolves.toBe('a')
    await expect(secondResult).resolves.toBe('b')
    expect(isSaving.value).toBe(false)
  })

  it('merges pending saves with the same key and keeps the latest value', async () => {
    const { enqueue } = useSaveQueue()
    const gate = deferred<void>()
    const sent: unknown[] = []

    const blocker = enqueue(() => gate.promise)
    const stale = enqueue(async () => {
      sent.push('stale')
      return 'stale'
    }, 'Run.Limit')
    const latest = enqueue(async () => {
      sent.push('latest')
      return 'latest'
    }, 'Run.Limit')
    const other = enqueue(async () => {
      sent.push('other')
      return 'other'
    }, 'Run.Other')

    gate.resolve()
    await blocker
    await expect(stale).resolves.toBe('latest')
    await expect(latest).resolves.toBe('latest')
    await expect(other).resolves.toBe('other')
    expect(sent).toEqual(['latest', 'other'])
  })

  it('does not merge with a save that is already running', async () => {
    const { enqueue } = useSaveQueue()
    const gate = deferred<void>()
    const sent: string[] = []

    const running = enqueue(async () => {
      sent.push('running')
      await gate.promise
      return 'running'
    }, 'Info.Name')
    const next = enqueue(async () => {
      sent.push('next')
      return 'next'
    }, 'Info.Name')

    gate.resolve()
    await expect(running).resolves.toBe('running')
    await expect(next).resolves.toBe('next')
    expect(sent).toEqual(['running', 'next'])
  })

  it('rejects only the failing save and keeps draining the rest', async () => {
    const { enqueue, isSaving } = useSaveQueue()

    const failed = enqueue(async () => {
      throw new Error('boom')
    })
    const after = enqueue(async () => 'ok')

    await expect(failed).rejects.toThrow('boom')
    await expect(after).resolves.toBe('ok')
    expect(isSaving.value).toBe(false)
  })

  it('accepts new saves after the queue has fully drained', async () => {
    const { enqueue, isSaving } = useSaveQueue()

    await expect(enqueue(async () => 1)).resolves.toBe(1)
    expect(isSaving.value).toBe(false)

    const later = enqueue(async () => 2)
    expect(isSaving.value).toBe(true)
    await expect(later).resolves.toBe(2)
    expect(isSaving.value).toBe(false)
  })
})
