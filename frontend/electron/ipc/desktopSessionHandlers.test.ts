import { expect, it, vi } from 'vite-plus/test'
import { registerDesktopSession } from './desktopSessionHandlers'

const ipc = vi.hoisted(() => ({
  calls: new Map<string, (...args: unknown[]) => unknown>(),
  events: new Map<string, (...args: unknown[]) => unknown>(),
  windows: [] as unknown[],
}))
const session = vi.hoisted(() => ({
  snapshot: { state: 'connecting', busy: true, executing: false },
  active: true,
  position: vi.fn(),
  close: vi.fn(),
  changeWindow: vi.fn(),
  closeRisk: vi.fn(),
  start: vi.fn(),
}))

vi.mock('electron', async () => {
  const { EventEmitter } = await import('node:events')
  class Window extends EventEmitter {
    webContents = Object.assign(new EventEmitter(), {
      send: vi.fn(),
      setWindowOpenHandler: vi.fn(),
    })
    isDestroyed = () => false
    isVisible = () => true
    isMinimized = () => false
    focus = vi.fn()
    show = vi.fn()
    loadURL = vi.fn()
    getContentBounds = () => ({ x: 0, y: 0, width: 600, height: 400 })
    getNativeWindowHandle = () => Buffer.alloc(8)
    constructor() {
      super()
      ipc.windows.push(this)
    }
  }
  return {
    BrowserWindow: Window,
    app: {},
    dialog: {},
    shell: {},
    screen: { getDisplayMatching: () => ({ scaleFactor: 1 }) },
    ipcMain: {
      handle: (channel: string, handler: (...args: unknown[]) => unknown) =>
        ipc.calls.set(channel, handler),
      on: (channel: string, handler: (...args: unknown[]) => unknown) =>
        ipc.events.set(channel, handler),
    },
  }
})
vi.mock('./analyticsHandlers', () => ({
  isApplicationWindowSender: (event: { owner: unknown }, owner: unknown) => owner === event.owner,
}))
vi.mock('../services/featureAnalytics', () => ({ beginMainFeature: vi.fn() }))
vi.mock('../services/instanceConfig', () => ({
  getBackendOwnership: () => 'owned',
  getDevelopmentServerUrl: () => 'http://127.0.0.1:5173',
  getRendererEnvironmentArguments: () => [],
}))
vi.mock('../services/desktopSessionService', () => ({
  DesktopSessionService: class {
    constructor() {
      return session
    }
  },
}))

it.skipIf(process.platform !== 'win32' || process.arch !== 'x64').each([
  ['connected', 'connected'],
  ['disconnected', 'failed'],
])(
  'settles the task when exit is cancelled and the desktop has become %s',
  async (finalState, outcome) => {
    ipc.calls.clear()
    ipc.events.clear()
    ipc.windows.length = 0
    session.snapshot.state = 'connecting'
    session.close.mockClear()
    const { BrowserWindow } = await import('electron')
    const main = new BrowserWindow()
    const lifecycle = registerDesktopSession(
      () => main,
      '',
      () => 'en-US'
    )
    const mainEvent = { owner: main }
    const start = Promise.withResolvers<{ queues: [] }>()
    session.start.mockReturnValue(start.promise)
    session.closeRisk.mockResolvedValue({ activeTasks: false, unmanagedPrograms: null })

    const connected = ipc.calls.get('desktop-session:connect-for-task')!(
      mainEvent
    ) as Promise<string>
    const delivered = vi.fn()
    void connected.then(delivered)
    const previewEvent = {
      owner: ipc.windows[1],
      senderFrame: { url: 'http://127.0.0.1:5173/#/desktop-session' },
    }
    ipc.events.get('desktop-session:bounds')!(previewEvent, { x: 0, y: 0, width: 500, height: 300 })
    const request = { queueIds: [], mode: 'proxy', resolution: '1080p' }
    const connecting = ipc.calls.get('desktop-session:start')!(previewEvent, request)

    const quitting = lifecycle.closeForAppQuit()
    const getPrompt = () =>
      ipc.calls.get('desktop-session:prompt:get')!(mainEvent) as { id: number; kind: string } | null
    await vi.waitFor(() => expect(getPrompt()?.kind).toBe('quit'))
    session.snapshot.state = 'connected'
    start.resolve({ queues: [] })
    await connecting
    expect(delivered).not.toHaveBeenCalled()

    session.snapshot.state = finalState
    ipc.calls.get('desktop-session:prompt:respond')!(mainEvent, getPrompt()!.id, 'cancel')
    expect(await quitting).toBe(false)
    expect(await connected).toBe(outcome)
    expect(session.close).not.toHaveBeenCalled()
    if (finalState === 'disconnected') {
      const retry = ipc.calls.get('desktop-session:connect-for-task')!(mainEvent)
      expect(retry).not.toBe(connected)
      ipc.calls.get('desktop-session:cancel-task-connect')!(previewEvent)
      expect(await retry).toBe('cancelled')
    }
  }
)
