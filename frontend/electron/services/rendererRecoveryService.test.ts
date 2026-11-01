import { EventEmitter } from 'node:events'
import type { BrowserWindow } from 'electron'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { attachRendererRecovery, RENDERER_RELOAD_TIMEOUT_MS } from './rendererRecoveryService'
import { analyticsService } from './analyticsService'
import { validateAnalyticsEvent } from './analyticsPolicy'

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
const originalPlatform = Object.getOwnPropertyDescriptor(process, 'platform')!
const crash = () =>
  win.webContents.emit('render-process-gone', {}, { reason: 'killed', exitCode: 1073807364 })
const failedLoad = (code = -6, isMainFrame = true, processId = 10) => {
  win.webContents.emit(
    'did-fail-load',
    {},
    code,
    'private error',
    'file:///private',
    isMainFrame,
    processId,
    20
  )
}
const ready = () => {
  win.webContents.emit('did-finish-load')
  recovery.rendererReady()
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
  recovery = attachRendererRecovery(win as unknown as BrowserWindow, {
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
  it('普通启动不制造重载结果，加载和挂载缺一不算恢复成功', async () => {
    ready()
    expect(reports.reload).not.toHaveBeenCalled()
    crash()
    win.webContents.emit('did-finish-load')
    expect(reports.reload).not.toHaveBeenCalled()
    recovery.rendererReady()
    ready()
    expect(reports.reload).toHaveBeenCalledExactlyOnceWith(
      expect.objectContaining({ outcome: 'success', resultKind: 'ready' })
    )
    await flushTelemetry()
    const results = reports.send.mock.calls
      .map(([payload]) => payload)
      .filter(payload => payload.eventName === 'renderer_recovery_finished')
    expect(results).toHaveLength(1)
    expect(
      validateAnalyticsEvent({ name: results[0].eventName, props: results[0].props }, false)
    ).not.toBeNull()
    expect(
      validateAnalyticsEvent({ name: results[0].eventName, props: results[0].props }, true)
    ).toBeNull()
    expect(
      validateAnalyticsEvent(
        { name: results[0].eventName, props: { ...results[0].props, url: 'private' } },
        false
      )
    ).toBeNull()
  })

  it('挂载 IPC 早于加载完成时也只结算一次', () => {
    crash()
    recovery.rendererReady()
    expect(reports.reload).not.toHaveBeenCalled()
    win.webContents.emit('did-finish-load')
    expect(reports.reload).toHaveBeenCalledTimes(1)
  })

  it('忽略子 frame、旧进程与被替换导航的失败，保留当前主页面的成功', () => {
    crash()
    failedLoad(-6, false)
    failedLoad(-3)
    failedLoad(-6, true, 9)
    expect(reports.reload).not.toHaveBeenCalled()
    ready()
    expect(reports.reload).toHaveBeenCalledWith(expect.objectContaining({ outcome: 'success' }))
  })

  it('主页面加载失败后，错误页加载和挂载不能反转结果', async () => {
    crash()
    failedLoad()
    ready()
    expect(reports.reload).toHaveBeenCalledExactlyOnceWith(
      expect.objectContaining({ outcome: 'failure', resultKind: 'load_failed', loadErrorCode: -6 })
    )
    await flushTelemetry()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('reload 抛错与超时分别记录失败和未知，迟到信号不补报', () => {
    win.webContents.reload.mockImplementationOnce(() => {
      throw new Error('private')
    })
    crash()
    expect(reports.reload).toHaveBeenLastCalledWith(
      expect.objectContaining({ outcome: 'failure', resultKind: 'reload_threw' })
    )
    crash()
    vi.advanceTimersByTime(RENDERER_RELOAD_TIMEOUT_MS)
    expect(reports.reload).toHaveBeenLastCalledWith(
      expect.objectContaining({ outcome: 'unknown', resultKind: 'timeout' })
    )
    ready()
    expect(reports.reload).toHaveBeenCalledTimes(2)
  })

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

  it('窗口销毁取消未决观察并清理超时', () => {
    crash()
    win.webContents.emit('destroyed')
    win.emit('closed')
    vi.advanceTimersByTime(RENDERER_RELOAD_TIMEOUT_MS)
    expect(reports.reload).toHaveBeenCalledExactlyOnceWith(
      expect.objectContaining({ outcome: 'cancelled', resultKind: 'window_closed' })
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

  it('关闭再开启统计不补发旧尝试，新尝试仍能记录', async () => {
    crash()
    await flushTelemetry()
    reports.send.mockClear()
    analyticsService.setEnabled(false)
    analyticsService.setEnabled(true)
    ready()
    await flushTelemetry()
    expect(reports.send).not.toHaveBeenCalled()
    crash()
    ready()
    await flushTelemetry()
    expect(
      reports.send.mock.calls.filter(
        ([payload]) => payload.eventName === 'renderer_recovery_finished'
      )
    ).toHaveLength(1)
  })
})
