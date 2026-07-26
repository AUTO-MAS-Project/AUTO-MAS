/**
 * useUserEditShared 单元测试（Lane 06 任务书第 6 条）。
 *
 * 在 vitest 默认 Node 环境下运行（仓库未安装 jsdom/happy-dom）；
 * 不渲染 Vue 组件，仅测试纯逻辑函数与 composable 的响应式行为。
 *
 * 注意：`useFieldSave`/`useCategoryChange`/`useEditorLifecycle` 内部使用 `onMounted`/
 * `onBeforeUnmount`，但在无组件实例的 Node 环境下 Vue 会发出 warn 但不阻塞执行
 * （lifecycle hooks 会被注册但不会自动触发）。测试中通过手动调用内部逻辑验证。
 */

import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import {
  buildNestedPatch,
  useEditorLogger,
  useFieldSave,
  useCategoryChange,
  useDirtyTracker,
  type EditorLogger,
} from '@/composables/useUserEditShared'

// ============================================================
// buildNestedPatch
// ============================================================

describe('buildNestedPatch', () => {
  it('单层 key 直接赋值', () => {
    expect(buildNestedPatch('name', 'alice')).toEqual({ name: 'alice' })
  })

  it('两层路径生成嵌套对象', () => {
    expect(buildNestedPatch('Info.Name', 'alice')).toEqual({ Info: { Name: 'alice' } })
  })

  it('三层路径生成深层嵌套对象', () => {
    expect(buildNestedPatch('a.b.c', 42)).toEqual({ a: { b: { c: 42 } } })
  })

  it('空路径返回空对象', () => {
    expect(buildNestedPatch('', 'value')).toEqual({})
  })

  it('value 为 null/undefined/对象/数组时原样保留', () => {
    expect(buildNestedPatch('Info.X', null)).toEqual({ Info: { X: null } })
    expect(buildNestedPatch('Info.X', undefined)).toEqual({ Info: { X: undefined } })
    expect(buildNestedPatch('Info.X', { nested: true })).toEqual({
      Info: { X: { nested: true } },
    })
    expect(buildNestedPatch('Info.X', [1, 2, 3])).toEqual({ Info: { X: [1, 2, 3] } })
  })

  it('与 SRCUserEdit.vue:223-232 原实现行为一致', () => {
    // 模拟 SRCUserEdit 的 handleFieldSave 中 buildNestedPatch 调用
    const key = 'Info.Name'
    const value = 'test-user'
    const result = buildNestedPatch(key, value)
    expect(result).toEqual({ Info: { Name: 'test-user' } })
    // 与 updateUser(scriptId, userId, userData) 的 userData 形态一致
  })
})

// ============================================================
// useEditorLogger
// ============================================================

describe('useEditorLogger', () => {
  it('window.electronAPI 不可用时退化为 no-op', () => {
    // Node 环境下 window 通常未定义
    const logger = useEditorLogger('test')
    expect(typeof logger.debug).toBe('function')
    expect(typeof logger.info).toBe('function')
    expect(typeof logger.warn).toBe('function')
    expect(typeof logger.error).toBe('function')
    // 不抛错
    expect(() => logger.debug('test')).not.toThrow()
    expect(() => logger.error('test')).not.toThrow()
  })

  it('window.electronAPI.getLogger 可用时使用真实 logger', () => {
    const originalWindow = (globalThis as any).window
    const fakeLogger = {
      debug: vi.fn(),
      info: vi.fn(),
      warn: vi.fn(),
      error: vi.fn(),
    }
    ;(globalThis as any).window = {
      electronAPI: { getLogger: vi.fn(() => fakeLogger) },
    }
    try {
      const logger = useEditorLogger('my-editor')
      expect(logger).toBe(fakeLogger)
      logger.info('hello')
      expect(fakeLogger.info).toHaveBeenCalledWith('hello')
    } finally {
      ;(globalThis as any).window = originalWindow
    }
  })
})

// ============================================================
// useDirtyTracker
// ============================================================

