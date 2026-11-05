import { app, powerSaveBlocker } from 'electron'

const WAKEUP_ARGUMENT = '--scheduled-wakeup'
const KEEP_AWAKE_MS = 10 * 60 * 1000
let blocker: number | undefined
let deadline: ReturnType<typeof setTimeout> | undefined
// 准备失败后仍会重试，来源在后端真正就绪后消费，与十分钟保活分开。
let wakeupBackendPending = isScheduledWakeupLaunch(process.argv)
let resumeBackendPending = false
let systemResumeTime: string | undefined
let quitContext:
  | { kind: 'manual' }
  | { kind: 'automatic'; nextWakeAt: number | undefined; wakeReceived: boolean }
  | undefined
let quitFinished = false

/** IPC 边界兼容旧的空退出请求；只有自动退出承担后续唤醒义务。 */
export function observeScheduledWakeupQuit(request: unknown): void {
  quitFinished = false
  if (
    typeof request !== 'object' ||
    request === null ||
    !('automatic' in request) ||
    request.automatic !== true
  ) {
    quitContext = { kind: 'manual' }
    return
  }
  if (quitContext?.kind === 'manual') return
  const nextWakeAt =
    'nextWakeAt' in request && typeof request.nextWakeAt === 'string'
      ? Date.parse(request.nextWakeAt)
      : NaN
  quitContext = {
    kind: 'automatic',
    nextWakeAt: Number.isFinite(nextWakeAt) ? nextWakeAt : undefined,
    wakeReceived: quitContext?.wakeReceived ?? false,
  }
}

export function cancelScheduledWakeupQuit(): void {
  quitContext = undefined
  quitFinished = false
}

/** 只在 will-quit 调用：此时窗口未取消关闭，Runtime 也已完成收尾。 */
export function finishScheduledWakeupQuit({ restart }: { restart: boolean }): void {
  if (quitFinished) return
  quitFinished = true
  // 先释放锁，之后到达的启动直接交给新实例；已被旧锁转发的启动由时间边界兜住。
  app.releaseSingleInstanceLock()
  const wakeup =
    quitContext?.kind === 'automatic' &&
    (quitContext.wakeReceived ||
      (quitContext.nextWakeAt !== undefined && Date.now() >= quitContext.nextWakeAt))
  if (restart || wakeup) {
    const args = process.argv.slice(1).filter(arg => arg !== WAKEUP_ARGUMENT)
    if (wakeup) args.push(WAKEUP_ARGUMENT)
    app.relaunch({ args })
  }
}

export function isScheduledWakeupLaunch(argv: readonly string[]): boolean {
  return argv.includes(WAKEUP_ARGUMENT)
}

/** 客户端准备开始后，保留来源供失败重试，直到后端真正就绪。 */
export function captureScheduledWakeupContext(): {
  scheduledWakeup: boolean
  resumedAt: string | undefined
} {
  wakeupBackendPending ||= blocker !== undefined
  resumeBackendPending ||= systemResumeTime !== undefined
  return { scheduledWakeup: wakeupBackendPending, resumedAt: systemResumeTime }
}

export function scheduledWakeupBackendReady(): void {
  wakeupBackendPending = false
  resumeBackendPending = false
  if (deadline === undefined) systemResumeTime = undefined
}

/** 在通知 renderer 恢复连接之前调用，避免稍后才到的第二实例造成竞态。 */
export function prepareSystemResumeRecovery(): void {
  systemResumeTime = new Date().toISOString()
  renewWakeupWindow()
}

/** 冷启动或已运行实例收到唤醒启动时，保活十分钟等待定时调度接管。 */
export function keepAwakeForScheduledWakeup(argv: readonly string[]): boolean {
  if (!isScheduledWakeupLaunch(argv)) return false
  if (quitContext?.kind === 'automatic') quitContext.wakeReceived = true
  if (blocker === undefined) blocker = powerSaveBlocker.start('prevent-app-suspension')
  renewWakeupWindow()
  return true
}

function renewWakeupWindow(): void {
  if (deadline) clearTimeout(deadline)
  deadline = setTimeout(() => {
    if (blocker !== undefined) powerSaveBlocker.stop(blocker)
    blocker = undefined
    deadline = undefined
    if (!resumeBackendPending) systemResumeTime = undefined
  }, KEEP_AWAKE_MS)
  deadline.unref()
}
