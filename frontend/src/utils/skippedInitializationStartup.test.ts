import { beforeEach, describe, expect, it, vi } from 'vite-plus/test'

const state = vi.hoisted(() => ({ browser: false }))
const calls = vi.hoisted(() => ({
  beginBootstrap: vi.fn(),
  finishBootstrap: vi.fn(),
  resetInitializationStatus: vi.fn(),
  backendStatus: vi.fn(),
  backendStart: vi.fn(),
  enterApp: vi.fn(),
  navigateTo: vi.fn(),
  finish: vi.fn(),
}))

vi.mock('@/utils/environment', () => ({ managesBackendProcess: () => !state.browser }))
vi.mock('@/i18n', () => ({ translate: (key: string) => key }))
vi.mock('ant-design-vue', () => ({ message: { error: vi.fn() } }))
vi.mock('@/composables/useAppInitialization', () => ({ useAppInitialization: () => calls }))
vi.mock('@/router', () => ({ navigateTo: calls.navigateTo }))
vi.mock('@/utils/appEntry', () => ({ enterApp: calls.enterApp }))
vi.mock('@/utils/analytics', () => ({ beginAnalyticsOperation: () => ({ finish: calls.finish }) }))
vi.mock('@/services/websocket/connection', () => ({ connectionState: () => ({ value: 'open' }) }))

describe('跳过安装后的启动所有权', () => {
  beforeEach(() => {
    vi.resetModules()
    vi.clearAllMocks()
    state.browser = false
    calls.backendStatus.mockResolvedValue({ isRunning: false, runtimeSupervised: true })
    calls.backendStart.mockResolvedValue({ success: true })
    calls.enterApp.mockResolvedValue(true)
    vi.stubGlobal('window', {
      electronAPI: {
        getLogger: () => ({ info: vi.fn(), error: vi.fn() }),
        backendStatus: calls.backendStatus,
        backendStart: calls.backendStart,
      },
    })
    vi.stubGlobal('sessionStorage', { setItem: vi.fn() })
  })

  it('启动失败转到恢复页，不把已有连接当成新后端启动成功', async () => {
    calls.backendStart.mockResolvedValue({ success: false, code: 'RUNTIME_NOT_FOUND' })
    const { startSkippedInitializationStartup } = await import('./skippedInitializationStartup')
    await startSkippedInitializationStartup()
    expect(calls.enterApp).not.toHaveBeenCalled()
    expect(calls.navigateTo).toHaveBeenCalledWith('/initialization', { replace: true })
    expect(calls.finish).toHaveBeenCalledWith(expect.objectContaining({ outcome: 'failure' }))
  })

  it('yarn web 只连接独立后端，不请求启动或查询 Electron 进程', async () => {
    state.browser = true
    const { startSkippedInitializationStartup } = await import('./skippedInitializationStartup')
    await startSkippedInitializationStartup()
    expect(calls.backendStart).not.toHaveBeenCalled()
    expect(calls.backendStatus).not.toHaveBeenCalled()
    expect(calls.enterApp).toHaveBeenCalledOnce()
  })
})
