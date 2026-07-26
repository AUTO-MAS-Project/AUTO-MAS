/**
 * UserEdit / ScriptEdit 共享 helper（Lane 06 任务书第 5 条）。
 *
 * 提取 10 组 UserEdit + 10 组 ScriptEdit 中真实重复的逻辑：
 * - `useFieldSave`：UserEdit 的「字段级 @blur 保存」模式（7/10 编辑器同构）。
 * - `useCategoryChange`：ScriptEdit 的 `handleChange(category, key, value)` 模式（6/10 编辑器同构）。
 * - `useDirtyTracker`：配合 `useUnsavedChangesGuard` 的脏状态管理。
 * - `useEditorLifecycle`：`onMounted(loadScript + subscribe)` / `onBeforeUnmount(unsubscribe)` 通用编排。
 * - `buildNestedPatch`：把 `'Info.Name'` 这样的点路径转成 `{ Info: { Name: value } }`。
 *
 * 设计原则（与任务书一致）：
 * - 不抹平专项编辑器差异：HSR 的 `FIELDS_REQUIRE_REFRESH_AFTER_SAVE` 作为可选配置透出，
 *   不内建到 composable 中。
 * - 不强行合并 schema 系（Generic/Plugin）与静态表单系：本 composable 仅服务静态表单系，
 *   schema 系继续走 `useSchemaActionRunner` + `SchemaForm`。
 * - 不引入新依赖；使用现有 `useUserApi` / `useScriptApi` / `useScriptRegistryApi`。
 * - 调用方仍拥有 `isInitializing` / `isSaving` ref，本 composable 通过闭包读取。
 */

import { onBeforeUnmount, onMounted, ref, type Ref } from 'vue'

/** 读取 Ref 或 getter 为值。 */
const readRef = <T>(value: Ref<T> | (() => T)): T =>
  typeof value === 'function' ? (value as () => T)() : value.value

/**
 * 把点路径（如 `Info.Name`）转换为嵌套对象（如 `{ Info: { Name: value } }`）。
 *
 * 来源：`SRCUserEdit.vue:223-232`、`MAAUserEdit.vue`、`MaaEndUserEdit.vue` 等同构实现。
 * 空路径返回空对象。中间节点自动创建为空对象（不覆盖已有对象）。
 */
export const buildNestedPatch = (dottedKey: string, value: unknown): Record<string, any> => {
  if (!dottedKey) {
    return {}
  }
  const parts = dottedKey.split('.')
  const root: Record<string, any> = {}
  let current: Record<string, any> = root
  for (let i = 0; i < parts.length - 1; i++) {
    current[parts[i]] = {}
    current = current[parts[i]]
  }
  current[parts[parts.length - 1]] = value
  return root
}

/** Logger 类型：与 `window.electronAPI.getLogger(name)` 返回值兼容。 */
export type EditorLogger = {
  debug: (...args: any[]) => void
  info: (...args: any[]) => void
  warn: (...args: any[]) => void
  error: (...args: any[]) => void
}

/** 创建或获取命名 logger；window.electronAPI 不可用时退化为 no-op。 */
export const useEditorLogger = (name: string): EditorLogger => {
  if (typeof window !== 'undefined' && window.electronAPI && window.electronAPI.getLogger) {
    return window.electronAPI.getLogger(name)
  }
  const noop = () => {}
  return { debug: noop, info: noop, warn: noop, error: noop }
}

// ============================================================
// useFieldSave
// ============================================================

