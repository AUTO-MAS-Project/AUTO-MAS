import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  handle: vi.fn(),
  existsSync: vi.fn(),
  requiresBundledRuntimeLock: vi.fn(),
  mirrorInitialize: vi.fn(),
  mirrorInitializeLocal: vi.fn(),
  stopBackendForRuntimeMutation: vi.fn(),
  prewarmBackend: vi.fn(),
  startBackend: vi.fn(),
  setStatusCallback: vi.fn(),
  getManagedProcesses: vi.fn(),
  installPackages: vi.fn(),
}))

vi.mock('electron', () => ({
  ipcMain: { handle: mocks.handle },
  BrowserWindow: class BrowserWindow {},
}))

vi.mock('fs', () => ({
  existsSync: mocks.existsSync,
}))

vi.mock('../../services/environmentService', () => ({
  getAppRoot: () => 'C:\\AUTO-MAS-test',
}))

vi.mock('../../services/logger', () => ({
  getLogger: () => ({
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  }),
}))

vi.mock('../../services/bundledRuntimePolicy', () => ({
  requiresBundledRuntimeLock: mocks.requiresBundledRuntimeLock,
}))

vi.mock('../../services/pluginBootstrapService', () => ({
  PluginBootstrapService: class PluginBootstrapService {
    installPackages = mocks.installPackages
  },
}))

vi.mock('../../services', () => {
  class InitializationService {
    private readonly mirrorService = {
      getApiEndpoint: () => 'http://localhost:36163',
      initialize: mocks.mirrorInitialize,
      initializeLocal: mocks.mirrorInitializeLocal,
    }

    getMirrorService() {
      return this.mirrorService
    }

    setBackendService() {}

    setTargetBranch() {}
  }

  class BackendService {
    stopBackendForRuntimeMutation = mocks.stopBackendForRuntimeMutation
    prewarmBackend = mocks.prewarmBackend
    startBackend = mocks.startBackend
    setStatusCallback = mocks.setStatusCallback
    getManagedProcesses = mocks.getManagedProcesses
  }

  return { InitializationService, BackendService }
})

