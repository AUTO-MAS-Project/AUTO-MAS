import { effectScope } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { AppRequestError } from '@/utils/appError'
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
  it('排队 → 保存中 → 已保存：串行执行，全部写完才清掉「有未保存改动」', async () => {
    const { scope, status } = setup()
    const first = deferred()
    const second = deferred()
    const order: string[] = []

    const firstSave = status.enqueueSave(async () => {
      order.push('first:start')
      await first.promise
      order.push('first:end')
    }, 'Info.Notes')
    const secondSave = status.enqueueSave(async () => {
      order.push('second:start')
      await second.promise
    }, 'Info.Account')
    expect(status.pendingCount()).toBe(2)
    expect(status.isSaving.value).toBe(true)
    expect(status.hasUnsavedChanges.value).toBe(true)
    expect(status.state.value).toBe('saving')
    expect(status.fieldStates['Info.Notes']).toBe('saving')

    first.resolve()
    await firstSave
    expect(status.pendingCount()).toBe(1)
    expect(status.isSaving.value).toBe(true)
    expect(status.hasUnsavedChanges.value).toBe(true)
    expect(status.fieldStates['Info.Notes']).toBe('saved')

    second.resolve()
    await secondSave
    // 串行：第二个在第一个写完之后才开始
    expect(order).toEqual(['first:start', 'first:end', 'second:start'])
    expect(status.pendingCount()).toBe(0)
    expect(status.isSaving.value).toBe(false)
    expect(status.hasUnsavedChanges.value).toBe(false)
    expect(status.state.value).toBe('saved')
    expect(status.fieldStates['Info.Account']).toBe('saved')
    expect(status.canLeave.value).toBe(true)
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

  it('写失败：状态是「失败已保留草稿」，禁止离开', async () => {
    const { scope, status } = setup()
    await expect(
      status.enqueueSave(async () => {
        throw new Error('写入失败')
      }, 'Info.Notes')
    ).rejects.toThrow('写入失败')

    expect(status.pendingCount()).toBe(0)
    expect(status.isSaving.value).toBe(false)
    expect(status.state.value).toBe('failed_draft_kept')
    expect(status.fieldStates['Info.Notes']).toBe('failed_draft_kept')
    expect(status.hasUnsavedChanges.value).toBe(true)
    expect(status.canLeave.value).toBe(false)
    scope.stop()
  })

  it('参数被拒 / 断线无法确认：分别是 rejected 与 unknown，都不显示为已保存', async () => {
    const { scope, status } = setup()
    await expect(
      status.enqueueSave(async () => {
        throw new AppRequestError('invalid_input')
      }, 'Info.Notes')
    ).rejects.toThrow()
    expect(status.state.value).toBe('rejected')

    await expect(
      status.enqueueSave(async () => {
        throw new AppRequestError('network_unavailable')
      }, 'Info.Account')
    ).rejects.toThrow()
    expect(status.state.value).toBe('unknown')
    expect(status.fieldStates['Info.Account']).toBe('unknown')
    expect(status.canLeave.value).toBe(false)
    scope.stop()
  })

  it('一次失败不阻塞后面的保存，成功后转回已保存并允许离开', async () => {
    const { scope, status } = setup()
    const failing = status.enqueueSave(async () => {
      throw new Error('写入失败')
    }, 'Info.Notes')
    const next = vi.fn(async () => undefined)
    const following = status.enqueueSave(next, 'Info.Notes')

    await expect(failing).rejects.toThrow('写入失败')
    await following
    expect(next).toHaveBeenCalledOnce()
    expect(status.state.value).toBe('saved')
    expect(status.fieldStates['Info.Notes']).toBe('saved')
    expect(status.canLeave.value).toBe(true)
    scope.stop()
  })
})
