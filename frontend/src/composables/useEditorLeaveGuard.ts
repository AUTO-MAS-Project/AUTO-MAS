import { onBeforeUnmount, ref, type Ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { registerAppCloseGuard } from '@/composables/appCloseGuards'

export type LeaveBlockReason = 'save_incomplete' | 'leave_rejected'

export interface EditorLeaveGuardOptions {
  /** 是否还有未落盘内容（在途保存 / 失败草稿 / 结果未知），用于原生关闭提示 */
  hasPending: () => boolean
  /** 等待并落盘所有在途保存；返回 false 表示仍有未落盘内容，禁止离开 */
  flush: () => Promise<boolean>
  /** 离开前的收尾（停原生会话、归档备份等）；返回 false 阻止离开 */
  onLeave?: () => Promise<boolean | void> | boolean | void
  /** 被阻止时提示用户 */
  onBlocked?: (reason: LeaveBlockReason) => void
}

/**
 * 编辑页统一离开守卫：路由离开、应用关闭、窗口关闭三条入口共用同一段落盘逻辑。
 *
 * - 路由离开（含页头「返回」按钮触发的 router.push）走 onBeforeRouteLeave；
 * - 应用关闭走既有 appCloseGuards 注册表，由 useAppLifecycle 的 prepareAppClose 等待；
 * - 原生窗口关闭（beforeunload）在仍有未落盘内容时拦截。
 *
 * 任何入口都先 await flush()：仍有未落盘内容一律不放行，不做「先离开再补写」。
 */
export function useEditorLeaveGuard(options: EditorLeaveGuardOptions): {
  leaving: Ref<boolean>
  confirmLeave: () => Promise<boolean>
} {
  const leaving = ref(false)
  let preparedToLeave = false

  const confirmLeave = async (): Promise<boolean> => {
    if (preparedToLeave) return true
    // 已经在处理离开（例如用户重复点击）：不重复触发落盘，也不放行
    if (leaving.value) return false

    leaving.value = true
    try {
      if (!(await options.flush())) {
        options.onBlocked?.('save_incomplete')
        return false
      }
      if (options.onLeave) {
        const result = await options.onLeave()
        if (result === false) {
          options.onBlocked?.('leave_rejected')
          return false
        }
      }
      preparedToLeave = true
      return true
    } finally {
      leaving.value = false
    }
  }

  const handleBeforeUnload = (event: BeforeUnloadEvent) => {
    if (preparedToLeave || !options.hasPending()) return
    event.preventDefault()
    event.returnValue = ''
  }

  window.addEventListener('beforeunload', handleBeforeUnload)
  const unregisterCloseGuard = registerAppCloseGuard(confirmLeave, () => {
    leaving.value = false
  })

  onBeforeRouteLeave(async () => await confirmLeave())

  onBeforeUnmount(() => {
    window.removeEventListener('beforeunload', handleBeforeUnload)
    unregisterCloseGuard()
  })

  return { leaving, confirmLeave }
}
