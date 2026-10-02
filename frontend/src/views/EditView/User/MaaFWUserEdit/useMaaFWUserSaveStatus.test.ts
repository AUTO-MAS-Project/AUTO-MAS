import { effectScope } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useMaaFWUserSaveStatus } from './useMaaFWUserSaveStatus'

const deferred = () => {
  let resolve!: () => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<void>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

const setup = () => {
  const scope = effectScope()
  const status = scope.run(() => useMaaFWUserSaveStatus())!
  return { scope, status }
}

describe('useMaaFWUserSaveStatus', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('保存中 → 已保存，两秒后回到空闲；全部写完才清掉「有未保存改动」', async () => {
    const { scope, status } = setup()
    const first = deferred()
    const second = deferred()
    const order: string[] = []

    const firstSave = status.enqueueSave(async () => {
      order.push('first:start')
      await first.promise
      order.push('first:end')
    })
    const secondSave = status.enqueueSave(async () => {
      order.push('second:start')
      await second.promise
    })
    expect(status.pendingCount()).toBe(2)
    expect(status.isSaving.value).toBe(true)
    expect(status.hasUnsavedChanges.value).toBe(true)
    expect(status.saveStatus.value).toBe('saving')

    first.resolve()
    await firstSave
    expect(status.pendingCount()).toBe(1)
    expect(status.isSaving.value).toBe(true)
    expect(status.hasUnsavedChanges.value).toBe(true)

    second.resolve()
    await secondSave
    // 串行：第二个在第一个写完之后才开始
    expect(order).toEqual(['first:start', 'first:end', 'second:start'])
    expect(status.pendingCount()).toBe(0)
    expect(status.isSaving.value).toBe(false)
    expect(status.hasUnsavedChanges.value).toBe(false)
    expect(status.saveStatus.value).toBe('saved')

    await vi.advanceTimersByTimeAsync(1999)
    expect(status.saveStatus.value).toBe('saved')
    await vi.advanceTimersByTimeAsync(1)
    expect(status.saveStatus.value).toBe('idle')
    scope.stop()
  })

  it('动作里读到的 pendingCount 含自己：只剩自己时是 1', async () => {
    const { scope, status } = setup()
    const seen: number[] = []
    const gate = deferred()
    const firstSave = status.enqueueSave(async () => {
      await gate.promise
      seen.push(status.pendingCount())
    })
    const secondSave = status.enqueueSave(async () => {
      seen.push(status.pendingCount())
    })
    gate.resolve()
    await Promise.all([firstSave, secondSave])
    expect(seen).toEqual([2, 1])
    scope.stop()
  })

  it('出错：状态带原因并把错误抛给调用方，后面的保存照常执行', async () => {
    const { scope, status } = setup()
    const failing = status.enqueueSave(async () => {
      throw new Error('写入失败')
    })
    const gate = deferred()
    const next = vi.fn(() => gate.promise)
    const following = status.enqueueSave(next)

    await expect(failing).rejects.toThrow('写入失败')
    expect(status.saveStatus.value).toBe('error')
    expect(status.saveErrorMessage.value).toBe('写入失败')
    gate.resolve()
    await following
    expect(next).toHaveBeenCalledOnce()
    expect(status.saveStatus.value).toBe('saved')
    expect(status.saveErrorMessage.value).toBe('')
    scope.stop()
  })

  it('出错后即使队列清空也保留「有未保存改动」', async () => {
    const { scope, status } = setup()
    await expect(
      status.enqueueSave(async () => {
        throw new Error('x')
      })
    ).rejects.toThrow('x')
    expect(status.pendingCount()).toBe(0)
    expect(status.isSaving.value).toBe(false)
    expect(status.hasUnsavedChanges.value).toBe(true)
    scope.stop()
  })

  it('作用域销毁时清掉回到空闲的定时器', async () => {
    const { scope, status } = setup()
    await status.enqueueSave(async () => undefined)
    expect(vi.getTimerCount()).toBe(1)
    scope.stop()
    expect(vi.getTimerCount()).toBe(0)
    await vi.advanceTimersByTimeAsync(5000)
    expect(status.saveStatus.value).toBe('saved')
  })
})