describe('useDirtyTracker', () => {
  it('初始 hasUnsavedChanges 为 false', () => {
    const { hasUnsavedChanges, isDirty } = useDirtyTracker()
    expect(hasUnsavedChanges.value).toBe(false)
    expect(isDirty()).toBe(false)
  })

  it('markDirty 后 hasUnsavedChanges 为 true', () => {
    const { hasUnsavedChanges, markDirty, isDirty } = useDirtyTracker()
    markDirty()
    expect(hasUnsavedChanges.value).toBe(true)
    expect(isDirty()).toBe(true)
  })

  it('markClean 后 hasUnsavedChanges 为 false', () => {
    const { hasUnsavedChanges, markDirty, markClean, isDirty } = useDirtyTracker()
    markDirty()
    markClean()
    expect(hasUnsavedChanges.value).toBe(false)
    expect(isDirty()).toBe(false)
  })

  it('reset 等价于 markClean', () => {
    const { hasUnsavedChanges, markDirty, reset, isDirty } = useDirtyTracker()
    markDirty()
    reset()
    expect(hasUnsavedChanges.value).toBe(false)
    expect(isDirty()).toBe(false)
  })

  it('isDirty getter 与 hasUnsavedChanges.value 始终一致', () => {
    const { hasUnsavedChanges, markDirty, markClean, isDirty } = useDirtyTracker()
    expect(isDirty()).toBe(hasUnsavedChanges.value)
    markDirty()
    expect(isDirty()).toBe(hasUnsavedChanges.value)
    markClean()
    expect(isDirty()).toBe(hasUnsavedChanges.value)
  })
})

// ============================================================
// useFieldSave
// ============================================================

const noopLogger: EditorLogger = {
  debug: () => {},
  info: () => {},
  warn: () => {},
  error: () => {},
}

describe('useFieldSave', () => {
  it('isInitializing=true 时跳过保存', async () => {
    const save = vi.fn().mockResolvedValue(true)
    const isInitializing = ref(true)
    const isSaving = ref(false)
    const { handleFieldSave } = useFieldSave({
      isInitializing,
      isSaving,
      save,
      logger: noopLogger,
    })
    await handleFieldSave('name', 'alice')
    expect(save).not.toHaveBeenCalled()
  })

  it('isSaving=true 时跳过保存（避免重入）', async () => {
    const save = vi.fn().mockResolvedValue(true)
    const isInitializing = ref(false)
    const isSaving = ref(true)
    const { handleFieldSave } = useFieldSave({
      isInitializing,
      isSaving,
      save,
      logger: noopLogger,
    })
    await handleFieldSave('name', 'alice')
    expect(save).not.toHaveBeenCalled()
  })

  it('正常保存成功：调用 save 并传入 buildNestedPatch 结果', async () => {
    const save = vi.fn().mockResolvedValue(true)
    const isInitializing = ref(false)
    const isSaving = ref(false)
    const onAfterSave = vi.fn()
    const { handleFieldSave } = useFieldSave({
      isInitializing,
      isSaving,
      save,
      logger: noopLogger,
      onAfterSave,
    })
    await handleFieldSave('Info.Name', 'alice')
    expect(save).toHaveBeenCalledWith({ Info: { Name: 'alice' } })
    expect(onAfterSave).toHaveBeenCalledWith('Info.Name', 'alice')
  })

  it('保存成功后 isSaving 自动复位', async () => {
    const save = vi.fn().mockResolvedValue(true)
    const isInitializing = ref(false)
    const isSaving = ref(false)
    const { handleFieldSave, isSaving: internalIsSaving } = useFieldSave({
      isInitializing,
      isSaving,
      save,
      logger: noopLogger,
    })
    const promise = handleFieldSave('name', 'alice')
    // 保存中
    // 等待完成
    await promise
    expect(internalIsSaving.value).toBe(false)
    expect(isSaving.value).toBe(false)
  })

  it('save 返回 false 时调用 onError 并保持 dirty', async () => {
    const save = vi.fn().mockResolvedValue(false)
    const onError = vi.fn()
    const dirtyTracker = useDirtyTracker()
    const isInitializing = ref(false)
    const isSaving = ref(false)
    const { handleFieldSave } = useFieldSave({
      isInitializing,
      isSaving,
      save,
      logger: noopLogger,
      onError,
      dirtyTracker,
    })
    await handleFieldSave('name', 'alice')
    expect(onError).toHaveBeenCalledWith('保存失败', 'name')
    expect(dirtyTracker.hasUnsavedChanges.value).toBe(true)
  })

  it('save 抛异常时调用 onError 并保持 dirty', async () => {
    const save = vi.fn().mockRejectedValue(new Error('网络错误'))
    const onError = vi.fn()
    const dirtyTracker = useDirtyTracker()
    const isInitializing = ref(false)
    const isSaving = ref(false)
    const { handleFieldSave } = useFieldSave({
      isInitializing,
      isSaving,
      save,
      logger: noopLogger,
      onError,
      dirtyTracker,
    })
    await handleFieldSave('name', 'alice')
    expect(onError).toHaveBeenCalledWith('网络错误', 'name')
    expect(dirtyTracker.hasUnsavedChanges.value).toBe(true)
  })

  it('保存前 markDirty（默认行为）', async () => {
    const save = vi.fn().mockResolvedValue(true)
    const dirtyTracker = useDirtyTracker()
    const isInitializing = ref(false)
    const isSaving = ref(false)
    const { handleFieldSave } = useFieldSave({
      isInitializing,
      isSaving,
      save,
      logger: noopLogger,
      dirtyTracker,
    })
    const promise = handleFieldSave('name', 'alice')
    // markDirtyBeforeSave 默认 true，应在 save 前标记脏
    expect(dirtyTracker.hasUnsavedChanges.value).toBe(true)
    await promise
    // 保存成功后 markClean
    expect(dirtyTracker.hasUnsavedChanges.value).toBe(false)
  })

  it('markDirtyBeforeSave=false 时不预先标记脏', async () => {
    const save = vi.fn().mockResolvedValue(true)
    const dirtyTracker = useDirtyTracker()
    const isInitializing = ref(false)
    const isSaving = ref(false)
    const { handleFieldSave } = useFieldSave({
      isInitializing,
      isSaving,
      save,
      logger: noopLogger,
      dirtyTracker,
      markDirtyBeforeSave: false,
    })
    await handleFieldSave('name', 'alice')
    // 未预先标记脏；保存成功后仍为 false
    expect(dirtyTracker.hasUnsavedChanges.value).toBe(false)
  })

  it('getter 形式的 isInitializing/isSaving 也能正确工作', async () => {
    const save = vi.fn().mockResolvedValue(true)
    let initializing = true
    let saving = false
    const { handleFieldSave } = useFieldSave({
      isInitializing: () => initializing,
      isSaving: () => saving,
      save,
      logger: noopLogger,
    })
    // 初始化中，跳过
    await handleFieldSave('name', 'alice')
    expect(save).not.toHaveBeenCalled()

    // 初始化完成
    initializing = false
    await handleFieldSave('name', 'alice')
    expect(save).toHaveBeenCalledWith({ name: 'alice' })
  })

  it('传入外部 isSaving ref 时同步更新', async () => {
    const save = vi.fn().mockResolvedValue(true)
    const isInitializing = ref(false)
    const isSaving = ref(false)
    const { handleFieldSave } = useFieldSave({
      isInitializing,
      isSaving,
      save,
      logger: noopLogger,
    })
    const promise = handleFieldSave('name', 'alice')
    // 外部 ref 应被同步为 true（保存中）
    expect(isSaving.value).toBe(true)
    await promise
    expect(isSaving.value).toBe(false)
  })
})

