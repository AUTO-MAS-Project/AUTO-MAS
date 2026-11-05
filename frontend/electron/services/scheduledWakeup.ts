import { powerSaveBlocker } from 'electron'

const WAKEUP_ARGUMENT = '--scheduled-wakeup'
const KEEP_AWAKE_MS = 10 * 60 * 1000
let blocker: number | undefined
let deadline: ReturnType<typeof setTimeout> | undefined
// 准备失败后仍会重试，来源在后端真正就绪后消费，与十分钟保活分开。
let wakeupBackendPending = isScheduledWakeupLaunch(process.argv)
let resumeBackendPending = false
let systemResumeTime: string | undefined

export function isScheduledWakeupLaunch(argv: readonly string[]): boolean {
  return argv.includes(WAKEUP_ARGUMENT)
}

/** 已有实例接到唤醒后，新启动或恢复的后端也应等待定时队列。 */
export function shouldSkipStartupQueues(): boolean {
  return wakeupBackendPending || blocker !== undefined
}

export function getSystemResumeTime(): string | undefined {
  return systemResumeTime
}

/** 客户端准备开始后，保留来源供失败重试，直到后端真正就绪。 */
export function captureScheduledWakeupContext(): {
  scheduledWakeup: boolean
  resumedAt: string | undefined
} {
  wakeupBackendPending ||= blocker !== undefined
  resumeBackendPending ||= systemResumeTime !== undefined
  return { scheduledWakeup: shouldSkipStartupQueues(), resumedAt: getSystemResumeTime() }
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

export function normalRelaunchArgs(argv: readonly string[]): string[] {
  return argv.filter(arg => arg !== WAKEUP_ARGUMENT)
}

/** 冷启动或已运行实例收到唤醒启动时，保活十分钟等待定时调度接管。 */
export function keepAwakeForScheduledWakeup(argv: readonly string[]): boolean {
  if (!isScheduledWakeupLaunch(argv)) return false
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
