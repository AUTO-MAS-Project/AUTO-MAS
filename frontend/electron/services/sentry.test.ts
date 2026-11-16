import { beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { beginMainRendererReload, configureMainSentry } from './sentry'

const sdk = vi.hoisted(() => {
  const options = { enabled: true }
  return { options, client: { getOptions: () => options }, captureMessage: vi.fn() }
})
vi.mock('@sentry/electron/main', () => ({
  getClient: () => sdk.client,
  captureMessage: sdk.captureMessage,
}))
vi.mock('electron', () => ({ app: {} }))
vi.mock('./instanceConfig', () => ({ isDevelopmentEnvironment: () => false }))

const crash = { reason: 'killed', exitCode: 1073807364, crashCount: 1, action: 'reload' as const }
const result = { outcome: 'success' as const, resultKind: 'ready' as const, durationMs: 100.2 }

beforeEach(() => {
  configureMainSentry(true)
  sdk.captureMessage.mockClear()
})

describe('渲染恢复 Sentry 上报', () => {
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
