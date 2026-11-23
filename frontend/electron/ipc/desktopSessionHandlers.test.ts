import { EventEmitter } from 'node:events'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import type { BrowserWindow } from 'electron'
import { beforeEach, expect, it, vi } from 'vite-plus/test'
import { registerDesktopSession } from './desktopSessionHandlers'

const mocks = vi.hoisted(() => ({
  handle: vi.fn(),
  on: vi.fn(),
  start: vi.fn(),
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
  getContentBounds = () => ({ x: 0, y: 0, width: 600, height: 400 })
  getNativeWindowHandle = () => Buffer.alloc(8)
  loadFile = async () => {
    this.crashed = false
    this.webContents.mainFrame.url =
      pathToFileURL(resolve('test-app/dist/index.html')).href + '#/desktop-session'
  }
}

let preview: TestWindow | undefined
const snapshot = { state: 'connecting' }

vi.mock('electron', () => ({
  app: { getAppPath: () => resolve('test-app') },
  BrowserWindow: function () {
    const window = new TestWindow()
    preview = window
    return window
  },
  dialog: { showMessageBox: mocks.messageBox },
  screen: { getDisplayMatching: () => ({ scaleFactor: 1 }) },
  ipcMain: { handle: mocks.handle, on: mocks.on },
}))
vi.mock('../services/analyticsService', () => ({ analyticsService: {} }))
vi.mock('../services/startupHardware/monitor', () => ({}))
vi.mock('../services/featureAnalytics', () => ({}))
vi.mock('../services/desktopSessionService', () => ({
  DesktopSessionService: class {
    active = true
    adopted = true
    snapshot = snapshot
    closeRisk = async () => ({ activeTasks: false, unmanagedPrograms: false })
    position = vi.fn()
    start = mocks.start
    waitForStart = async () => {}
    close = mocks.close
    changeWindow = mocks.changeWindow
    parkForPrompt = mocks.park
  },
}))

beforeEach(() => {
  vi.clearAllMocks()
  preview = undefined
  snapshot.state = 'connecting'
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

function closePreview(bridge: ReturnType<typeof registerDesktopSession>, window: TestWindow) {
  window.emit('close', { preventDefault() {} })
  return bridge.closeForAppQuit()
}

it.runIf(process.platform === 'win32' && process.arch === 'x64')(
  '恢复预览窗口时，注销确认仍可操作，取消后才恢复原生画面',
  async () => {
    const { bridge, window } = openPreview()
    const closing = closePreview(bridge, window)
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
    await expect(closePreview(bridge, window)).resolves.toBe(false)
    expect(invoke(window, 'prompt:get')).toBeNull()

    const closing = closePreview(bridge, window)
    await vi.waitFor(() =>
      expect(invoke(window, 'prompt:get')).toMatchObject({ kind: 'close-adopted' })
    )
    window.emit('unresponsive')
    await expect(closing).resolves.toBe(false)
    await expect(closePreview(bridge, window)).resolves.toBe(false)
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

    await expect(closePreview(bridge, window)).resolves.toBe(false)
    expect(window.destroyed).toBe(false)
    expect(mocks.close).not.toHaveBeenCalled()
    await expect(closePreview(bridge, window)).resolves.toBe(true)
    expect(window.destroyed).toBe(true)
    expect(mocks.close).toHaveBeenCalledExactlyOnceWith({ logoff: false, onlyIfIdle: false })
  }
)

it.runIf(process.platform === 'win32' && process.arch === 'x64').each([
  ['connected', 'connected'],
  ['disconnected', 'failed'],
])('settles the pending task after cancelling app quit (%s)', async (state, outcome) => {
  const main = new TestWindow()
  const bridge = registerDesktopSession(
    () => main as unknown as BrowserWindow,
    '',
    () => 'en-US'
  )
  const pending = invoke(main, 'connect-for-task') as Promise<string>
  const window = preview!
  const [, bounds] = mocks.on.mock.calls.find(([name]) => name === 'desktop-session:bounds')!
  bounds(
    { sender: window.webContents, senderFrame: window.webContents.mainFrame },
    { x: 0, y: 0, width: 500, height: 300 }
  )
  const start = Promise.withResolvers<{ queues: [] }>()
  mocks.start.mockReturnValue(start.promise)
  const connecting = invoke(window, 'start', invoke(window, 'pending'))
  const quitting = bridge.closeForAppQuit()
  await vi.waitFor(() => expect(invoke(main, 'prompt:get')).toMatchObject({ kind: 'quit' }))
  snapshot.state = 'connected'
  start.resolve({ queues: [] })
  await connecting
  snapshot.state = state
  invoke(main, 'prompt:respond', invoke(main, 'prompt:get').id, 'cancel')
  await expect(quitting).resolves.toBe(false)
  await expect(pending).resolves.toBe(outcome)
  expect(mocks.close).not.toHaveBeenCalled()
})

it.runIf(process.platform === 'win32' && process.arch === 'x64')(
  '主窗口已经无响应时，从托盘退出改用原生确认',
  async () => {
    const main = new TestWindow() as unknown as BrowserWindow
    const bridge = registerDesktopSession(
      () => main,
      '',
      () => 'en-US'
    )
    bridge.setRendererResponsive(main, false)
    mocks.messageBox.mockResolvedValueOnce({ response: 1 })

    await expect(bridge.closeForAppQuit()).resolves.toBe(false)
    expect(mocks.messageBox).toHaveBeenCalledWith(
      main,
      expect.objectContaining({ defaultId: 1, cancelId: 1 })
    )
    expect(mocks.close).not.toHaveBeenCalled()
  }
)

it.runIf(process.platform === 'win32' && process.arch === 'x64')(
  '退出确认拦截尚未派发的连接时，结清托管请求以便重试',
  async () => {
    const main = new TestWindow()
    const bridge = registerDesktopSession(
      () => main as unknown as BrowserWindow,
      '',
      () => 'en-US'
    )
    const first = invoke(main, 'connect-for-task')
    const window = preview!
    const request = invoke(window, 'pending')
    const quitting = bridge.closeForAppQuit()
    await vi.waitFor(() => expect(invoke(main, 'prompt:get')).toMatchObject({ kind: 'quit' }))

    await invoke(window, 'start', request)
    invoke(main, 'prompt:respond', invoke(main, 'prompt:get').id, 'cancel')

    await expect(quitting).resolves.toBe(false)
    await expect(first).resolves.toBe('cancelled')
    expect(mocks.start).not.toHaveBeenCalled()
    const retry = invoke(main, 'connect-for-task')
    expect(retry).not.toBe(first)
    const nextRequest = invoke(window, 'pending')
    expect(nextRequest).toMatchObject({ forTask: true })
    invoke(window, 'cancel-task-connect', nextRequest.taskConnectId)
    await expect(retry).resolves.toBe('cancelled')
  }
)

it.runIf(process.platform === 'win32' && process.arch === 'x64')(
  '预览崩溃后再次启动托管会重新加载页面并处理新的连接请求',
  async () => {
    const main = new TestWindow()
    registerDesktopSession(
      () => main as unknown as BrowserWindow,
      '',
      () => 'en-US'
    )
    const first = invoke(main, 'connect-for-task')
    const window = preview!
    window.crashed = true
    window.webContents.emit('render-process-gone')
    await expect(first).resolves.toBe('failed')

    const retry = invoke(main, 'connect-for-task')
    expect(window.webContents.isCrashed()).toBe(false)
    const nextRequest = invoke(window, 'pending')
    expect(nextRequest).toMatchObject({ forTask: true })
    invoke(window, 'cancel-task-connect', nextRequest.taskConnectId)
    await expect(retry).resolves.toBe('cancelled')
  }
)

it.runIf(process.platform === 'win32' && process.arch === 'x64').each(['unresponsive', 'timeout'])(
  '预览未接单时结束启动等待，拒绝迟到的请求 (%s)',
  async failure => {
    vi.useFakeTimers()
    try {
      const main = new TestWindow()
      registerDesktopSession(
        () => main as unknown as BrowserWindow,
        '',
        () => 'en-US'
      )
      const first = invoke(main, 'connect-for-task')
      const window = preview!
      const expired = invoke(window, 'pending')
      if (failure === 'unresponsive') {
        window.emit('unresponsive')
        await expect(invoke(main, 'connect-for-task')).resolves.toBe('preview_unavailable')
        window.emit('responsive')
      } else {
        await vi.advanceTimersByTimeAsync(300_000)
      }
      await expect(first).resolves.toBe('preview_unavailable')

      const retry = invoke(main, 'connect-for-task')
      const current = invoke(window, 'pending')
      expect(current.taskConnectId).not.toBe(expired.taskConnectId)
      await expect(invoke(window, 'start', expired)).resolves.toMatchObject({
        code: 'preview_unavailable',
      })
      expect(mocks.start).not.toHaveBeenCalled()
      invoke(window, 'cancel-task-connect', current.taskConnectId)
      await expect(retry).resolves.toBe('cancelled')
    } finally {
      vi.useRealTimers()
    }
  }
)

it
  .runIf(process.platform === 'win32' && process.arch === 'x64')
  .each(['while connecting', 'while waiting for password'])(
  '预览失去响应后结束密码等待，并允许重新连接 (%s)',
  async failure => {
    const main = new TestWindow()
    registerDesktopSession(
      () => main as unknown as BrowserWindow,
      '',
      () => 'en-US'
    )
    const first = invoke(main, 'connect-for-task')
    const window = preview!
    const expired = invoke(window, 'pending')
    const [, bounds] = mocks.on.mock.calls.find(([name]) => name === 'desktop-session:bounds')!
    bounds(
      { sender: window.webContents, senderFrame: window.webContents.mainFrame },
      { x: 0, y: 0, width: 500, height: 300 }
    )
    const start = Promise.withResolvers<{ code: string; queues: [] }>()
    mocks.start.mockReturnValueOnce(start.promise)
    const connecting = invoke(window, 'start', expired)
    if (failure === 'while connecting') {
      window.emit('unresponsive')
      expect(invoke(main, 'connect-for-task')).toBe(first)
    }
    start.resolve({ code: 'password_required', queues: [] })
    if (failure === 'while waiting for password') {
      await expect(connecting).resolves.toMatchObject({ code: 'password_required' })
      window.emit('unresponsive')
    } else {
      await expect(connecting).resolves.toMatchObject({ code: 'preview_unavailable' })
    }
    await expect(first).resolves.toBe('preview_unavailable')

    window.emit('responsive')
    const retry = invoke(main, 'connect-for-task')
    const current = invoke(window, 'pending')
    expect(current.taskConnectId).not.toBe(expired.taskConnectId)
    await expect(
      invoke(window, 'start', { ...expired, password: 'late-password' })
    ).resolves.toMatchObject({
      code: 'preview_unavailable',
    })
    expect(mocks.start).toHaveBeenCalledTimes(1)
    mocks.start.mockResolvedValueOnce({ queues: [] })
    snapshot.state = 'connected'
    await invoke(window, 'start', current)
    await expect(retry).resolves.toBe('connected')
  }
)
