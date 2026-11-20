import { beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import type { Event, EventHint } from '@sentry/electron/main'
import {
  beginMainRendererReload,
  captureMainRendererCrash,
  captureStartupHostFailure,
  configureMainSentry,
} from './sentry'

const sdk = vi.hoisted(() => {
  const options = { enabled: true }
  return {
    options,
    client: { getOptions: () => options },
    captureEvent: vi.fn<(event: Event, hint?: EventHint) => void>(),
    init: vi.fn<(options: { beforeSend(event: Event, hint: EventHint): Event | null }) => void>(),
    active: true,
    permission: 1,
  }
})
vi.mock('@sentry/electron/main', () => ({
  getClient: () => (sdk.init.mock.calls.length ? sdk.client : undefined),
  init: sdk.init,
  setTag: vi.fn(),
  captureEvent: sdk.captureEvent,
}))
vi.mock('electron', () => ({ app: { getVersion: () => 'test' } }))
vi.mock('./startupHardware/monitor', () => ({
  startupAttempt: () =>
    sdk.active
      ? {
          wallStart: 0,
          generation: 1,
          snapshot: () => ({
            coverage: 'sampled',
            sample_age: '<1s',
            cpu_peak: '90-100%',
            unknown: 'private',
          }),
        }
      : undefined,
  isStartupUploadAllowed: (generation: number | null) => generation === sdk.permission,
}))
vi.mock('./instanceConfig', () => ({ isDevelopmentEnvironment: () => false }))

const crash = { reason: 'killed', exitCode: 1073807364, crashCount: 1, action: 'reload' as const }
const result = { outcome: 'success' as const, resultKind: 'ready' as const, durationMs: 100.2 }

beforeEach(() => {
  configureMainSentry(true)
  sdk.captureEvent.mockClear()
  sdk.active = true
  sdk.permission = 1
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
    const received = sdk.captureEvent.mock.calls.map(
      ([event, hint]) =>
        beforeSend(
          {
            ...event,
            timestamp: Date.now() / 1000,
            contexts: { startup_resources: { untrusted: true } },
          },
          hint ?? {}
        )?.contexts?.startup_resources
    )
    expect(received.map(Boolean)).toEqual([true, false, false, false, true])
    expect(received[0]).toEqual({ coverage: 'sampled', sample_age: '<1s', cpu_peak: '90-100%' })
  })
  it('发送前采样已结束时仍保留失败现场，撤销许可后丢弃待发事件', () => {
    captureStartupHostFailure('runtime_binary', 'unknown')
    const [event, hint] = sdk.captureEvent.mock.calls[0]
    const { beforeSend } = sdk.init.mock.calls[0][0]
    sdk.active = false
    expect(beforeSend({ ...event }, hint ?? {})?.contexts?.startup_resources).toEqual({
      coverage: 'sampled',
      sample_age: '<1s',
      cpu_peak: '90-100%',
    })
    expect(
      beforeSend(
        { ...event, contexts: { startup_resources: { raw: 'untrusted' } } },
        { data: { startupFailure: { resources: { raw: 'untrusted' } } } }
      )?.contexts?.startup_resources
    ).toBeUndefined()
    sdk.permission++
    expect(beforeSend({ ...event }, hint ?? {})).toBeNull()
    sdk.permission = 1
    configureMainSentry(false)
    configureMainSentry(true)
    expect(beforeSend({ ...event }, hint ?? {})).toBeNull()
  })
  it('关闭再开启不补发旧尝试，关闭时开始的尝试也不发送', () => {
    const finish = beginMainRendererReload(crash)
    configureMainSentry(false)
    const disabledFinish = beginMainRendererReload(crash)
    configureMainSentry(true)
    finish(result)
    disabledFinish(result)
    expect(sdk.captureEvent).not.toHaveBeenCalled()
    beginMainRendererReload(crash)({
      ...result,
      outcome: 'failure',
      resultKind: 'load_failed',
      loadErrorCode: -6,
    })
    expect(sdk.captureEvent).toHaveBeenCalledTimes(1)
  })
})
