import type { BrowserWindow, RenderProcessGoneDetails } from 'electron'
import { decideRendererRecovery, type RendererReloadResult } from '../rendererCrashRecovery'
import { beginMainFeature, mainCountBucket } from './featureAnalytics'
import { getLogger } from './logger'
import { beginMainRendererReload, captureMainRendererCrash } from './sentry'

export const RENDERER_RELOAD_TIMEOUT_MS = 30_000
const WM_ENDSESSION = 0x0016
const logger = getLogger('渲染进程恢复')

interface RendererRecoveryOptions {
  isQuitting(): boolean
  onRendererGone(): void
  onReload(): void
}

/** 一次重载只结算一次；窗口与系统退出均由主进程确认。 */
export function attachRendererRecovery(win: BrowserWindow, options: RendererRecoveryOptions) {
  let crashes: number[] = []
  let sessionEnding = false
  let pending: {
    loaded: boolean
    ready: boolean
    timer: ReturnType<typeof setTimeout>
    finish(result: Omit<RendererReloadResult, 'durationMs'>): void
  } | null = null

  const finishPending = (result: Omit<RendererReloadResult, 'durationMs'>) => {
    const attempt = pending
    if (!attempt) return
    pending = null
    clearTimeout(attempt.timer)
    attempt.finish(result)
  }
  const finishIfReady = () => {
    if (sessionEnding || options.isQuitting()) {
      finishPending({
        outcome: 'cancelled',
        resultKind: sessionEnding ? 'session_end' : 'app_quitting',
      })
    } else if (pending?.loaded && pending.ready) {
      finishPending({ outcome: 'success', resultKind: 'ready' })
    }
  }
  const endSession = () => {
    sessionEnding = true
    finishPending({ outcome: 'cancelled', resultKind: 'session_end' })
    logger.info('Windows 会话正在结束，停止渲染进程恢复')
  }
  win.on('query-session-end', endSession)
  win.on('session-end', endSession)
  if (process.platform === 'win32') {
    // 别的应用或用户可能取消关机；Electron 不暴露 WM_ENDSESSION(FALSE)。
    win.hookWindowMessage(WM_ENDSESSION, wParam => {
      if (wParam.readUInt32LE(0) === 0) {
        sessionEnding = false
        logger.info('Windows 会话结束已取消，重新允许渲染进程恢复')
      }
    })
  }

  win.webContents.on('render-process-gone', (_event, details: RenderProcessGoneDetails) => {
    if (sessionEnding) {
      logger.info('Windows 会话结束期间忽略渲染进程退出')
      return
    }
    options.onRendererGone()
    finishPending({
      outcome: options.isQuitting() ? 'cancelled' : 'failure',
      resultKind: options.isQuitting() ? 'app_quitting' : 'renderer_gone',
    })
    const decision = decideRendererRecovery({
      reason: details.reason,
      exitCode: details.exitCode,
      isQuitting: options.isQuitting(),
      isWindowDestroyed: win.isDestroyed(),
      now: Date.now(),
      previousCrashes: crashes,
    })
    crashes = decision.crashes
    if (decision.action === 'ignore') {
      logger.info(decision.detail)
      return
    }

    logger.error(decision.detail)
    const crash = { ...details, crashCount: decision.crashCount, action: decision.action }
    captureMainRendererCrash(crash)
    const reasonKind =
      details.reason === 'crashed' || details.reason === 'oom' || details.reason === 'killed'
        ? details.reason
        : details.reason === 'launch-failed'
          ? 'launch_failed'
          : 'other'
    beginMainFeature('renderer_recovery_decided').finish({
      reason_kind: reasonKind,
      recovery_action: decision.action === 'give-up' ? 'give_up' : 'reload',
      count_bucket: mainCountBucket(decision.crashCount),
      outcome: 'accepted',
    })
    if (decision.action === 'give-up') return

    const startedAt = performance.now()
    const analytics = beginMainFeature('renderer_recovery_finished')
    const report = beginMainRendererReload(crash)
    const attempt = {
      loaded: false,
      ready: false,
      timer: setTimeout(() => {
        if (pending !== attempt) return
        finishPending({
          outcome: options.isQuitting() ? 'cancelled' : 'unknown',
          resultKind: options.isQuitting() ? 'app_quitting' : 'timeout',
        })
      }, RENDERER_RELOAD_TIMEOUT_MS),
      finish(result: Omit<RendererReloadResult, 'durationMs'>) {
        const durationMs = performance.now() - startedAt
        logger.info(`渲染进程重载结束: ${result.outcome}, ${result.resultKind}`)
        report({ ...result, durationMs })
        analytics.finish({
          reason_kind: reasonKind,
          result_kind: result.resultKind,
          count_bucket: mainCountBucket(decision.crashCount),
          outcome: result.outcome,
        })
      },
    }
    pending = attempt
    attempt.timer.unref()
    options.onReload()
    try {
      win.webContents.reload()
    } catch {
      finishPending({ outcome: 'failure', resultKind: 'reload_threw' })
    }
  })

  win.webContents.on('did-start-loading', () => {
    if (pending) {
      pending.loaded = false
      pending.ready = false
    }
  })
  win.webContents.on('did-finish-load', () => {
    if (pending) pending.loaded = true
    finishIfReady()
  })
  win.webContents.on(
    'did-fail-load',
    (_event, errorCode, _description, _url, isMainFrame, frameProcessId, frameRoutingId) => {
      // 子 frame 或被新导航替换的旧加载，不代表当前主页面恢复失败。
      if (!isMainFrame || errorCode === -3) return
      const frame = win.webContents.mainFrame
      if (frameProcessId !== frame.processId || frameRoutingId !== frame.routingId) return
      finishPending({ outcome: 'failure', resultKind: 'load_failed', loadErrorCode: errorCode })
    }
  )
  win.webContents.once('destroyed', () => {
    finishPending({ outcome: 'cancelled', resultKind: 'window_closed' })
  })
  win.once('closed', () => {
    finishPending({ outcome: 'cancelled', resultKind: 'window_closed' })
  })
  return {
    isSessionEnding: () => sessionEnding,
    rendererReady() {
      if (pending) pending.ready = true
      finishIfReady()
    },
  }
}
