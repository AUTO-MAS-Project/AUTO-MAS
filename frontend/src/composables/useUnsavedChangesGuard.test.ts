import { effectScope, ref } from 'vue'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { useUnsavedChangesGuard } from './useUnsavedChangesGuard'

/**
 * 这些测试在 vitest 默认 Node 环境下运行（仓库未安装 jsdom/happy-dom，
 * 见 frontend/src/views/PluginPageHost.test.ts:171 注释）。
 *
 * useUnsavedChangesGuard 内部对 `typeof window === 'undefined'` 做了 guard，
 * 因此在 Node 环境下 `bindBeforeUnload` 返回 no-op，`onMounted`/`onBeforeUnmount`
 * 不会触发 window.addEventListener。我们只测 guard 状态机与 saveError 逻辑；
 * window 事件部分由 composable 内部 guard 保证安全降级。
 */
describe('useUnsavedChangesGuard', () => {
  let scope: ReturnType<typeof effectScope> | null = null

  beforeEach(() => {
    scope = effectScope()
  })

  afterEach(() => {
    scope?.stop()
    scope = null
  })

  const createGuard = (
    overrides: {
      isDirty?: boolean
      isSaving?: boolean
      confirmMessage?: string
      onBeforeLeave?: () => void
    } = {}
  ) => {
    const isDirty = ref(overrides.isDirty ?? false)
    const isSaving = ref(overrides.isSaving ?? false)
    let guard: ReturnType<typeof useUnsavedChangesGuard> | null = null
    scope!.run(() => {
      guard = useUnsavedChangesGuard({
        isDirty,
        isSaving,
        confirmMessage: overrides.confirmMessage,
        onBeforeLeave: overrides.onBeforeLeave,
      })
    })
    return {
      isDirty,
      isSaving,
      ...(guard as unknown as ReturnType<typeof useUnsavedChangesGuard>),
    }
  }

  it('shouldGuard is false when not dirty', () => {
    const { shouldGuard } = createGuard({ isDirty: false })
    expect(shouldGuard.value).toBe(false)
  })

  it('shouldGuard is false when dirty but saving', () => {
    const { shouldGuard } = createGuard({ isDirty: true, isSaving: true })
    expect(shouldGuard.value).toBe(false)
  })

  it('shouldGuard is true only when dirty and not saving', () => {
    const { shouldGuard } = createGuard({ isDirty: true, isSaving: false })
    expect(shouldGuard.value).toBe(true)
  })

  it('confirmLeave returns true when no guard needed', () => {
    const { confirmLeave } = createGuard({ isDirty: false })
    expect(confirmLeave()).toBe(true)
  })

  it('confirmLeave returns false and calls onBeforeLeave when guard needed', () => {
    const onBeforeLeave = vi.fn()
    const { confirmLeave } = createGuard({ isDirty: true, isSaving: false, onBeforeLeave })
    expect(confirmLeave()).toBe(false)
    expect(onBeforeLeave).toHaveBeenCalledOnce()
  })

  it('confirmLeaveNow temporarily disables guard; cancelLeave re-enables', () => {
    const { shouldGuard, confirmLeave, confirmLeaveNow, cancelLeave } = createGuard({
      isDirty: true,
      isSaving: false,
    })
    expect(shouldGuard.value).toBe(true)
    expect(confirmLeave()).toBe(false)

    confirmLeaveNow()
    expect(shouldGuard.value).toBe(false)
    expect(confirmLeave()).toBe(true)

    cancelLeave()
    expect(shouldGuard.value).toBe(true)
    expect(confirmLeave()).toBe(false)
  })

  it('setSaveError / clearSaveError manage saveError ref', () => {
    const { saveError, setSaveError, clearSaveError } = createGuard()
    expect(saveError.value).toBe('')
    setSaveError('网络错误：连接超时')
    expect(saveError.value).toBe('网络错误：连接超时')
    // 保存错误不应影响 isDirty（保留输入由调用方控制 modelValue，guard 不清空）
    clearSaveError()
    expect(saveError.value).toBe('')
  })

  it('setSaveError coerces non-string to string', () => {
    const { saveError, setSaveError } = createGuard()
    setSaveError(123 as any)
    expect(saveError.value).toBe('123')
    // 实现：String(message ?? '')，null/undefined 归一为空串
    setSaveError(null as any)
    expect(saveError.value).toBe('')
    setSaveError(undefined as any)
    expect(saveError.value).toBe('')
    setSaveError({ toString: () => 'obj-string' } as any)
    expect(saveError.value).toBe('obj-string')
  })

  it('bindBeforeUnload safely returns no-op when window is undefined (Node env)', () => {
    // 在 Node 环境下，composable 内部 guard 应返回 no-op unbind，不抛错
    const { bindBeforeUnload } = createGuard({ isDirty: true, isSaving: false })
    const unbind = bindBeforeUnload()
    expect(typeof unbind).toBe('function')
    // 调用 unbind 不应抛错
    expect(() => unbind()).not.toThrow()
  })

  it('bindBeforeUnload registers and unregisters window.beforeunload handler when window exists', () => {
    // 模拟 window 存在的环境（如 jsdom）
    const originalWindow = (globalThis as any).window
    const fakeWindow = {
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }
    ;(globalThis as any).window = fakeWindow
    try {
      const { bindBeforeUnload } = createGuard({ isDirty: true, isSaving: false })
      const unbind = bindBeforeUnload()
      expect(fakeWindow.addEventListener).toHaveBeenCalledWith('beforeunload', expect.any(Function))
      unbind()
      expect(fakeWindow.removeEventListener).toHaveBeenCalledWith(
        'beforeunload',
        expect.any(Function)
      )
    } finally {
      // 恢复
      if (originalWindow === undefined) {
        delete (globalThis as any).window
      } else {
        ;(globalThis as any).window = originalWindow
      }
    }
  })

  it('beforeunload handler sets returnValue only when shouldGuard is true (with mocked window)', () => {
    const originalWindow = (globalThis as any).window
    const listeners: Record<string, ((event: any) => void) | undefined> = {}
    const fakeWindow = {
      addEventListener: vi.fn((name: string, handler: (event: any) => void) => {
        listeners[name] = handler
      }),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn((event: any) => {
        const handler = listeners['beforeunload']
        if (handler) {
          handler(event)
        }
        return true
      }),
    }
    ;(globalThis as any).window = fakeWindow
    try {
      const { isDirty, bindBeforeUnload } = createGuard({ isDirty: false, isSaving: false })
      const unbind = bindBeforeUnload()
      const event = {
        preventDefault: vi.fn(),
        returnValue: '',
      }

      // 不 dirty：不拦截
      ;(fakeWindow.dispatchEvent as any)(event)
      expect(event.preventDefault).not.toHaveBeenCalled()
      expect(event.returnValue).toBe('')

      // dirty：拦截
      isDirty.value = true
      ;(fakeWindow.dispatchEvent as any)(event)
      expect(event.preventDefault).toHaveBeenCalled()
      expect(event.returnValue).not.toBe('')

      unbind()
    } finally {
      if (originalWindow === undefined) {
        delete (globalThis as any).window
      } else {
        ;(globalThis as any).window = originalWindow
      }
    }
  })

  it('saveError 保留输入：guard 不会清空 modelValue（由调用方控制）', () => {
    // guard 仅暴露 saveError 状态；modelValue 不在 guard 职责内。
    // 调用方应在保存失败时不调用 emit('update:modelValue', {})，从而保留输入。
    const { saveError, setSaveError } = createGuard()
    setSaveError('保存失败：服务器 500')
    // guard 不持有 modelValue，无法清空；保留输入由调用方保证
    expect(saveError.value).toBe('保存失败：服务器 500')
  })
})
