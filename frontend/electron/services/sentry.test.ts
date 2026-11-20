import { beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import type { Event } from '@sentry/electron/main'
import { beginMainRendererReload, captureMainRendererCrash, configureMainSentry } from './sentry'

const sdk = vi.hoisted(() => {
  const options = { enabled: true }
  return {
    options,
    client: { getOptions: () => options },
    captureMessage: vi.fn(),
    init: vi.fn<(options: { beforeSend(event: Event): Event }) => void>(),
  }
})
vi.mock('@sentry/electron/main', () => ({
  getClient: () => (sdk.init.mock.calls.length ? sdk.client : undefined),
  init: sdk.init,
  setTag: vi.fn(),
  captureMessage: sdk.captureMessage,
}))
vi.mock('electron', () => ({ app: { getVersion: () => 'test' } }))
vi.mock('./startupHardware/monitor', () => ({
  startupAttempt: () => ({
    wallStart: 0,
    snapshot: () => ({ coverage: 'sampled', sample_age: '<1s', cpu_peak: '90-100%' }),
  }),
}))
vi.mock('./instanceConfig', () => ({ isDevelopmentEnvironment: () => false }))

const crash = { reason: 'killed', exitCode: 1073807364, crashCount: 1, action: 'reload' as const }
const result = { outcome: 'success' as const, resultKind: 'ready' as const, durationMs: 100.2 }

beforeEach(() => {
  configureMainSentry(true)
  sdk.captureMessage.mockClear()
})

describe('渲染恢复 Sentry 上报', () => {
  it('发送前仅为崩溃和失败的重载附上启动硬件摘要', () => {
    captureMainRendererCrash(crash)
    const finish = beginMainRendererReload(crash)
    finish(result)
    finish({ outcome: 'cancelled', resultKind: 'window_closed', durationMs: 1 })
    finish({ outcome: 'unknown', resultKind: 'timeout', durationMs: 1 })
    finish({ outcome: 'failure', resultKind: 'load_failed', durationMs: 1 })
    const { beforeSend } = sdk.init.mock.calls[0][0]
    const received = sdk.captureMessage.mock.calls.map(
      ([message, options]) =>
        beforeSend({
          message,
          ...options,
          timestamp: Date.now() / 1000,
          contexts: { startup_resources: { untrusted: true } },
        }).contexts?.startup_resources
    )
    expect(received.map(Boolean)).toEqual([true, false, false, false, true])
    expect(received[0]).toEqual({ coverage: 'sampled', sample_age: '<1s', cpu_peak: '90-100%' })
  })
  it('关闭再开启不补发旧尝试，关闭时开始的尝试也不发送', () => {
    const finish = beginMainRendererReload(crash)
    configureMainSentry(false)
    const disabledFinish = beginMainRendererReload(crash)
    configureMainSentry(true)
    finish(result)
    disabledFinish(result)
    expect(sdk.captureMessage).not.toHaveBeenCalled()
    beginMainRendererReload(crash)({
      ...result,
      outcome: 'failure',
      resultKind: 'load_failed',
      loadErrorCode: -6,
    })
    expect(sdk.captureMessage).toHaveBeenCalledTimes(1)
  })
})
