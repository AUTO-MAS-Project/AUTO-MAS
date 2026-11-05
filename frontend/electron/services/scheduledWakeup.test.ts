import { afterEach, beforeEach, expect, it, vi } from 'vite-plus/test'

const blocker = vi.hoisted(() => ({ start: vi.fn(() => 41), stop: vi.fn() }))
vi.mock('electron', () => ({ powerSaveBlocker: blocker }))

afterEach(() => vi.useRealTimers())
beforeEach(() => {
  vi.resetModules()
  blocker.start.mockClear()
  blocker.stop.mockClear()
})

it('renews a temporary wake request for an already running instance and releases it', async () => {
  vi.useFakeTimers()
  const { keepAwakeForScheduledWakeup, shouldSkipStartupQueues } = await import('./scheduledWakeup')
  expect(keepAwakeForScheduledWakeup(['AUTO-MAS.exe', '--auto-start'])).toBe(false)
  expect(blocker.start).not.toHaveBeenCalled()
  expect(shouldSkipStartupQueues()).toBe(false)
  expect(keepAwakeForScheduledWakeup(['AUTO-MAS.exe', '--scheduled-wakeup'])).toBe(true)
  expect(shouldSkipStartupQueues()).toBe(true)
  await vi.advanceTimersByTimeAsync(9 * 60 * 1000)
  keepAwakeForScheduledWakeup(['AUTO-MAS.exe', '--scheduled-wakeup'])
  await vi.advanceTimersByTimeAsync(9 * 60 * 1000)
  expect(blocker.stop).not.toHaveBeenCalled()
  await vi.advanceTimersByTimeAsync(60 * 1000)
  expect(blocker.stop).toHaveBeenCalledWith(41)
  expect(shouldSkipStartupQueues()).toBe(false)
})

it('consumes a cold wake launch after backend ready and removes it from ordinary relaunch', async () => {
  vi.useFakeTimers()
  const originalArgs = process.argv
  process.argv = [...originalArgs, '--scheduled-wakeup']
  let wakeup: typeof import('./scheduledWakeup')
  try {
    wakeup = await import('./scheduledWakeup')
    wakeup.keepAwakeForScheduledWakeup(process.argv)
  } finally {
    process.argv = originalArgs
  }
  await vi.advanceTimersByTimeAsync(11 * 60 * 1000)
  // 首次后端准备尚未完成时保留来源；就绪后不能影响后续的普通启动。
  expect(wakeup.shouldSkipStartupQueues()).toBe(true)
  wakeup.scheduledWakeupBackendReady()
  expect(wakeup.shouldSkipStartupQueues()).toBe(false)
  expect(
    wakeup.normalRelaunchArgs(['app.asar', '--scheduled-wakeup', '--connect-existing-backend'])
  ).toEqual(['app.asar', '--connect-existing-backend'])
})

it('marks resume before a Runtime client can start, even when the wake launch arrives later', async () => {
  vi.useFakeTimers()
  const wakeup = await import('./scheduledWakeup')
  expect(wakeup.shouldSkipStartupQueues()).toBe(false)
  const resumedAt = new Date().toISOString()
  wakeup.prepareSystemResumeRecovery()
  // 系统恢复只能提供提示，尚无定时唤醒命令时不能直接跳过启动队列。
  expect(wakeup.shouldSkipStartupQueues()).toBe(false)
  expect(wakeup.getSystemResumeTime()).toBe(resumedAt)
  wakeup.keepAwakeForScheduledWakeup(['AUTO-MAS.exe', '--scheduled-wakeup'])
  wakeup.scheduledWakeupBackendReady()
  expect(wakeup.shouldSkipStartupQueues()).toBe(true)
  // 睡眠恢复时系统校时不能把十分钟窗口延长成一小时。
  vi.setSystemTime(Date.now() - 60 * 60 * 1000)
  await vi.advanceTimersByTimeAsync(10 * 60 * 1000)
  expect(wakeup.shouldSkipStartupQueues()).toBe(false)
  expect(wakeup.getSystemResumeTime()).toBeUndefined()
})

it('keeps the resume source for a failed backend preparation retry after the keep-awake window', async () => {
  vi.useFakeTimers()
  const wakeup = await import('./scheduledWakeup')
  wakeup.prepareSystemResumeRecovery()
  const resumedAt = wakeup.getSystemResumeTime()
  expect(wakeup.captureScheduledWakeupContext()).toEqual({ scheduledWakeup: false, resumedAt })
  // 第一次客户端拿到来源后准备失败，十一分钟后重建客户端仍需保留同一恢复时间。
  await vi.advanceTimersByTimeAsync(11 * 60 * 1000)
  expect(wakeup.getSystemResumeTime()).toBe(resumedAt)
  expect(wakeup.captureScheduledWakeupContext()).toEqual({ scheduledWakeup: false, resumedAt })
  wakeup.scheduledWakeupBackendReady()
  expect(wakeup.getSystemResumeTime()).toBeUndefined()
})
