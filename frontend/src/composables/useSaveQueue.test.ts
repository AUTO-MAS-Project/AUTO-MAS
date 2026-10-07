import { describe, expect, it } from 'vitest'
import { useSaveQueue } from './useSaveQueue'
import { AppRequestError } from '@/utils/appError'

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
describe('useSaveQueue 保存状态机', () => {
  it('页面级与字段级都按 dirty → saving → saved 流转', async () => {
    const { enqueue, state, fieldStates, isSaving, canLeave } = useSaveQueue()
    const gate = deferred<void>()
    expect(state.value).toBe('idle')

    const pending = enqueue(async () => {
      await gate.promise
      return true
    }, 'Info.Name')

    expect(state.value).toBe('saving')
    expect(fieldStates['Info.Name']).toBe('saving')
    expect(canLeave.value).toBe(false)

    gate.resolve()
    await pending
    expect(state.value).toBe('saved')
    expect(fieldStates['Info.Name']).toBe('saved')
    expect(isSaving.value).toBe(false)
    expect(canLeave.value).toBe(true)
  })

  it('同一字段在途时再来一次改动回落到 dirty，不假装已保存', async () => {
    const { enqueue, state, fieldStates } = useSaveQueue()
    const gate = deferred<void>()
    const running = enqueue(async () => {
      await gate.promise
      return 'first'
    }, 'Info.Notes')
    expect(fieldStates['Info.Notes']).toBe('saving')

    const queued = enqueue(async () => 'second', 'Info.Notes')
    expect(fieldStates['Info.Notes']).toBe('dirty')

    gate.resolve()
    await running
    // 第一次保存已返回，但更新的值仍在排队/在途：绝不能显示为已保存
    expect(fieldStates['Info.Notes']).not.toBe('saved')
    expect(state.value).not.toBe('saved')
    await queued
    expect(fieldStates['Info.Notes']).toBe('saved')
    expect(state.value).toBe('saved')
  })

  it('写失败默认落 failed_draft_kept 并禁止离开', async () => {
    const { enqueue, state, fieldStates, canLeave, hasUnresolved } = useSaveQueue()
    const failed = enqueue(async () => {
      throw new Error('write failed')
    }, 'Info.Name')

    await expect(failed).rejects.toThrow('write failed')
    expect(state.value).toBe('failed_draft_kept')
    expect(fieldStates['Info.Name']).toBe('failed_draft_kept')
    expect(hasUnresolved.value).toBe(true)
    expect(canLeave.value).toBe(false)
  })

  it('断线无法确认落 unknown，且不会自愈为已保存', async () => {
    const { enqueue, enqueueSave, state, markResolved, canLeave } = useSaveQueue()
    const offline = enqueue(async () => {
      throw new AppRequestError('network_unavailable')
    }, 'Info.Name')

    await expect(offline).rejects.toBeInstanceOf(AppRequestError)
    expect(state.value).toBe('unknown')
    expect(canLeave.value).toBe(false)

    markResolved('Info.Name', 'failed_reverted')
    expect(state.value).toBe('failed_reverted')
    expect(canLeave.value).toBe(false)

    const recovered = await enqueueSave(async () => ({ outcome: 'saved' as const }), 'Info.Name')
    expect(recovered.outcome).toBe('saved')
    expect(state.value).toBe('saved')
    expect(canLeave.value).toBe(true)
  })

  it('业务拒绝落 rejected 且保留输入，已回读旧值落 failed_reverted', async () => {
    const { enqueueSave, fieldStates } = useSaveQueue()

    await enqueueSave(async () => ({ outcome: 'rejected' as const }), 'Info.Name')
    expect(fieldStates['Info.Name']).toBe('rejected')

    await enqueueSave(async () => ({ outcome: 'failed_reverted' as const }), 'Info.Notes')
    expect(fieldStates['Info.Notes']).toBe('failed_reverted')

    await enqueueSave(async () => ({ outcome: 'discarded' as const }), 'Info.Id')
    expect(fieldStates['Info.Id']).toBe('discarded')
  })

  it('enqueueSave 里 run 抛错时按异常分类，不把未知当成功', async () => {
    const { enqueueSave, state } = useSaveQueue()
    const report = await enqueueSave(async () => {
      throw new AppRequestError('network_unavailable')
    }, 'Info.Name')
    expect(report.outcome).toBe('unknown')
    expect(state.value).toBe('unknown')
  })

  it('waitForIdle 等完在途保存后才放行', async () => {
    const { enqueue, waitForIdle, isSaving } = useSaveQueue()
    const gate = deferred<void>()
    const pending = enqueue(async () => {
      await gate.promise
    })

    let idle = false
    const wait = waitForIdle().then(() => {
      idle = true
    })
    expect(idle).toBe(false)
    expect(isSaving.value).toBe(true)

    gate.resolve()
    await pending
    await wait
    expect(idle).toBe(true)
    expect(isSaving.value).toBe(false)
  })
})
