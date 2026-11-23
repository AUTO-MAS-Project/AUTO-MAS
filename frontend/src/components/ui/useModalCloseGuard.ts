import { onScopeDispose, watch, type Ref } from 'vue'

export interface ModalCloseGuardOptions {
  open: Ref<boolean>
  /** 编辑会话标识：父组件在同一更新轮次切换编辑对象时，靠它区分新旧会话 */
  sessionKey?: () => unknown
  dirty: () => boolean
  submitting: () => boolean
  confirmDiscard: () => Promise<boolean>
  onClose: () => void
}

/**
 * 弹窗关闭保护状态机。
 *
 * 每次打开或切换 sessionKey 分配独立会话序号并仅允许一个待决确认；
 * 确认结果返回时若已切换会话、窗口已关闭、已卸载或已进入提交态，则忽略旧确认。
 */
export function useModalCloseGuard(options: ModalCloseGuardOptions) {
  let sessionId = 0
  let disposed = false
  let pendingConfirm: { sessionId: number; promise: Promise<boolean> } | null = null

  const invalidateSession = () => {
    sessionId += 1
    pendingConfirm = null
  }

  // 使用 sync 刷新：在同一 tick 内切换 open 或 sessionKey 时立即使旧确认失效。
  watch([options.open, () => options.sessionKey?.()], invalidateSession, { flush: 'sync' })

  onScopeDispose(() => {
    disposed = true
    invalidateSession()
  })

  const requestClose = (): Promise<boolean> => {
    if (disposed || !options.open.value || options.submitting()) {
      return Promise.resolve(false)
    }

    if (!options.dirty()) {
      options.onClose()
      return Promise.resolve(true)
    }

    if (pendingConfirm && pendingConfirm.sessionId === sessionId) {
      return pendingConfirm.promise
    }

    const currentSession = sessionId
    const currentKey = options.sessionKey?.()
    const promise = (async () => {
      try {
        const confirmed = await options.confirmDiscard()
        if (
          !confirmed ||
          disposed ||
          sessionId !== currentSession ||
          !Object.is(options.sessionKey?.(), currentKey) ||
          !options.open.value ||
          options.submitting()
        ) {
          return false
        }
        options.onClose()
        return true
      } finally {
        if (pendingConfirm?.sessionId === currentSession) {
          pendingConfirm = null
        }
      }
    })()

    pendingConfirm = { sessionId: currentSession, promise }
    return promise
  }

  return { requestClose }
}