describe('initialization handler safe cleanup', () => {
  beforeEach(() => {
    vi.resetModules()
    mocks.handle.mockReset()
    mocks.existsSync.mockReset()
    mocks.requiresBundledRuntimeLock.mockReset()
    mocks.mirrorInitialize.mockReset()
    mocks.mirrorInitializeLocal.mockReset()
    mocks.stopBackendForRuntimeMutation.mockReset()
    mocks.prewarmBackend.mockReset()
    mocks.startBackend.mockReset()
    mocks.setStatusCallback.mockReset()
    mocks.getManagedProcesses.mockReset()
    mocks.installPackages.mockReset()

    mocks.existsSync.mockReturnValue(true)
    mocks.requiresBundledRuntimeLock.mockReturnValue(true)
    mocks.mirrorInitialize.mockResolvedValue(undefined)
    mocks.stopBackendForRuntimeMutation.mockResolvedValue({ success: true, wasRunning: false })
    mocks.prewarmBackend.mockResolvedValue(undefined)
    mocks.startBackend.mockResolvedValue({ success: true })
    mocks.installPackages.mockResolvedValue({
      success: true,
      installedPackages: [],
      failedPackages: [],
      warnings: [],
      summary: 'ok',
    })
  })

  it('coalesces concurrent cleanup calls into one exact backend stop', async () => {
    let completeStop: ((result: { success: boolean; wasRunning: boolean }) => void) | undefined
    mocks.stopBackendForRuntimeMutation.mockImplementation(
      () =>
        new Promise(resolve => {
          completeStop = resolve
        })
    )
    const { cleanupInitializationResources } = await import('../../ipc/initializationHandlers')

    const first = cleanupInitializationResources()
    const second = cleanupInitializationResources()
    await vi.waitFor(() => expect(mocks.stopBackendForRuntimeMutation).toHaveBeenCalledOnce())
    completeStop?.({ success: true, wasRunning: true })

    await expect(first).resolves.toEqual({ success: true })
    await expect(second).resolves.toEqual({ success: true })
    expect(mocks.stopBackendForRuntimeMutation).toHaveBeenCalledOnce()
  })

  it('returns the safe refusal instead of killing a development backend', async () => {
    mocks.stopBackendForRuntimeMutation.mockResolvedValue({
      success: false,
      wasRunning: true,
      error: '检测到开发模式后端，已拒绝停止或修改其运行时文件',
    })
    const { cleanupInitializationResources } = await import('../../ipc/initializationHandlers')

    await expect(cleanupInitializationResources()).resolves.toEqual({
      success: false,
      error: '检测到开发模式后端，已拒绝停止或修改其运行时文件',
    })
  })

  it('keeps related-process compatibility scoped to managed backend records', async () => {
    const managed = [{ pid: 4242, name: 'python.exe', command: '', commandLine: '' }]
    mocks.getManagedProcesses.mockResolvedValue(managed)
    const { getManagedBackendProcesses } = await import('../../ipc/initializationHandlers')

    await expect(getManagedBackendProcesses()).resolves.toEqual(managed)
  })

  it('deduplicates lifecycle prewarm and renderer repair after bundled validation', async () => {
    let finishBootstrap!: (result: {
      success: boolean
      installedPackages: string[]
      failedPackages: string[]
      warnings: never[]
      summary: string
    }) => void
    mocks.installPackages.mockImplementation(
      () =>
        new Promise(resolve => {
          finishBootstrap = resolve
        })
    )

    const { prewarmBackend, registerInitializationHandlers } =
      await import('../../ipc/initializationHandlers')
    registerInitializationHandlers({ webContents: { id: 1 } } as never)
    const repairHandler = mocks.handle.mock.calls.find(
      ([channel]) => channel === 'repair-runtime-and-start'
    )?.[1]
    expect(repairHandler).toBeTypeOf('function')

    const lifecyclePrewarm = prewarmBackend({
      currentVersion: 'v6.0.0-alpha.1',
      initializedVersion: 'v6.0.0-alpha.1',
      autoUpdateEnabled: false,
    })
    await vi.waitFor(() => expect(mocks.installPackages).toHaveBeenCalledOnce())

    const sender = { send: vi.fn() }
    const rendererRepair = repairHandler({ sender })
    finishBootstrap({
      success: true,
      installedPackages: [],
      failedPackages: [],
      warnings: [],
      summary: 'ok',
    })

    await expect(lifecyclePrewarm).resolves.toBeUndefined()
    await expect(rendererRepair).resolves.toEqual({ success: true, summary: 'ok' })
    expect(mocks.mirrorInitializeLocal).toHaveBeenCalledOnce()
    expect(mocks.mirrorInitialize).not.toHaveBeenCalled()
    expect(mocks.stopBackendForRuntimeMutation).toHaveBeenCalledOnce()
    expect(mocks.installPackages).toHaveBeenCalledOnce()
    expect(mocks.prewarmBackend).toHaveBeenCalledOnce()
    expect(mocks.startBackend).toHaveBeenCalledOnce()

    mocks.installPackages.mockResolvedValue({
      success: true,
      installedPackages: [],
      failedPackages: [],
      warnings: [],
      summary: 'checked again',
    })
    await expect(repairHandler({ sender })).resolves.toEqual({
      success: true,
      summary: 'checked again',
    })
    expect(mocks.mirrorInitializeLocal).toHaveBeenCalledTimes(2)
    expect(mocks.stopBackendForRuntimeMutation).toHaveBeenCalledTimes(2)
    expect(mocks.installPackages).toHaveBeenCalledTimes(2)
    expect(mocks.prewarmBackend).toHaveBeenCalledTimes(2)
    expect(mocks.startBackend).toHaveBeenCalledTimes(2)
  })

  it('releases a failed lifecycle prewarm so renderer repair can retry', async () => {
    mocks.installPackages
      .mockResolvedValueOnce({
        success: false,
        installedPackages: [],
        failedPackages: ['broken'],
        warnings: [],
        error: 'bootstrap failed',
        summary: 'bootstrap failed',
      })
      .mockResolvedValueOnce({
        success: true,
        installedPackages: [],
        failedPackages: [],
        warnings: [],
        summary: 'repaired',
      })

    const { prewarmBackend, registerInitializationHandlers } =
      await import('../../ipc/initializationHandlers')
    registerInitializationHandlers({ webContents: { id: 1 } } as never)
    const repairHandler = mocks.handle.mock.calls.find(
      ([channel]) => channel === 'repair-runtime-and-start'
    )?.[1]

    await expect(
      prewarmBackend({
        currentVersion: 'v6.0.0-alpha.1',
        initializedVersion: 'v6.0.0-alpha.1',
        autoUpdateEnabled: false,
      })
    ).rejects.toThrow('bootstrap failed')
    await expect(repairHandler({ sender: { send: vi.fn() } })).resolves.toEqual({
      success: true,
      summary: 'repaired',
    })

    expect(mocks.installPackages).toHaveBeenCalledTimes(2)
    expect(mocks.prewarmBackend).toHaveBeenCalledOnce()
    expect(mocks.startBackend).toHaveBeenCalledOnce()
  })

  it('keeps the remote mirror refresh for a non-bundled repair', async () => {
    mocks.requiresBundledRuntimeLock.mockReturnValue(false)
    const { registerInitializationHandlers } = await import('../../ipc/initializationHandlers')
    registerInitializationHandlers({ webContents: { id: 1 } } as never)
    const repairHandler = mocks.handle.mock.calls.find(
      ([channel]) => channel === 'repair-runtime-and-start'
    )?.[1]

    await expect(repairHandler({ sender: { send: vi.fn() } })).resolves.toEqual({
      success: true,
      summary: 'ok',
    })
    expect(mocks.mirrorInitialize).toHaveBeenCalledOnce()
    expect(mocks.mirrorInitializeLocal).not.toHaveBeenCalled()
  })

  it('uses local mirror configuration for bundled init-mirrors', async () => {
    const { registerInitializationHandlers } = await import('../../ipc/initializationHandlers')
    registerInitializationHandlers({ webContents: { id: 1 } } as never)
    const initMirrorsHandler = mocks.handle.mock.calls.find(
      ([channel]) => channel === 'init-mirrors'
    )?.[1]

    await expect(initMirrorsHandler()).resolves.toEqual({ success: true })
    expect(mocks.mirrorInitializeLocal).toHaveBeenCalledOnce()
    expect(mocks.mirrorInitialize).not.toHaveBeenCalled()
  })

  it('keeps the remote mirror refresh for non-bundled init-mirrors', async () => {
    mocks.requiresBundledRuntimeLock.mockReturnValue(false)
    const { registerInitializationHandlers } = await import('../../ipc/initializationHandlers')
    registerInitializationHandlers({ webContents: { id: 1 } } as never)
    const initMirrorsHandler = mocks.handle.mock.calls.find(
      ([channel]) => channel === 'init-mirrors'
    )?.[1]

    await expect(initMirrorsHandler()).resolves.toEqual({ success: true })
    expect(mocks.mirrorInitialize).toHaveBeenCalledOnce()
    expect(mocks.mirrorInitializeLocal).not.toHaveBeenCalled()
  })

  it('does not prewarm an update or version-mismatch startup', async () => {
    const { prewarmBackend, shouldPrewarmBackend } =
      await import('../../ipc/initializationHandlers')

    expect(
      shouldPrewarmBackend({
        currentVersion: 'v6.0.0-alpha.1',
        initializedVersion: 'v5.4.0',
        autoUpdateEnabled: false,
      })
    ).toBe(false)
    await prewarmBackend({
      currentVersion: 'v6.0.0-alpha.1',
      initializedVersion: 'v6.0.0-alpha.1',
      autoUpdateEnabled: true,
    })
    expect(mocks.stopBackendForRuntimeMutation).not.toHaveBeenCalled()
    expect(mocks.prewarmBackend).not.toHaveBeenCalled()
  })
})
