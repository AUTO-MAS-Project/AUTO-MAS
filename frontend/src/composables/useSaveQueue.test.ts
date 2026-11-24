import { describe, expect, it } from 'vite-plus/test'
import { useSaveQueue } from './useSaveQueue'

const deferred = <T>() => {
  let resolve!: (_value: T) => void
  const promise = new Promise<T>(resolvePromise => {
    resolve = resolvePromise
  })
  return { promise, resolve }
}

const flush = () => new Promise(resolve => setTimeout(resolve, 0))

describe('useSaveQueue', () => {
  it('merges pending saves with the same key, respects barriers, and isolates errors', async () => {
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
    const barrier = enqueue(async () => {
      sent.push('barrier')
      return 'barrier'
    })
    const afterBarrier = enqueue(async () => {
      sent.push('after-barrier')
      return 'after-barrier'
    }, 'Run.Limit')

    gate.resolve()
    await blocker
    await expect(stale).resolves.toBe('latest')
    await expect(latest).resolves.toBe('latest')
    await expect(barrier).resolves.toBe('barrier')
    await expect(afterBarrier).resolves.toBe('after-barrier')
    expect(sent).toEqual(['latest', 'barrier', 'after-barrier'])

    const runningGate = deferred<void>()
    const runningSent: string[] = []
    const running = enqueue(async () => {
      runningSent.push('running')
      await runningGate.promise
      return 'running'
    }, 'Info.Name')
    const next = enqueue(async () => {
      runningSent.push('next')
      return 'next'
    }, 'Info.Name')

    runningGate.resolve()
    await expect(running).resolves.toBe('running')
    await expect(next).resolves.toBe('next')
    expect(runningSent).toEqual(['running', 'next'])

    const failed = enqueue(async () => {
      throw new Error('boom')
    })
    const after = enqueue(async () => 'ok')

    await expect(failed).rejects.toThrow('boom')
    await expect(after).resolves.toBe('ok')
    expect(isSaving.value).toBe(false)
  })

  it('serializes writes globally across independent callers while keeping isSaving per caller', async () => {
    const pageQueue = useSaveQueue()
    const childQueue = useSaveQueue()
    const gate = deferred<void>()
    const order: string[] = []

    const p1 = pageQueue.enqueue(async () => {
      order.push('page-start')
      await gate.promise
      order.push('page-end')
      return 'page'
    }, 'Info.Name')

    const p2 = childQueue.enqueue(async () => {
      order.push('child-run')
      return 'child'
    }, 'Info.Name')

    expect(pageQueue.isSaving.value).toBe(true)
    expect(childQueue.isSaving.value).toBe(true)
    expect(order).toEqual(['page-start'])

    const idle = pageQueue.waitForIdle()
    gate.resolve()
    await expect(p1).resolves.toBe('page')
    await expect(p2).resolves.toBe('child')
    await idle

    expect(order).toEqual(['page-start', 'page-end', 'child-run'])
    expect(pageQueue.isSaving.value).toBe(false)
    expect(childQueue.isSaving.value).toBe(false)
  })
})
