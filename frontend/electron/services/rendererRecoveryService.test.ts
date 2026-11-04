import type { BrowserWindow } from 'electron'
import { EventEmitter } from 'node:events'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { analyticsService } from './analyticsService'
import { attachRendererRecovery, RENDERER_RELOAD_TIMEOUT_MS } from './rendererRecoveryService'

const reports = vi.hoisted(() => ({
  crash: vi.fn(),
  reload: vi.fn(),
  send: vi.fn(async () => {}),
}))
vi.mock('./logger', () => ({ getLogger: () => ({ info: vi.fn(), error: vi.fn() }) }))
vi.mock('./sentry', () => ({
  captureMainRendererCrash: reports.crash,
  beginMainRendererReload: () => reports.reload,
}))
vi.mock('./analyticsService', async () => {
  const { AnalyticsService } = await import('./analytics')
  return {
    analyticsService: new AnalyticsService({
      isAllowed: () => true,
      systemProps: () => ({
        isDebug: false,
        locale: 'test',
        osName: 'Windows',
        osVersion: 'test',
        engineName: 'Chromium',
        engineVersion: 'test',
        appVersion: 'test',
        sdkVersion: 'test',
      }),
      send: reports.send,
    }),
  }
})

class TestWindow extends EventEmitter {
  webContents = Object.assign(new EventEmitter(), {
    mainFrame: { processId: 10, routingId: 20 },
    reload: vi.fn(() => this.webContents.emit('did-start-loading')),
  })
  isDestroyed = () => false
  hooks = new Map<number, (wParam: Buffer) => void>()
  hookWindowMessage = (message: number, callback: (wParam: Buffer) => void) => {
    this.hooks.set(message, callback)
  }
}

let win: TestWindow
let recovery: ReturnType<typeof attachRendererRecovery>
let quitting: boolean
let crashHistory: number[]
const originalPlatform = Object.getOwnPropertyDescriptor(process, 'platform')!
const crash = () =>
  win.webContents.emit('render-process-gone', {}, { reason: 'killed', exitCode: 1073807364 })
const ready = () => {
  win.webContents.emit('did-finish-load')
  recovery.rendererReady(win.webContents.mainFrame)
}
const flushTelemetry = async () => {
  for (let i = 0; i < 8; i++) await Promise.resolve()
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.clearAllMocks()
  Object.defineProperty(process, 'platform', { value: 'win32' })
  analyticsService.setEnabled(false)
  analyticsService.setEnabled(true)
  win = new TestWindow()
  quitting = false
  crashHistory = []
  recovery = attachRendererRecovery(win as unknown as BrowserWindow, {
    crashHistory,
    isQuitting: () => quitting,
    onRendererGone: vi.fn(),
    onReload: vi.fn(),
  })
})
afterEach(() => {
  win.emit('closed')
  analyticsService.setEnabled(false)
  Object.defineProperty(process, 'platform', originalPlatform)
  vi.useRealTimers()
})

describe('渲染进程恢复结果', () => {
  it('再次退出先结束旧尝试，连续退出最多重载三次', () => {
    crash()
    crash()
    expect(reports.reload).toHaveBeenCalledExactlyOnceWith(
      expect.objectContaining({ outcome: 'failure', resultKind: 'renderer_gone' })
    )
    crash()
    crash()
    expect(win.webContents.reload).toHaveBeenCalledTimes(3)
    expect(reports.crash).toHaveBeenLastCalledWith(
      expect.objectContaining({ action: 'give-up', crashCount: 4 })
    )
    ready()
    expect(reports.reload).toHaveBeenCalledTimes(3)
  })

  it('会话结束不制造崩溃或重载，取消关机后重新恢复', async () => {
    win.emit('query-session-end')
    crash()
    expect(recovery.isSessionEnding()).toBe(true)
    expect(reports.crash).not.toHaveBeenCalled()
    expect(win.webContents.reload).not.toHaveBeenCalled()
    win.hooks.get(0x0016)!(Buffer.alloc(8))
    expect(recovery.isSessionEnding()).toBe(false)
    expect(win.webContents.reload).toHaveBeenCalledTimes(1)
    win.emit('session-end')
    crash()
    ready()
    expect(reports.reload).toHaveBeenCalledExactlyOnceWith(
      expect.objectContaining({ outcome: 'cancelled', resultKind: 'session_end' })
    )
    expect(reports.crash).toHaveBeenCalledTimes(1)
    await flushTelemetry()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('取消关机后重建正常退出的 renderer，但不伪造崩溃', () => {
    win.emit('query-session-end')
    win.webContents.emit('render-process-gone', {}, { reason: 'clean-exit', exitCode: 0 })
    win.hooks.get(0x0016)!(Buffer.alloc(8))
    expect(win.webContents.reload).toHaveBeenCalledTimes(1)
    expect(reports.crash).not.toHaveBeenCalled()
    ready()
    expect(reports.reload).toHaveBeenCalledExactlyOnceWith(
      expect.objectContaining({ outcome: 'success' })
    )
  })

  it('重建主窗口仍共享同一进程的重载预算', () => {
    crash()
    crash()
    win.emit('closed')
    win = new TestWindow()
    recovery = attachRendererRecovery(win as unknown as BrowserWindow, {
      crashHistory,
      isQuitting: () => false,
      onRendererGone: vi.fn(),
      onReload: vi.fn(),
    })
    crash()
    crash()
    expect(win.webContents.reload).toHaveBeenCalledTimes(1)
    expect(reports.crash).toHaveBeenLastCalledWith(
      expect.objectContaining({ action: 'give-up', crashCount: 4 })
    )
  })

  it('退出期间不重载，正在退出的尝试不记为超时失败', () => {
    crash()
    quitting = true
    vi.advanceTimersByTime(RENDERER_RELOAD_TIMEOUT_MS)
    expect(reports.reload).toHaveBeenLastCalledWith(
      expect.objectContaining({ outcome: 'cancelled', resultKind: 'app_quitting' })
    )
    crash()
    expect(win.webContents.reload).toHaveBeenCalledTimes(1)
  })
})