export interface UseFieldSaveOptions {
  /** 当前是否正在初始化（加载中）；为 true 时跳过保存。 */
  isInitializing: Ref<boolean> | (() => boolean)
  /** 当前是否正在保存；为 true 时跳过保存（避免重入）。 */
  isSaving: Ref<boolean> | (() => boolean)
  /**
   * 实际执行保存的函数。
   * 入参为 `buildNestedPatch(key, value)` 的结果。
   * 返回 true 表示保存成功。
   */
  save: (patch: Record<string, any>) => Promise<boolean>
  /** 日志器；通常由 `useEditorLogger(name)` 获取。 */
  logger: EditorLogger
  /** 保存成功后回调（如 HSR 的「保存后回拉」语义）。 */
  onAfterSave?: (key: string, value: unknown) => void | Promise<void>
  /** 保存失败回调；用于在 UI 上展示错误（不清空 modelValue）。 */
  onError?: (errorMsg: string, key: string) => void
  /** 脏状态追踪器；保存成功 → markClean，保存失败 → markDirty。 */
  dirtyTracker?: ReturnType<typeof useDirtyTracker>
  /** 是否在保存前 markDirty；默认 true（适用于「字段级立即保存但可能失败」模型）。 */
  markDirtyBeforeSave?: boolean
}

export interface UseFieldSaveReturn {
  /** 保存中状态（响应式）。调用方应使用此 ref 绑定 UI loading。 */
  isSaving: Ref<boolean>
  /**
   * 保存单个字段。
   *
   * 与 `SRCUserEdit.vue:205` / `MAAUserEdit.vue:550` 等同构：
   * - 初始化中或保存中时跳过。
   * - 用 `buildNestedPatch` 构造嵌套 patch。
   * - 成功后调用 `onAfterSave` 与 `markClean`。
   * - 失败时调用 `onError` 与 `markDirty`，不清空 modelValue（由调用方控制）。
   */
  handleFieldSave: (key: string, value: unknown) => Promise<void>
}

/**
 * UserEdit 字段级保存 composable。
 *
 * 复用来源（observed）：
 * - `views/EditView/User/SRCUserEdit.vue:205-245`
 * - `views/EditView/User/MAAUserEdit.vue:550`
 * - `views/EditView/User/MaaEndUserEdit.vue`（同构）
 * - `views/EditView/User/GeneralUserEdit.vue:106`
 * - `views/EditView/User/MaaFWUserEdit.vue:711`
 * - `views/EditView/User/OkScriptUserEdit.vue:434`
 * - `views/EditView/User/OkwwUserEdit.vue:483`
 */
export const useFieldSave = (options: UseFieldSaveOptions): UseFieldSaveReturn => {
  const {
    isInitializing,
    isSaving: isSavingRefOrGetter,
    save,
    logger,
    onAfterSave,
    onError,
    dirtyTracker,
    markDirtyBeforeSave = true,
  } = options

  // 内部维护一个 isSaving ref，与外部 ref 双向同步。
  // 调用方可能传入 ref 或 getter；这里统一为 ref。
  const isSavingInternal = ref(false)

  const handleFieldSave = async (key: string, value: unknown) => {
    if (readRef(isInitializing) || readRef(isSavingRefOrGetter) || isSavingInternal.value) {
      logger.debug(
        `跳过保存: 初始化=${readRef(isInitializing)}, 保存中=${readRef(isSavingRefOrGetter)}`
      )
      return
    }

    if (markDirtyBeforeSave) {
      dirtyTracker?.markDirty()
    }

    isSavingInternal.value = true
    // 同步外部 ref（如果传入的是 ref）
    if (typeof isSavingRefOrGetter !== 'function') {
      isSavingRefOrGetter.value = true
    }

    try {
      const patch = buildNestedPatch(key, value)
      logger.debug(`保存字段: ${key} = ${JSON.stringify(value)}`)
      const success = await save(patch)
      if (success) {
        logger.info(`字段已保存: ${key}`)
        dirtyTracker?.markClean()
        await onAfterSave?.(key, value)
      } else {
        // save 返回 false 表示业务失败（如后端校验不通过）；保留输入，标记 dirty。
        dirtyTracker?.markDirty()
        onError?.('保存失败', key)
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`保存字段失败: ${errorMsg}`)
      dirtyTracker?.markDirty()
      onError?.(errorMsg, key)
    } finally {
      isSavingInternal.value = false
      if (typeof isSavingRefOrGetter !== 'function') {
        isSavingRefOrGetter.value = false
      }
    }
  }

  return {
    isSaving: isSavingInternal,
    handleFieldSave,
  }
}

// ============================================================
// useCategoryChange
// ============================================================

