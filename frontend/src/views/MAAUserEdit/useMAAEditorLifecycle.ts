import { computed, nextTick, onBeforeUnmount, onUnmounted, ref, type Ref } from 'vue'
import { onBeforeRouteLeave, useRouter } from 'vue-router'
import { registerAppCloseGuard } from '@/composables/appCloseGuards'

interface EditorLifecycleOptions {
  pageRef: Ref<HTMLElement | undefined>
  canStart: () => boolean
  flushEdits: () => Promise<boolean>
  waitForSaves: () => Promise<boolean>
  flushImmediateEdits: () => void
  hasPendingEdits: () => boolean
  disposeEdits: () => void
  startSession: (taskId: string, viewOnly?: boolean) => Promise<boolean>
  stopSession: (keepOnFailure?: boolean) => Promise<boolean>
  backup: () => Promise<void>
  onSaveError: (error: unknown) => void
  onStopFailure: () => void
  onUnloadBlocked: () => void
}

// 保存、恢复、会话启动和退出共享一个页面生命周期，不让旧操作跨过配置恢复边界。
export function useMAAEditorLifecycle(options: EditorLifecycleOptions) {
  const preparingSession = ref(false)
  const restoringConfig = ref(false)
  const leavingPage = ref(false)
  const editorBusy = computed(
    () => preparingSession.value || restoringConfig.value || leavingPage.value
  )
  let active = true
  let generation = 0
  let operationPromise: Promise<boolean> | null = null
  let leavePromise: Promise<boolean> | null = null
  let cleanupPromise: Promise<void> | null = null
  let preparedToLeave = false
  const pendingEdits = new Set<Promise<unknown>>()

  const trackEdit = <T>(edit: () => Promise<T>): Promise<T> => {
    const pending = edit().finally(() => pendingEdits.delete(pending))
    pendingEdits.add(pending)
    return pending
  }

  const blurCurrentInput = () => {
    const focused = document.activeElement
    if (focused instanceof HTMLElement && options.pageRef.value?.contains(focused)) focused.blur()
  }

  const flushPendingEdits = async (): Promise<boolean> => {
    blurCurrentInput()
    await nextTick()
    try {
      // 基建导入等直接写配置的操作也必须完成，才能恢复、启动或退出。
      while (pendingEdits.size > 0) await Promise.all([...pendingEdits])
      return await options.flushEdits()
    } catch (error) {
      options.onSaveError(error)
      return false
    }
  }

  const isCurrent = (version: number) => active && version === generation && options.canStart()

  const startPreparedSession = async (taskId: string, viewOnly: boolean, version: number) => {
    if (!isCurrent(version)) return false
    const started = await options.startSession(taskId, viewOnly)
    // 不能撤销已发出的启动请求，迟到会话必须停止；停止请求由会话层共享。
    if (!active || version !== generation) {
      if (!(await options.stopSession(true))) options.onStopFailure()
      return false
    }
    return started
  }

  const startConfiguration = (taskId: string): Promise<boolean> => {
    if (!active || editorBusy.value || !options.canStart()) return Promise.resolve(false)
    preparingSession.value = true
    const version = ++generation
    operationPromise = (async () => {
      try {
        if (!(await flushPendingEdits())) return false
        return await startPreparedSession(taskId, false, version)
      } finally {
        preparingSession.value = false
        operationPromise = null
      }
    })()
    return operationPromise
  }

  const restoreConfiguration = (
    restore: () => Promise<boolean>,
    viewTaskId?: string
  ): Promise<boolean> => {
    if (!active || editorBusy.value || !options.canStart()) return Promise.resolve(false)
    restoringConfig.value = true
    const version = ++generation
    operationPromise = (async () => {
      try {
        // 必须在恢复请求前保存旧编辑；恢复以后绝不能再冲刷旧队列。
        if (!(await flushPendingEdits()) || !isCurrent(version)) return false
        if (!(await restore())) return false
        if (viewTaskId) return await startPreparedSession(viewTaskId, true, version)
        return true
      } finally {
        restoringConfig.value = false
        operationPromise = null
      }
    })()
    return operationPromise
  }

  const backupOnce = () => {
    cleanupPromise ??= options.backup()
    return cleanupPromise
  }

  const leaveEditor = (): Promise<boolean> => {
    if (leavePromise) return leavePromise
    leavingPage.value = true
    generation++
    leavePromise = (async () => {
      let prepared = false
      try {
        // 恢复请求已发出时，等待恢复与重载完成再退出；待启动会话则由代数取消。
        await operationPromise
        if (!(await flushPendingEdits())) return false
        if (!(await options.stopSession(true))) {
          options.onStopFailure()
          return false
        }
        await backupOnce()
        prepared = true
        preparedToLeave = true
        return true
      } catch (error) {
        options.onSaveError(error)
        return false
      } finally {
        // 成功后保持锁定到导航结束/窗口退出；其它路由守卫取消时再解除。
        if (!prepared) leavingPage.value = false
        leavePromise = null
      }
    })()
    return leavePromise
  }

  const cancelLeaving = () => {
    if (!active) return
    leavingPage.value = false
    preparedToLeave = false
    cleanupPromise = null
  }
  onBeforeRouteLeave(leaveEditor)
  const unregisterCloseGuard = registerAppCloseGuard(leaveEditor, cancelLeaving)
  const router = useRouter()
  const unregisterAfterEach = router.afterEach((_to, _from, failure) => {
    // afterEach 早于组件卸载：成功导航保留退出锁和归档结果，只有取消时解锁。
    if (failure) cancelLeaving()
  })
  const unregisterRouteError = router.onError(cancelLeaving)

  const handleBeforeUnload = (event: BeforeUnloadEvent) => {
    if (preparedToLeave) return
    // 刷新不能等待异步请求，只能同步提交失焦/防抖草稿并提示仍未保存。
    blurCurrentInput()
    options.flushImmediateEdits()
    if (editorBusy.value || pendingEdits.size > 0 || options.hasPendingEdits()) {
      event.preventDefault()
      event.returnValue = ''
      options.onUnloadBlocked()
    }
  }
  window.addEventListener('beforeunload', handleBeforeUnload)

  onBeforeUnmount(() => {
    blurCurrentInput()
    options.disposeEdits()
    active = false
    generation++
    unregisterCloseGuard()
    unregisterAfterEach()
    unregisterRouteError()
    window.removeEventListener('beforeunload', handleBeforeUnload)
  })
  onUnmounted(() => {
    void (async () => {
      await operationPromise
      await Promise.all([...pendingEdits])
      await options.waitForSaves()
      if (await options.stopSession(true)) await backupOnce()
    })().catch(options.onSaveError)
  })

  return {
    preparingSession,
    leavingPage,
    editorBusy,
    startConfiguration,
    restoreConfiguration,
    trackEdit,
  }
}
