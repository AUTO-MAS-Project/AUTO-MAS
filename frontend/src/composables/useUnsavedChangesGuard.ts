/**
 * 表单未保存更改离开保护与保存失败输入保留。
 *
 * 对应 Lane 06 任务书第 4 条：
 * - 离开存在未保存更改的表单时必须保护（弹出确认；route 守卫；beforeunload）。
 * - 保存失败时保留用户输入并显示具体原因（不清空 modelValue；不跳转）。
 *
 * 设计原则：
 * - 不引入新依赖；使用 vue-router 4 的 onBeforeRouteLeave（可选）和原生 beforeunload。
 * - 调用方提供 isDirty 与 isSaving 状态；本 composable 仅负责守卫逻辑。
 * - 不在离开守卫中执行异步 IO；只做同步确认。
 * - 保存失败原因通过 saveError ref 暴露；调用方负责展示。
 */

import { computed, ref, onMounted, onBeforeUnmount, type Ref } from 'vue'

export interface UseUnsavedChangesGuardOptions {
  /** 是否存在未保存更改（响应式或函数）。 */
  isDirty: Ref<boolean> | (() => boolean)
  /** 是否正在保存（响应式或函数）；保存中不触发离开拦截。 */
  isSaving: Ref<boolean> | (() => boolean)
  /** 离开确认文案；默认“您有未保存的更改，确定要离开吗？”。 */
  confirmMessage?: string
  /** 离开前回调（同步；用于触发 visible 退出确认弹窗等）。 */
  onBeforeLeave?: () => void
}

const readRef = <T>(value: Ref<T> | (() => T)): T =>
  typeof value === 'function' ? (value as () => T)() : value.value

/**
 * 提供“未保存更改”离开守卫与保存错误状态。
 *
 * 用法：
 * ```ts
 * const { isDirty, isSaving, saveError, setSaveError, clearSaveError, bindBeforeUnload, leave } =
 *   useUnsavedChangesGuard({ isDirty, isSaving })
 * bindBeforeUnload()
 * ```
 *
 * - `bindBeforeUnload()` 在 onMounted 中注册 window.beforeunload；
 *   `onBeforeUnmount` 中自动清理。
 * - `leave()` 在调用方确认离开后调用，临时跳过守卫并执行跳转。
 * - 路由级守卫由调用方自行使用 `onBeforeRouteLeave` 调用 `confirmLeave` 实现。
 */
export const useUnsavedChangesGuard = (options: UseUnsavedChangesGuardOptions) => {
  const { isDirty, isSaving, confirmMessage, onBeforeLeave } = options

  /** 保存失败原因文案；空串表示无错误。 */
  const saveError = ref('')

  /** 内部标志：调用方已显式确认离开，下一次守卫应放行。 */
  const leavingConfirmed = ref(false)

  /** 当前是否处于“应拦截离开”状态。 */
  const shouldGuard = computed(
    () => !leavingConfirmed.value && readRef(isDirty) && !readRef(isSaving)
  )

  /** 设置保存错误；同时保证 isSaving 不被错误地置 false（由调用方控制）。 */
  const setSaveError = (message: string) => {
    saveError.value = typeof message === 'string' ? message : String(message ?? '')
  }

  /** 清空保存错误。 */
  const clearSaveError = () => {
    saveError.value = ''
  }

  /**
   * 路由级离开守卫。
   *
   * 调用方应在 `onBeforeRouteLeave((to, from, next) => next(confirmLeave()))` 中使用。
   * 返回 false 表示拦截，true 表示放行。
   */
  const confirmLeave = (): boolean => {
    if (!shouldGuard.value) {
      return true
    }
    onBeforeLeave?.()
    // 调用方可通过 onBeforeLeave 弹出确认框；这里返回 false 由调用方按用户选择继续。
    return false
  }

  /**
   * 用户在确认弹窗中点击“离开”后调用；临时跳过守卫。
   *
   * 调用方应在执行实际跳转前调用本函数。
   */
  const confirmLeaveNow = () => {
    leavingConfirmed.value = true
  }

  /**
   * 用户在确认弹窗中点击“留下”后调用；重置标志。
   */
  const cancelLeave = () => {
    leavingConfirmed.value = false
  }

  /** beforeunload 事件处理器。 */
  const handleBeforeUnload = (event: BeforeUnloadEvent) => {
    if (!shouldGuard.value) {
      return
    }
    event.preventDefault()
    event.returnValue = confirmMessage || '您有未保存的更改，确定要离开吗？'
    return event.returnValue
  }

  /** 注册 window.beforeunload；返回取消注册函数。 */
  const bindBeforeUnload = () => {
    if (typeof window === 'undefined' || typeof window.addEventListener !== 'function') {
      return () => {}
    }
    window.addEventListener('beforeunload', handleBeforeUnload)
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload)
    }
  }

  let unbindBeforeUnload: (() => void) | null = null

  onMounted(() => {
    unbindBeforeUnload = bindBeforeUnload()
  })

  onBeforeUnmount(() => {
    unbindBeforeUnload?.()
    unbindBeforeUnload = null
  })

  return {
    saveError,
    shouldGuard,
    setSaveError,
    clearSaveError,
    confirmLeave,
    confirmLeaveNow,
    cancelLeave,
    bindBeforeUnload,
  }
}
