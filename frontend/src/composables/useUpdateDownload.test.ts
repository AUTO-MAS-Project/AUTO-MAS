import { afterEach, beforeEach, expect, it, vi } from 'vite-plus/test'
import type { AppUpdateEvent } from '../../electron/services/appUpdateTypes'

const boundary = vi.hoisted(() => ({
  start: vi.fn(),
  switchToCnb: vi.fn(),
  cancel: vi.fn(),
  finishDownload: vi.fn(),
  started: vi.fn(),
  finishSwitch: vi.fn(),
}))
vi.mock('@/services/updateDownloadApi', () => ({ updateDownloadApi: boundary }))
vi.mock('@/i18n', () => ({ translate: (key: string) => key }))
vi.mock('@/services/websocket/connection', () => ({
  connectionState: () => ({ value: 'closed' }),
  onConnected: vi.fn(),
}))
vi.mock('@/utils/analytics', () => ({
  beginAnalyticsOperation: () => ({ finish: boundary.finishSwitch }),
}))
vi.mock('@/utils/updateAnalytics', () => ({
  analyticsUpdateSource: (source: string) => source,
  beginDownloadAnalytics: () => ({ started: boundary.started, finish: boundary.finishDownload }),
}))
vi.mock('ant-design-vue', () => ({
  Modal: { confirm: vi.fn() },
  message: { error: vi.fn(), success: vi.fn() },
}))

let flow: ReturnType<typeof import('./useUpdateDownload').useUpdateDownload>
let receive: (event: AppUpdateEvent) => void
const snapshot = (status: AppUpdateEvent['snapshot']['status'], source = 'GitHub') => ({
  status,
  source,
  version: 'v5.9.0',
  downloaded_size: 0,
  file_size: 100,
  speed: 0,
  file: null,
  message: null,
})

beforeEach(async () => {
  // 只隔离桌面事件、IPC 和统计传输，保留真实窗口状态及操作代次处理。
  vi.clearAllMocks()
  vi.stubGlobal('window', {
    electronAPI: {
      getLogger: () => ({ info: vi.fn(), warn: vi.fn(), error: vi.fn() }),
      onAppUpdate: (listener: typeof receive) => {
        receive = listener
        return () => {}
      },
    },
  })
  flow = (await import('./useUpdateDownload')).useUpdateDownload()
  boundary.start.mockResolvedValue({ code: 200 })
})
afterEach(() => {
  // 释放模块持有的订阅、计时器和界面状态，避免后续场景接收到旧事件。
  flow.disposeUpdateDownloadSubscriptions()
  flow.reset()
  vi.unstubAllGlobals()
})

it.each(['completed', 'failed'] as const)(
  '换源保持窗口与整次下载观察，%s 事件只结束一次',
  async terminal => {
    // 换源进度不能被当成普通下载或终态，保存/预检失败也须在原窗口显示。
    let resolve!: (result: { code: number }) => void
    let reject!: (error: unknown) => void
    boundary.switchToCnb.mockReturnValue(
      new Promise<{ code: number }>((complete, fail) => {
        resolve = complete
        reject = fail
      })
    )
    await flow.start('v5.9.0', {})
    receive({ type: 'progress', snapshot: snapshot('downloading') })
    const switching = flow.switchToCnb()
    receive({ type: 'progress', snapshot: snapshot('switchingSource') })
    expect(flow.status.value).toBe('switchingSource')
    expect(flow.modalVisible.value).toBe(true)
    expect(boundary.finishDownload).not.toHaveBeenCalled()
    if (terminal === 'completed')
      receive({ type: 'progress', snapshot: snapshot('downloading', 'CNB') })
    receive({
      type: terminal,
      snapshot: {
        ...snapshot(terminal, 'CNB'),
        message: terminal === 'failed' ? 'precheck failed' : null,
      },
    })
    if (terminal === 'completed') resolve({ code: 200 })
    else reject(new Error('precheck failed'))
    await switching
    expect(flow.status.value).toBe(terminal)
    expect(flow.modalVisible.value).toBe(true)
    expect(boundary.finishDownload).toHaveBeenCalledExactlyOnceWith('CNB', terminal)
    if (terminal === 'failed') expect(flow.failureReason.value).toBe('precheck failed')
  }
)

it('换源途中允许用户取消，并由取消事件结束同一次下载', async () => {
  // 取消优先于尚未返回的换源请求，迟到的请求结果不能重新打开下载窗口。
  let reject!: (error: unknown) => void
  boundary.switchToCnb.mockReturnValue(
    new Promise<{ code: number }>((_complete, fail) => {
      reject = fail
    })
  )
  boundary.cancel.mockImplementation(async () => {
    receive({ type: 'cancelled', snapshot: snapshot('cancelled') })
    return { code: 200 }
  })
  await flow.start('v5.9.0', {})
  const switching = flow.switchToCnb()
  receive({ type: 'progress', snapshot: snapshot('switchingSource') })
  await flow.cancel()
  reject(new DOMException('cancelled', 'AbortError'))
  await switching
  expect(flow.status.value).toBe('idle')
  expect(flow.modalVisible.value).toBe(false)
  expect(boundary.finishDownload).toHaveBeenCalledExactlyOnceWith('GitHub', 'cancelled')
})
