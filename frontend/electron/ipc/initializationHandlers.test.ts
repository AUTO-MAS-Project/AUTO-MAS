import { describe, expect, it, vi } from 'vitest'

// 只验证注册守卫：handler 本体依赖真实服务，全部替换成空壳
vi.mock('electron', () => ({
  ipcMain: { handle: vi.fn(), on: vi.fn() },
  BrowserWindow: class {},
}))
vi.mock('../services', () => ({ InitializationService: class {}, BackendService: class {} }))
vi.mock('../services/logger', () => ({
  getLogger: () => ({ error: vi.fn(), warn: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))
vi.mock('../services/environmentService', () => ({ getAppRoot: () => 'D:/app' }))
vi.mock('../services/runtime', () => ({
  resolveRuntimeLaunchConfig: vi.fn(),
  resolveRuntimeLaunchMode: vi.fn(() => 'off'),
}))
vi.mock('../services/runtimeInitializationService', () => ({
  listRuntimeMappableMirrorKeys: vi.fn(() => []),
  mapDoctorChecksToCriticalFiles: vi.fn(),
}))
vi.mock('../services/runtimeUpdateService', () => ({
  abortRuntimeUpdateForShutdown: vi.fn(),
  cancelBackendUpdate: vi.fn(),
  retryBackendUpdate: vi.fn(),
  updateBackendViaRuntime: vi.fn(),
}))

const { ipcMain } = await import('electron')
const { registerInitializationHandlers } = await import('./initializationHandlers')

describe('registerInitializationHandlers', () => {
  it('重复调用不再二次注册 handler', () => {
    const handle = vi.mocked(ipcMain.handle)
    registerInitializationHandlers({} as never)
    const registeredOnce = handle.mock.calls.length
    expect(registeredOnce).toBeGreaterThan(0)

    // 强退失败后重建窗口会再走一遍 createWindow；第二次必须是空操作，
    // 否则 ipcMain.handle 会因 second handler 抛错
    registerInitializationHandlers({} as never)
    expect(handle.mock.calls.length).toBe(registeredOnce)
  })
})
