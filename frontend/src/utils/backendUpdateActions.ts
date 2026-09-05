/**
 * 后端更新失败结局到界面动作的决策。
 *
 * 纯函数、不碰 window，便于单测。主进程已经在 `supportRequired` 里给出「重试已无意义」的
 * 判定（`retryable=false`、`INTERNAL_ERROR`、`contact-support`），这里只负责据此收口：
 * 不可重试时一个重试按钮都不给，改为提示携带日志反馈。
 */

import type { RuntimeUpdateOutcome, RuntimeUpdateRetryAction } from '@/types/electron'

export interface BackendUpdateActions {
  /** 可展示的重试入口；不可重试时为空。 */
  retryActions: RuntimeUpdateRetryAction[]
  /** 源码与依赖已就位（或取消后旧后端没拉起来），给「重新启动后端」。 */
  showRestartBackend: boolean
  /** 提示用户携带日志反馈。 */
  showContactSupport: boolean
}

export function resolveBackendUpdateActions(
  outcome: RuntimeUpdateOutcome | null | undefined
): BackendUpdateActions {
  if (!outcome || outcome.success) {
    return { retryActions: [], showRestartBackend: false, showContactSupport: false }
  }

  const showContactSupport = outcome.supportRequired === true
  return {
    retryActions: showContactSupport ? [] : [...(outcome.retryActions ?? [])],
    showRestartBackend: outcome.phase === 'restart',
    showContactSupport,
  }
}
