import type { BrowserWindow, IpcMainInvokeEvent } from 'electron'
import { resolve } from 'path'
import { pathToFileURL } from 'url'
import { beforeEach, expect, it, vi } from 'vite-plus/test'
import { registerAppUpdateHandlers } from './appUpdateHandlers'
import type { BackendService } from '../services/backendService'

const mocks = vi.hoisted(() => ({
  handle: vi.fn(),
  check: vi.fn(),
  start: vi.fn(),
  switchSource: vi.fn(),
  install: vi.fn(),
}))

vi.mock('electron', () => ({
  app: { getAppPath: () => resolve('test-app') },
  ipcMain: { handle: mocks.handle },
}))
vi.mock('../services/analyticsService', () => ({
  analyticsService: {},
  refreshAnalyticsPreference: vi.fn(),
}))
vi.mock('../services/instanceConfig', () => ({ getDevelopmentServerUrl: () => undefined }))
vi.mock('../services/appUpdateService', () => ({
  checkAppUpdate: mocks.check,
  AppUpdateService: class {
    start = mocks.start
    switchToCnb = mocks.switchSource
    install = mocks.install
  },
}))

beforeEach(() => vi.clearAllMocks())

function bridge(updatesEnabled: boolean) {
  const mainFrame = { url: pathToFileURL(resolve('test-app/dist/index.html')).href }
  const webContents = { mainFrame }
  const window = { isDestroyed: () => false, webContents } as unknown as BrowserWindow
  const event = { sender: webContents, senderFrame: mainFrame } as unknown as IpcMainInvokeEvent
  const quit = vi.fn(async () => {})
  registerAppUpdateHandlers({
    installRoot: resolve('test-install'),
    updatesEnabled,
    window: () => window,
    backendUrl: () => 'http://127.0.0.1:36164',
    backend: () => ({}) as BackendService,
    ownsBackend: () => true,
    quit,
  })
  return {
    quit,
    invoke: async (name: string, ...args: unknown[]) => {
      const handler = mocks.handle.mock.calls.find(
        ([channel]) => channel === `app-update:${name}`
      )![1]
      return handler(event, ...args)
    },
  }
}

it('拥有后端的开发模式也必须在访问更新服务前拒绝桌面更新', async () => {
  const { invoke, quit } = bridge(false)
  await expect(invoke('check', { currentVersion: 'v5.9.0', settings: {} })).resolves.toMatchObject({
    code: 403,
    message: expect.stringContaining('请退出开发后端模式'),
  })
  await expect(invoke('start', 'v5.9.0', {})).rejects.toThrow('请退出开发后端模式')
  await expect(invoke('switch')).rejects.toThrow('请退出开发后端模式')
  await expect(invoke('install')).rejects.toThrow('请退出开发后端模式')
  for (const action of [mocks.check, mocks.start, mocks.switchSource, mocks.install, quit]) {
    expect(action).not.toHaveBeenCalled()
  }
})

it('正常启动仍可安装已有更新并退出', async () => {
  const { invoke, quit } = bridge(true)
  await expect(invoke('install')).resolves.toEqual({ code: 200 })
  expect(mocks.install).toHaveBeenCalledOnce()
  expect(quit).toHaveBeenCalledOnce()
})
