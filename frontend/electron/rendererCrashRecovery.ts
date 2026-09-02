/**
 * 渲染进程崩溃恢复决策。
 *
 * Electron 不会自动重建崩掉的渲染进程：`render-process-gone` 之后 BrowserWindow
 * 还在（托盘、显示/隐藏都正常），但里面的 frame 已经没了，用户看到的就是一个
 * 永远黑着的窗口，只能从任务管理器强杀。这里把「要不要重载」的判断抽成纯函数，
 * 副作用留在 main.ts。
 */

export interface RendererCrashInput {
  /** `render-process-gone` 事件的 details.reason。 */
  reason: string
  /** `render-process-gone` 事件的 details.exitCode。 */
  exitCode: number
  /** 应用正在退出时渲染进程消失属于正常拆卸，不做恢复。 */
  isQuitting: boolean
  /** 窗口已销毁时没有可重载的目标。 */
  isWindowDestroyed: boolean
  now: number
  /** 此前若干次崩溃的时间戳（毫秒）。 */
  previousCrashes: readonly number[]
}

export type RendererRecoveryAction = 'ignore' | 'reload' | 'give-up'

export interface RendererCrashDecision {
  action: RendererRecoveryAction
  /** 决策说明，直接写进日志与上报。 */
  detail: string
  /** 保留在统计窗口内的崩溃时间戳，供下一次决策使用。 */
  crashes: number[]
  /** 本次崩溃在统计窗口内是第几次。 */
  crashCount: number
}

/** 连续崩溃统计窗口：只有窗口期内的崩溃才算「反复崩溃」。 */
export const CRASH_WINDOW_MS = 5 * 60 * 1000

/** 统计窗口内最多自动重载几次，超出就停手，避免崩溃—重载死循环烧 CPU。 */
export const MAX_RELOAD_ATTEMPTS = 3

export function decideRendererRecovery(input: RendererCrashInput): RendererCrashDecision {
  const kept = input.previousCrashes.filter(at => input.now - at < CRASH_WINDOW_MS)

  // 正常退出不计入崩溃统计，否则退出流程会污染下一次启动的判断。
  if (input.reason === 'clean-exit') {
    return {
      action: 'ignore',
      detail: '渲染进程正常退出（clean-exit）',
      crashes: kept,
      crashCount: kept.length,
    }
  }

  const crashes = [...kept, input.now]
  const crashCount = crashes.length

  if (input.isQuitting) {
    return {
      action: 'ignore',
      detail: `应用正在退出，忽略渲染进程退出（reason=${input.reason}）`,
      crashes,
      crashCount,
    }
  }

  if (input.isWindowDestroyed) {
    return {
      action: 'give-up',
      detail: `窗口已销毁，无法重载（reason=${input.reason}）`,
      crashes,
      crashCount,
    }
  }

  if (crashCount > MAX_RELOAD_ATTEMPTS) {
    return {
      action: 'give-up',
      detail:
        `渲染进程 ${CRASH_WINDOW_MS / 1000}s 内第 ${crashCount} 次崩溃` +
        `（reason=${input.reason}, exitCode=${input.exitCode}），` +
        `超过 ${MAX_RELOAD_ATTEMPTS} 次自动重载上限，停止重载`,
      crashes,
      crashCount,
    }
  }

  return {
    action: 'reload',
    detail:
      `渲染进程异常退出（reason=${input.reason}, exitCode=${input.exitCode}），` +
      `第 ${crashCount}/${MAX_RELOAD_ATTEMPTS} 次自动重载`,
    crashes,
    crashCount,
  }
}
