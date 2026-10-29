import type { BrowserWindow, IpcMainInvokeEvent } from 'electron'
import { resolve, join } from 'path'
import { pathToFileURL } from 'url'
import { beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { registerFluxdownInstallHandlers } from './fluxdownInstallHandlers'

const mocks = vi.hoisted(() => ({ handle: vi.fn(), install: vi.fn(), devUrl: '' }))
vi.mock('electron', () => ({
  app: { getAppPath: () => resolve('test-app') },
  ipcMain: { handle: mocks.handle },
}))
vi.mock('../services/analyticsService', () => ({
  analyticsService: {},
  refreshAnalyticsPreference: vi.fn(),
}))
vi.mock('../services/instanceConfig', () => ({ getDevelopmentServerUrl: () => mocks.devUrl }))
vi.mock('../services/fluxdownInstallService', () => ({ installFluxdown: mocks.install }))
beforeEach(() => {
  vi.clearAllMocks()
  mocks.devUrl = ''
})

function bridge() {
  const mainFrame = { url: pathToFileURL(join(resolve('test-app'), 'dist/index.html')).href }
  const webContents = { mainFrame }
  const window = { isDestroyed: () => false, webContents } as unknown as BrowserWindow
  registerFluxdownInstallHandlers(
    () => window,
    () => 'http://127.0.0.1:36164'
  )
  const handler = mocks.handle.mock.calls[0][1] as (
    event: IpcMainInvokeEvent,
    mirror: unknown
  ) => unknown
  const event = { sender: webContents, senderFrame: mainFrame } as unknown as IpcMainInvokeEvent
  return { handler, event, mainFrame }
}

describe('installation IPC trust boundary', () => {
  it('accepts the packaged application main frame', async () => {
    mocks.install.mockResolvedValue({ code: 200 })
    const { handler, event } = bridge()
    await expect(handler(event, 'auto')).resolves.toEqual({ code: 200 })
    expect(mocks.install).toHaveBeenCalledWith('http://127.0.0.1:36164', 'auto')
  })

  it('accepts only the configured development application entry', async () => {
    mocks.devUrl = 'http://127.0.0.1:5173/'
    const { handler, event, mainFrame } = bridge()
    mainFrame.url = mocks.devUrl
    mocks.install.mockResolvedValue({ code: 200 })
    await expect(handler(event, 'github')).resolves.toEqual({ code: 200 })
  })

  it.each(['remote', 'iframe', 'other-window'])('rejects %s even with the preload API', kind => {
    const { handler, event, mainFrame } = bridge()
    if (kind === 'remote') mainFrame.url = 'https://attacker.test/'
    if (kind === 'iframe')
      event.senderFrame = { url: mainFrame.url } as IpcMainInvokeEvent['senderFrame']
    if (kind === 'other-window') event.sender = {} as IpcMainInvokeEvent['sender']
    expect(() => handler(event, 'auto')).toThrow()
    expect(mocks.install).not.toHaveBeenCalled()
  })
})
