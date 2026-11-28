import { effectScope, ref } from 'vue'
import { describe, expect, it, vi } from 'vite-plus/test'
import { useModalCloseGuard } from './useModalCloseGuard'

function createDeferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(r => {
    resolve = r
  })
  return { promise, resolve }
}

describe('useModalCloseGuard', () => {
  it('旧确认返回时不会关闭重新打开的新窗口', async () => {
    const scope = effectScope()
    const open = ref(true)
    const dirty = ref(true)
    const submitting = ref(false)
    const firstConfirm = createDeferred<boolean>()
    const confirmDiscard = vi.fn(() => firstConfirm.promise)
    const onClose = vi.fn(() => {
      open.value = false
    })

    const guard = scope.run(() =>
      useModalCloseGuard({
        open,
        dirty: () => dirty.value,
        submitting: () => submitting.value,
        confirmDiscard,
        onClose,
      })
    )!

    const firstClose = guard.requestClose()
    expect(confirmDiscard).toHaveBeenCalledTimes(1)

    // 等确认期间关闭旧编辑并打开新一份编辑
    open.value = false
    open.value = true

    firstConfirm.resolve(true)
    await expect(firstClose).resolves.toBe(false)
    expect(open.value).toBe(true)
    expect(onClose).not.toHaveBeenCalled()

    scope.stop()
  })

  it('等确认期间开始提交时，旧确认不会关闭正在保存的弹窗', async () => {
    const scope = effectScope()
    const open = ref(true)
    const submitting = ref(false)
    const deferred = createDeferred<boolean>()
    const onClose = vi.fn(() => {
      open.value = false
    })

    const guard = scope.run(() =>
      useModalCloseGuard({
        open,
        dirty: () => true,
        submitting: () => submitting.value,
        confirmDiscard: () => deferred.promise,
        onClose,
      })
    )!

    const pending = guard.requestClose()
    submitting.value = true
    deferred.resolve(true)

    await expect(pending).resolves.toBe(false)
    expect(open.value).toBe(true)
    expect(onClose).not.toHaveBeenCalled()

    scope.stop()
  })

  it('连续触发关闭共用同一次待决确认，确认后仅关闭一次', async () => {
    const scope = effectScope()
    const open = ref(true)
    const deferred = createDeferred<boolean>()
    const confirmDiscard = vi.fn(() => deferred.promise)
    const onClose = vi.fn(() => {
      open.value = false
    })

    const guard = scope.run(() =>
      useModalCloseGuard({
        open,
        dirty: () => true,
        submitting: () => false,
        confirmDiscard,
        onClose,
      })
    )!

    const p1 = guard.requestClose()
    const p2 = guard.requestClose()
    expect(p1).toBe(p2)
    expect(confirmDiscard).toHaveBeenCalledTimes(1)

    deferred.resolve(true)
    await expect(Promise.all([p1, p2])).resolves.toEqual([true, true])
    expect(open.value).toBe(false)
    expect(onClose).toHaveBeenCalledTimes(1)

    scope.stop()
  })

  it('取消确认后解除待决锁，再次关闭可重新弹出确认；卸载后旧确认不触发关闭', async () => {
    const scope = effectScope()
    const open = ref(true)
    const first = createDeferred<boolean>()
    const second = createDeferred<boolean>()
    const confirmDiscard = vi
      .fn<() => Promise<boolean>>()
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise)
    const onClose = vi.fn(() => {
      open.value = false
    })

    const guard = scope.run(() =>
      useModalCloseGuard({
        open,
        dirty: () => true,
        submitting: () => false,
        confirmDiscard,
        onClose,
      })
    )!

    const p1 = guard.requestClose()
    first.resolve(false)
    await expect(p1).resolves.toBe(false)
    expect(open.value).toBe(true)

    const p2 = guard.requestClose()
    expect(confirmDiscard).toHaveBeenCalledTimes(2)
    scope.stop()
    second.resolve(true)
    await expect(p2).resolves.toBe(false)
    expect(onClose).not.toHaveBeenCalled()
  })
})
