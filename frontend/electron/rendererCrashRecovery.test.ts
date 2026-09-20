import { describe, expect, it } from 'vitest'

import {
  CRASH_WINDOW_MS,
  MAX_RELOAD_ATTEMPTS,
  decideRendererRecovery,
  type RendererCrashInput,
} from './rendererCrashRecovery'

const baseInput = (overrides: Partial<RendererCrashInput> = {}): RendererCrashInput => ({
  reason: 'crashed',
  exitCode: 5,
  isQuitting: false,
  isWindowDestroyed: false,
  now: 1_000_000,
  previousCrashes: [],
  ...overrides,
})

describe('decideRendererRecovery', () => {
  it('重载首次崩溃并记录时间戳', () => {
    const decision = decideRendererRecovery(baseInput())

    expect(decision.action).toBe('reload')
    expect(decision.crashCount).toBe(1)
    expect(decision.crashes).toEqual([1_000_000])
    expect(decision.detail).toContain('crashed')
  })

  it('正常退出不重载也不计入崩溃统计', () => {
    const decision = decideRendererRecovery(
      baseInput({ reason: 'clean-exit', exitCode: 0, previousCrashes: [999_000] })
    )

    expect(decision.action).toBe('ignore')
    expect(decision.crashes).toEqual([999_000])
    expect(decision.crashCount).toBe(1)
  })

  it('应用退出过程中的渲染进程消失不做恢复', () => {
    const decision = decideRendererRecovery(baseInput({ isQuitting: true }))

    expect(decision.action).toBe('ignore')
  })

  it('窗口已销毁时放弃重载', () => {
    const decision = decideRendererRecovery(baseInput({ isWindowDestroyed: true }))

    expect(decision.action).toBe('give-up')
  })

  it('统计窗口内超过上限后停止重载', () => {
    const previousCrashes = Array.from({ length: MAX_RELOAD_ATTEMPTS }, (_, i) => 999_000 + i)
    const decision = decideRendererRecovery(baseInput({ previousCrashes }))

    expect(decision.action).toBe('give-up')
    expect(decision.crashCount).toBe(MAX_RELOAD_ATTEMPTS + 1)
    expect(decision.detail).toContain(`${MAX_RELOAD_ATTEMPTS} 次自动重载上限`)
  })

  it('窗口期外的旧崩溃被剔除，重新允许重载', () => {
    const now = CRASH_WINDOW_MS * 2
    const stale = Array.from({ length: MAX_RELOAD_ATTEMPTS }, (_, i) => i)
    const decision = decideRendererRecovery(baseInput({ now, previousCrashes: stale }))

    expect(decision.action).toBe('reload')
    expect(decision.crashCount).toBe(1)
    expect(decision.crashes).toEqual([now])
  })

  it('oom 与 launch-failed 同样触发重载', () => {
    for (const reason of ['oom', 'launch-failed', 'abnormal-exit', 'killed']) {
      expect(decideRendererRecovery(baseInput({ reason })).action).toBe('reload')
    }
  })
})