// ============================================================
// useCategoryChange
// ============================================================

describe('useCategoryChange', () => {
  it('isInitializing=true 时跳过保存', async () => {
    const updateScript = vi.fn().mockResolvedValue(true)
    const isInitializing = ref(true)
    const isSaving = ref(false)
    const { handleChange } = useCategoryChange({
      scriptId: 's1',
      isInitializing,
      isSaving,
      updateScript,
      logger: noopLogger,
    })
    await handleChange('Info', 'Name', 'alice')
    expect(updateScript).not.toHaveBeenCalled()
  })

  it('正常保存：调用 updateScript 并传入 { [category]: { [key]: value } }', async () => {
    const updateScript = vi.fn().mockResolvedValue(true)
    const isInitializing = ref(false)
    const isSaving = ref(false)
    const { handleChange } = useCategoryChange({
      scriptId: 's1',
      isInitializing,
      isSaving,
      updateScript,
      logger: noopLogger,
    })
    await handleChange('Info', 'Name', 'alice')
    expect(updateScript).toHaveBeenCalledWith('s1', { Info: { Name: 'alice' } })
  })

  it('save 返回 false 时调用 onError 并保持 dirty', async () => {
    const updateScript = vi.fn().mockResolvedValue(false)
    const onError = vi.fn()
    const dirtyTracker = useDirtyTracker()
    const isInitializing = ref(false)
    const isSaving = ref(false)
    const { handleChange } = useCategoryChange({
      scriptId: 's1',
      isInitializing,
      isSaving,
      updateScript,
      logger: noopLogger,
      onError,
      dirtyTracker,
    })
    await handleChange('Info', 'Name', 'alice')
    expect(onError).toHaveBeenCalledWith('保存失败', 'Info', 'Name')
    expect(dirtyTracker.hasUnsavedChanges.value).toBe(true)
  })

  it('save 抛异常时调用 onError 并保持 dirty', async () => {
    const updateScript = vi.fn().mockRejectedValue(new Error('500'))
    const onError = vi.fn()
    const dirtyTracker = useDirtyTracker()
    const isInitializing = ref(false)
    const isSaving = ref(false)
    const { handleChange } = useCategoryChange({
      scriptId: 's1',
      isInitializing,
      isSaving,
      updateScript,
      logger: noopLogger,
      onError,
      dirtyTracker,
    })
    await handleChange('Info', 'Name', 'alice')
    expect(onError).toHaveBeenCalledWith('500', 'Info', 'Name')
    expect(dirtyTracker.hasUnsavedChanges.value).toBe(true)
  })

  it('fieldsRequireRefresh 命中时调用 refreshScript', async () => {
    const updateScript = vi.fn().mockResolvedValue(true)
    const refreshScript = vi.fn().mockResolvedValue(undefined)
    const isInitializing = ref(false)
    const isSaving = ref(false)
    const { handleChange } = useCategoryChange({
      scriptId: 's1',
      isInitializing,
      isSaving,
      updateScript,
      logger: noopLogger,
      fieldsRequireRefresh: new Set(['Info.Name', 'M7A.Path']),
      refreshScript,
    })
    // 命中
    await handleChange('Info', 'Name', 'alice')
    expect(refreshScript).toHaveBeenCalledTimes(1)

    // 不命中
    refreshScript.mockClear()
    await handleChange('Info', 'Notes', 'note')
    expect(refreshScript).not.toHaveBeenCalled()
  })

  it('fieldsRequireRefresh 未提供时不调用 refreshScript（不抛错）', async () => {
    const updateScript = vi.fn().mockResolvedValue(true)
    const isInitializing = ref(false)
    const isSaving = ref(false)
    const { handleChange } = useCategoryChange({
      scriptId: 's1',
      isInitializing,
      isSaving,
      updateScript,
      logger: noopLogger,
    })
    await expect(handleChange('Info', 'Name', 'alice')).resolves.toBeUndefined()
  })

  it('fieldsRequireRefresh 提供但 refreshScript 未提供时不抛错', async () => {
    const updateScript = vi.fn().mockResolvedValue(true)
    const isInitializing = ref(false)
    const isSaving = ref(false)
    const { handleChange } = useCategoryChange({
      scriptId: 's1',
      isInitializing,
      isSaving,
      updateScript,
      logger: noopLogger,
      fieldsRequireRefresh: new Set(['Info.Name']),
      // refreshScript 未提供
    })
    await expect(handleChange('Info', 'Name', 'alice')).resolves.toBeUndefined()
  })

  it('与 HSRScriptEdit.vue:639-662 行为一致：FIELDS_REQUIRE_REFRESH_AFTER_SAVE 命中后回拉', async () => {
    // 模拟 HSR 的 FIELDS_REQUIRE_REFRESH_AFTER_SAVE = new Set([
    //   'Info.Name', 'M7A.Path', 'SRA.Path', 'Game.Path'
    // ])
    const FIELDS_REQUIRE_REFRESH_AFTER_SAVE = new Set([
      'Info.Name',
      'M7A.Path',
      'SRA.Path',
      'Game.Path',
    ])
    const updateScript = vi.fn().mockResolvedValue(true)
    const refreshScript = vi.fn().mockResolvedValue(undefined)
    const isInitializing = ref(false)
    const isSaving = ref(false)
    const { handleChange } = useCategoryChange({
      scriptId: 'hsr-1',
      isInitializing,
      isSaving,
      updateScript,
      logger: noopLogger,
      fieldsRequireRefresh: FIELDS_REQUIRE_REFRESH_AFTER_SAVE,
      refreshScript,
    })

    // 命中 Info.Name
    await handleChange('Info', 'Name', 'new-name')
    expect(refreshScript).toHaveBeenCalledTimes(1)

    // 命中 M7A.Path
    await handleChange('M7A', 'Path', '/path/to/m7a')
    expect(refreshScript).toHaveBeenCalledTimes(2)

    // 未命中 Info.Notes
    await handleChange('Info', 'Notes', 'note')
    expect(refreshScript).toHaveBeenCalledTimes(2)
  })

  it('保存成功后 markClean', async () => {
    const updateScript = vi.fn().mockResolvedValue(true)
    const dirtyTracker = useDirtyTracker()
    const isInitializing = ref(false)
    const isSaving = ref(false)
    const { handleChange } = useCategoryChange({
      scriptId: 's1',
      isInitializing,
      isSaving,
      updateScript,
      logger: noopLogger,
      dirtyTracker,
    })
    await handleChange('Info', 'Name', 'alice')
    expect(dirtyTracker.hasUnsavedChanges.value).toBe(false)
  })
})
