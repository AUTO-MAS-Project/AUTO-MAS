import { EventEmitter } from 'node:events'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import type { BrowserWindow } from 'electron'
import { beforeEach, expect, it, vi } from 'vite-plus/test'
import { registerDesktopSession } from './desktopSessionHandlers'

const mocks = vi.hoisted(() => ({
  handle: vi.fn(),
  close: vi.fn(async () => {}),
  changeWindow: vi.fn(),
  park: vi.fn(async () => true),
  messageBox: vi.fn(),
}))

class TestWindow extends EventEmitter {
  crashed = false
  destroyed = false
  minimized = false
  webContents = Object.assign(new EventEmitter(), {
    mainFrame: { url: pathToFileURL(resolve('test-app/dist/index.html')).href },
    isDestroyed: () => this.destroyed,
    isCrashed: () => this.crashed,
    setWindowOpenHandler: vi.fn(),
    send: vi.fn(),
  })

  isDestroyed = () => this.destroyed
  isMinimized = () => this.minimized
  isVisible = () => true
  show = vi.fn()
  focus = vi.fn()
  destroy = () => {
    this.destroyed = true
    this.emit('closed')
  }
  restore = () => {
    this.minimized = false
    this.emit('restore')
  }
  loadFile = async () => {
    this.webContents.mainFrame.url += '#/desktop-session'
  }
}

let preview: TestWindow | undefined

vi.mock('electron', () => ({
  app: { getAppPath: () => resolve('test-app') },
  BrowserWindow: function () {
    const window = new TestWindow()
    preview = window
    return window
  },
  dialog: { showMessageBox: mocks.messageBox },
  ipcMain: { handle: mocks.handle, on: vi.fn() },
}))
vi.mock('../services/analyticsService', () => ({ analyticsService: {} }))
vi.mock('../services/startupHardware/monitor', () => ({}))
vi.mock('../services/featureAnalytics', () => ({}))
vi.mock('../services/desktopSessionService', () => ({
  DesktopSessionService: class {
    active = true
    adopted = true
    waitForStart = async () => {}
    close = mocks.close
    changeWindow = mocks.changeWindow
    parkForPrompt = mocks.park
  },
}))

beforeEach(() => {
  vi.clearAllMocks()
  preview = undefined
})

function invoke(window: TestWindow, channel: string, ...args: unknown[]) {
  const [, handler] = mocks.handle.mock.calls.find(
    ([name]) => name === `desktop-session:${channel}`
  )!
  return handler({ sender: window.webContents, senderFrame: window.webContents.mainFrame }, ...args)
}

function openPreview() {
  const main = new TestWindow()
  const bridge = registerDesktopSession(
    () => main as unknown as BrowserWindow,
    '',
    () => 'en-US'
  )
  invoke(main, 'open', { queueIds: [], resolution: 'primary', mode: 'native' })
  return { bridge, window: preview! }
}

it.runIf(process.platform === 'win32' && process.arch === 'x64')(
  '恢复预览窗口时，注销确认仍可操作，取消后才恢复原生画面',
  async () => {
    const { bridge, window } = openPreview()
    const closing = bridge.closeForAppQuit()
    await vi.waitFor(() =>
      expect(invoke(window, 'prompt:get')).toMatchObject({ kind: 'close-adopted' })
    )
    const { id } = invoke(window, 'prompt:get')
    window.minimized = true
    window.emit('minimize')
    window.restore()
    invoke(window, 'prompt:respond', id, 'cancel')

    await expect(closing).resolves.toBe(false)
    expect(mocks.changeWindow.mock.calls.slice(0, -1).flat()).not.toContain('visible')
    expect(mocks.changeWindow).toHaveBeenLastCalledWith('visible')
    expect(mocks.close).not.toHaveBeenCalled()
  }
)

it.runIf(process.platform === 'win32' && process.arch === 'x64')(
  '画面移出失败或预览失去响应时，改用原生确认且可取消',
  async () => {
    const { bridge, window } = openPreview()
    mocks.messageBox.mockResolvedValue({ response: 2 })
    mocks.park.mockResolvedValueOnce(false)
    await expect(bridge.closeForAppQuit()).resolves.toBe(false)
    expect(invoke(window, 'prompt:get')).toBeNull()

    const closing = bridge.closeForAppQuit()
    await vi.waitFor(() =>
      expect(invoke(window, 'prompt:get')).toMatchObject({ kind: 'close-adopted' })
    )
    window.emit('unresponsive')
    await expect(closing).resolves.toBe(false)
    await expect(bridge.closeForAppQuit()).resolves.toBe(false)
    expect(mocks.messageBox).toHaveBeenCalledTimes(3)
    expect(mocks.close).not.toHaveBeenCalled()
  }
)

it.runIf(process.platform === 'win32' && process.arch === 'x64')(
  '预览渲染进程崩溃后，取消原生确认保留会话，再次选择仅断开也不会注销',
  async () => {
    const { bridge, window } = openPreview()
    window.crashed = true
    mocks.messageBox.mockResolvedValueOnce({ response: 2 }).mockResolvedValueOnce({ response: 0 })

    await expect(bridge.closeForAppQuit()).resolves.toBe(false)
    expect(window.destroyed).toBe(false)
    expect(mocks.close).not.toHaveBeenCalled()
    await expect(bridge.closeForAppQuit()).resolves.toBe(true)
    expect(window.destroyed).toBe(true)
    expect(mocks.close).toHaveBeenCalledExactlyOnceWith({ logoff: false })
  }
)
