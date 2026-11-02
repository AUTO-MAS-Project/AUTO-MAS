import type { BrowserWindow, IpcMainInvokeEvent } from 'electron'
import { join, resolve } from 'path'
import { pathToFileURL } from 'url'
import { beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { registerQqCredentialHandlers } from './qqCredentialHandlers'

const mocks = vi.hoisted(() => ({ handle: vi.fn(), credentials: vi.fn(), devUrl: '' }))
vi.mock('electron', () => ({
  app: { getAppPath: () => resolve('test-app') },
  ipcMain: { handle: mocks.handle },
}))
vi.mock('../services/analyticsService', () => ({
  analyticsService: {},
  refreshAnalyticsPreference: vi.fn(),
}))
vi.mock('../services/instanceConfig', () => ({ getDevelopmentServerUrl: () => mocks.devUrl }))
vi.mock('../services/qqCredentialService', () => ({ qqCredentials: mocks.credentials }))

beforeEach(() => {
  vi.clearAllMocks()
  mocks.devUrl = ''
})

function bridge() {
  const mainFrame = { url: pathToFileURL(join(resolve('test-app'), 'dist/index.html')).href }
  const webContents = { mainFrame }
  const window = { isDestroyed: () => false, webContents } as unknown as BrowserWindow
  registerQqCredentialHandlers(
    () => window,
    () => 'http://127.0.0.1:36164'
  )
  const get = mocks.handle.mock.calls.find(call => call[0] === 'qq-credentials:get')![1] as (
    event: IpcMainInvokeEvent
  ) => unknown
  const set = mocks.handle.mock.calls.find(call => call[0] === 'qq-credentials:set')![1] as (
    event: IpcMainInvokeEvent,
    value: unknown
  ) => unknown
  const event = { sender: webContents, senderFrame: mainFrame } as unknown as IpcMainInvokeEvent
  return { get, set, event, mainFrame }
}

describe('QQ credential IPC trust boundary', () => {
  it('accepts the packaged main frame for both fixed actions', () => {
    const { get, set, event } = bridge()
    get(event)
    set(event, { appId: 'app' })
    expect(mocks.credentials).toHaveBeenNthCalledWith(1, 'http://127.0.0.1:36164', 'get', undefined)
    expect(mocks.credentials).toHaveBeenNthCalledWith(2, 'http://127.0.0.1:36164', 'set', {
      appId: 'app',
    })
  })

  it.each(['remote', 'iframe', 'other-window'])('rejects %s', kind => {
    const { get, set, event, mainFrame } = bridge()
    if (kind === 'remote') mainFrame.url = 'https://example.invalid/'
    if (kind === 'iframe')
      event.senderFrame = { url: mainFrame.url } as IpcMainInvokeEvent['senderFrame']
    if (kind === 'other-window') event.sender = {} as IpcMainInvokeEvent['sender']
    expect(() => get(event)).toThrow()
    expect(() => set(event, {})).toThrow()
    expect(mocks.credentials).not.toHaveBeenCalled()
  })
})