export interface UseCategoryChangeOptions {
  /** Script ID。 */
  scriptId: string
  /** 当前是否正在初始化；为 true 时跳过保存。 */
  isInitializing: Ref<boolean> | (() => boolean)
  /** 当前是否正在保存；为 true 时跳过保存。 */
  isSaving: Ref<boolean> | (() => boolean)
  /**
   * 实际执行保存的函数。
   * 入参为 `{ [category]: { [key]: value } }`。
   */
  updateScript: (id: string, patch: Record<string, Record<string, unknown>>) => Promise<boolean>
  /** 日志器。 */
  logger: EditorLogger
  /**
   * 需要在保存后回拉（refreshScript）的字段集合（点路径 `${category}.${key}`）。
   *
   * 来源：`HSRScriptEdit.vue:639-644` 的 `FIELDS_REQUIRE_REFRESH_AFTER_SAVE`。
   * 用于 DPAPI 加解密、路径规范化等后端语义化校正。
   * 其他编辑器可不传。
   */
  fieldsRequireRefresh?: Set<string>
  /** 当命 `fieldsRequireRefresh` 时调用的回拉函数。 */
  refreshScript?: () => Promise<void>
  /** 保存失败回调。 */
  onError?: (errorMsg: string, category: string, key: string) => void
  /** 脏状态追踪器。 */
  dirtyTracker?: ReturnType<typeof useDirtyTracker>
}

export interface UseCategoryChangeReturn {
  /** 保存中状态。 */
  isSaving: Ref<boolean>
  /**
   * 保存单个 category.key 变更。
   *
   * 与 `HSRScriptEdit.vue:646` / `MAAScriptEdit.vue` / `MaaEndScriptEdit.vue:468` 等同构。
   */
  handleChange: (category: string, key: string, value: unknown) => Promise<void>
}

/**
 * ScriptEdit 分类变更保存 composable。
 *
 * 复用来源（observed）：
 * - `views/EditView/Script/HSRScriptEdit.vue:646-662`（含 fieldsRequireRefresh）
 * - `views/EditView/Script/MAAScriptEdit.vue`
 * - `views/EditView/Script/MaaEndScriptEdit.vue:468`
 * - `views/EditView/Script/SRCScriptEdit.vue:302`
 * - `views/EditView/Script/OkScriptScriptEdit.vue:512`
 * - `views/EditView/Script/OkwwScriptEdit.vue:404`（saveScriptPatch 局部函数）
 */
export const useCategoryChange = (options: UseCategoryChangeOptions): UseCategoryChangeReturn => {
  const {
    scriptId,
    isInitializing,
    isSaving: isSavingRefOrGetter,
    updateScript,
    logger,
    fieldsRequireRefresh,
    refreshScript,
    onError,
    dirtyTracker,
  } = options

  const isSavingInternal = ref(false)

  const handleChange = async (category: string, key: string, value: unknown) => {
    if (readRef(isInitializing) || readRef(isSavingRefOrGetter) || isSavingInternal.value) {
      return
    }

    dirtyTracker?.markDirty()
    isSavingInternal.value = true
    if (typeof isSavingRefOrGetter !== 'function') {
      isSavingRefOrGetter.value = true
    }

    try {
      const updateData: Record<string, Record<string, unknown>> = {
        [category]: { [key]: value },
      }
      const success = await updateScript(scriptId, updateData)
      if (!success) {
        dirtyTracker?.markDirty()
        onError?.('保存失败', category, key)
        return
      }
      logger.info(`配置已保存: ${category}.${key}`)
      dirtyTracker?.markClean()

      if (fieldsRequireRefresh && refreshScript) {
        if (fieldsRequireRefresh.has(`${category}.${key}`)) {
          await refreshScript()
        }
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`保存失败: ${errorMsg}`)
      dirtyTracker?.markDirty()
      onError?.(errorMsg, category, key)
    } finally {
      isSavingInternal.value = false
      if (typeof isSavingRefOrGetter !== 'function') {
        isSavingRefOrGetter.value = false
      }
    }
  }

  return {
    isSaving: isSavingInternal,
    handleChange,
  }
}

// ============================================================
// useDirtyTracker
// ============================================================

