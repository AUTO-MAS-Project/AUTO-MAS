import { beforeEach, describe, expect, it, vi } from 'vitest'

// ==================== 全局桩 ====================

const logger = { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }

const beginWindow = vi.fn()
const endWindow = vi.fn()

vi.mock('@/composables/useAppLifecycle', () => ({
  beginIntentionalBackendRestart: (reason: string) => beginWindow(reason),
  endIntentionalBackendRestart: (reason: string) => endWindow(reason),
}))

vi.mock('@/services/websocket/connection', () => ({
  reconnectNow: vi.fn(async () => true),
}))

vi.mock('./useVersionService', () => ({
  getBackendVersion: vi.fn(async () => undefined),
}))

const updateBackendViaRuntime = vi.fn()
const retryBackendUpdate = vi.fn()

const loadModule = async () => {
  vi.resetModules()
  const mod = await import('./useBackendRuntimeUpdate')
  return mod.useBackendRuntimeUpdate()
}

describe('useBackendRuntimeUpdate 有意重启窗口', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('window', {
      electronAPI: {
        getLogger: () => logger,
        updateBackendViaRuntime,
        retryBackendUpdate,
        onBackendUpdateProgress: vi.fn(),
        removeBackendUpdateProgressListener: vi.fn(),
      },
    })
  })

  it('更新成功时进入窗口并在收口处结束', async () => {
    updateBackendViaRuntime.mockResolvedValue({ success: true })
    const runtimeUpdate = await loadModule()

    await runtimeUpdate.start('v5.5.0')

    // 停机发生在 updateBackendViaRuntime 内部，窗口必须早于它进入
    expect(beginWindow).toHaveBeenCalledTimes(1)
    expect(beginWindow.mock.invocationCallOrder[0]).toBeLessThan(
      updateBackendViaRuntime.mock.invocationCallOrder[0]
    )
    expect(endWindow).toHaveBeenCalledTimes(1)
  })

  it('更新失败时也结束窗口，把事故路径还给协调器', async () => {
    updateBackendViaRuntime.mockResolvedValue({
      success: false,
      phase: 'bootstrap',
      error: 'boom',
    })
    const runtimeUpdate = await loadModule()

    await runtimeUpdate.start('v5.5.0')

    expect(beginWindow).toHaveBeenCalledTimes(1)
    expect(endWindow).toHaveBeenCalledTimes(1)
  })

  it('IPC 抛异常时窗口不会滞留', async () => {
    updateBackendViaRuntime.mockRejectedValue(new Error('ipc down'))
    const runtimeUpdate = await loadModule()

    await runtimeUpdate.start('v5.5.0')

    expect(beginWindow).toHaveBeenCalledTimes(1)
    expect(endWindow).toHaveBeenCalledTimes(1)
  })

  it('单步重试同样进入窗口', async () => {
    retryBackendUpdate.mockResolvedValue({ success: true })
    const runtimeUpdate = await loadModule()

    await runtimeUpdate.retry('workspace-sync')

    expect(beginWindow).toHaveBeenCalledTimes(1)
    expect(beginWindow.mock.calls[0][0]).toContain('重试')
    expect(endWindow).toHaveBeenCalledTimes(1)
  })
})
