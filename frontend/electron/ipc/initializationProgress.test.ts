import type { BrowserWindow, IpcMainInvokeEvent } from 'electron'
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vite-plus/test'
import { InitializationService } from '../services/initializationService'
import { registerInitializationHandlers } from './initializationHandlers'

type Handler = (event: IpcMainInvokeEvent, ...args: unknown[]) => unknown
const bridge = vi.hoisted(() => ({
  handlers: new Map<string, Handler>(),
  api: undefined as Window['electronAPI'] | undefined,
  config: {
    mode: 'managed' as const,
    runtimePath: '/isolated/runtime.exe',
    appRoot: '/isolated',
    dataRoot: '/isolated',
  },
}))
vi.mock('electron', () => {
  const event = {
    sender: {
      isDestroyed: () => false,
      send: vi.fn(),
    },
  } as unknown as IpcMainInvokeEvent
  return {
    app: { getVersion: () => '5.8.0-beta.3', isPackaged: false },
    ipcMain: {
      handle: (channel: string, handler: Handler) => bridge.handlers.set(channel, handler),
    },
    ipcRenderer: {
      invoke: async (channel: string, ...args: unknown[]) => {
        const handler = bridge.handlers.get(channel)
        if (!handler) throw new Error(`Unexpected IPC invocation: ${channel}`)
        return handler(event, ...args)
      },
      on: vi.fn(),
      removeAllListeners: vi.fn(),
      send: vi.fn(),
    },
    contextBridge: {
      exposeInMainWorld: (key: string, value: unknown) => {
        if (key === 'electronAPI') bridge.api = value as Window['electronAPI']
      },
    },
  }
})
vi.mock('../services', async () => ({
  InitializationService: (await import('../services/initializationService')).InitializationService,
}))
vi.mock('../services/logger', () => ({
  getLogger: () => ({ info: vi.fn(), warn: vi.fn(), error: vi.fn(), debug: vi.fn() }),
}))
vi.mock('../services/backendService', () => ({ BackendService: class {} }))
vi.mock('../services/environmentService', () => ({
  getAppRoot: () => bridge.config.appRoot,
}))
vi.mock('../services/runtime', async importOriginal => ({
  ...(await importOriginal<typeof import('../services/runtime')>()),
  resolveRuntimeLaunchConfig: () => bridge.config,
}))
vi.mock('../services/runtimeUpdateService', () => ({
  cancelBackendUpdate: vi.fn(),
  retryBackendUpdate: vi.fn(),
  updateBackendViaRuntime: vi.fn(),
}))
vi.mock('../services/initializationAnalytics', () => ({
  observeInitializationStage: (_stage: string, _mode: string, run: () => unknown) => run(),
}))
beforeAll(async () => {
  vi.stubGlobal('window', { addEventListener: vi.fn() })
  await import('../preload')
  registerInitializationHandlers({} as BrowserWindow)
})
afterEach(() => vi.restoreAllMocks())
afterAll(() => vi.unstubAllGlobals())

describe('initialization recovery through preload and IPC', () => {
  it.each([
    ['installPython', 'python'],
    ['pullRepository', 'repository'],
    ['installDependencies', 'dependency'],
  ] as const)(
    '%s keeps retry separate from rebuild through preload and IPC',
    async (method, stage) => {
      const retry = vi
        .spyOn(InitializationService.prototype, 'retryStageViaRuntime')
        .mockResolvedValue({ success: true })
      await bridge.api![method](false)
      expect(retry).toHaveBeenLastCalledWith(stage, expect.any(Function), 'sync')
      await bridge.api![method](true)
      expect(retry).toHaveBeenLastCalledWith(stage, expect.any(Function), 'rebuild')
    }
  )
})
