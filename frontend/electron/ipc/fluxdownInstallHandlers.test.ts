import type { BrowserWindow, IpcMainInvokeEvent } from 'electron'
import { join, resolve } from 'path'
import { pathToFileURL } from 'url'
import { beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { registerFluxdownInstallHandlers } from './fluxdownInstallHandlers'

const mocks = vi.hoisted(() => ({ handle: vi.fn(), install: vi.fn() }))
vi.mock('electron', () => ({
  app: { getAppPath: () => resolve('test-app') },
  ipcMain: { handle: mocks.handle },
}))
vi.mock('../services/analyticsService', () => ({
  analyticsService: {},
  refreshAnalyticsPreference: vi.fn(),
}))
vi.mock('../services/instanceConfig', () => ({ getDevelopmentServerUrl: () => '' }))
vi.mock('../services/fluxdownInstallService', () => ({ installFluxdown: mocks.install }))
beforeEach(() => {
  vi.clearAllMocks()
})

function bridge() {
  const mainFrame = { url: pathToFileURL(join(resolve('test-app'), 'dist/index.html')).href }
  const webContents = { mainFrame }
  const window = { isDestroyed: () => false, webContents } as unknown as BrowserWindow
  registerFluxdownInstallHandlers(
    () => window,
    () => 'http://127.0.0.1:36164'
  )
  const handler = mocks.handle.mock.lastCall![1] as (
    event: IpcMainInvokeEvent,
    mirror: unknown
  ) => unknown
  const event = { sender: webContents, senderFrame: mainFrame } as unknown as IpcMainInvokeEvent
  return { handler, event, mainFrame }
}

describe('installation IPC trust boundary', () => {
  it('accepts the packaged application main frame', async () => {
    mocks.install.mockResolvedValue({ code: 200 })
    const allowed = bridge()
    await expect(allowed.handler(allowed.event, 'auto')).resolves.toEqual({ code: 200 })
    expect(mocks.install).toHaveBeenCalledWith('http://127.0.0.1:36164', 'auto')
    for (const kind of ['remote', 'iframe', 'other-window'] as const) {
      mocks.install.mockClear()
      const denied = bridge()
      if (kind === 'remote') denied.mainFrame.url = 'https://attacker.test/'
      if (kind === 'iframe')
        denied.event.senderFrame = {
          url: denied.mainFrame.url,
        } as IpcMainInvokeEvent['senderFrame']
      if (kind === 'other-window') denied.event.sender = {} as IpcMainInvokeEvent['sender']
      expect(() => denied.handler(denied.event, 'auto'), kind).toThrow()
      expect(mocks.install, kind).not.toHaveBeenCalled()
    }
  })
})