export interface UseDirtyTrackerReturn {
  /** 是否存在未保存更改。 */
  hasUnsavedChanges: Ref<boolean>
  /** 标记为脏。 */
  markDirty: () => void
  /** 标记为干净。 */
  markClean: () => void
  /** 重置为干净（与 markClean 等价，语义上用于 onMounted 初始化）。 */
  reset: () => void
  /** 当前是否脏（getter，便于传给 useUnsavedChangesGuard）。 */
  isDirty: () => boolean
}

/**
 * 脏状态追踪器。
 *
 * 复用来源（observed）：
 * - `composables/useMaaFWScriptConfig.ts:141,379,386`
 * - `views/EditView/User/MaaFWUserEdit.vue:159,713,737`
 *
 * 设计：保持轻量；不与 `useUnsavedChangesGuard` 强耦合，由调用方把 `isDirty` 传入。
 * 语义：保存失败后保持 dirty；保存成功后 markClean；用户输入触发 markDirty。
 */
export const useDirtyTracker = (): UseDirtyTrackerReturn => {
  const hasUnsavedChanges = ref(false)
  const markDirty = () => {
    hasUnsavedChanges.value = true
  }
  const markClean = () => {
    hasUnsavedChanges.value = false
  }
  const reset = () => {
    hasUnsavedChanges.value = false
  }
  const isDirty = () => hasUnsavedChanges.value
  return { hasUnsavedChanges, markDirty, markClean, reset, isDirty }
}

// ============================================================
// useEditorLifecycle
// ============================================================

export interface EditorSubscription {
  /** 订阅函数；返回订阅 ID（用于取消）。 */
  subscribe: () => string | Promise<string>
  /** 取消订阅函数。 */
  unsubscribe: (id: string) => void
}

export interface UseEditorLifecycleOptions {
  /** 挂载时执行（通常为 loadScript + subscribe）。 */
  onMount: () => Promise<void> | void
  /** 卸载时执行（通常为 unsubscribe + removeEventListener）。 */
  onUnmount?: () => void
  /** 可选订阅列表；composable 自动管理 subscribe / unsubscribe。 */
  subscriptions?: EditorSubscription[]
}

/**
 * 编辑器生命周期编排。
 *
 * 复用来源（observed）：
 * - `views/EditView/Script/MaaFWScriptEdit.vue:274-278`
 * - `views/EditView/Script/HSRScriptEdit.vue:575`
 * - `views/EditView/Script/PluginScriptEdit.vue:118`
 * - `views/EditView/Script/MaaEndScriptEdit.vue:395`
 *
 * 不强制要求所有编辑器使用；仅服务有 onMounted/onBeforeUnmount 共同模式的编辑器。
 */
export const useEditorLifecycle = (options: UseEditorLifecycleOptions): void => {
  const { onMount, onUnmount, subscriptions } = options
  const subscriptionIds: Array<{ unsubscribe: (id: string) => void; id: string }> = []

  onMounted(async () => {
    // 先 subscribe，再 onMount（onMount 内部可能依赖已订阅的 snapshot）。
    if (subscriptions) {
      for (const sub of subscriptions) {
        try {
          const id = await sub.subscribe()
          subscriptionIds.push({ unsubscribe: sub.unsubscribe, id })
        } catch (error) {
          // 单个订阅失败不阻塞其他订阅与 onMount
          console.warn('[useEditorLifecycle] subscribe failed:', error)
        }
      }
    }
    try {
      await onMount()
    } catch (error) {
      console.error('[useEditorLifecycle] onMount failed:', error)
    }
  })

  onBeforeUnmount(() => {
    // 先 onUnmount（可能需要读取订阅数据），再 unsubscribe
    try {
      onUnmount?.()
    } catch (error) {
      console.warn('[useEditorLifecycle] onUnmount failed:', error)
    }
    for (const { unsubscribe, id } of subscriptionIds) {
      try {
        unsubscribe(id)
      } catch (error) {
        console.warn('[useEditorLifecycle] unsubscribe failed:', error)
      }
    }
    subscriptionIds.length = 0
  })
}
