import { expect, it, vi } from 'vite-plus/test'
import {
  WS_DESKTOP_SESSION_LOGIN_FINISHED,
  WS_DESKTOP_SESSION_LOGIN_NEEDED,
  WS_ID_MAIN,
} from './websocket/types'

const { prompt, send } = vi.hoisted(() => ({
  prompt: vi.fn<() => Promise<boolean>>(),
  send: vi.fn(),
}))
vi.mock('@/composables/useDesktopSessionLogin', () => ({ promptScheduledDesktopLogin: prompt }))
vi.mock('./websocket/connection', () => ({ send }))
vi.mock('@/i18n', () => ({ translate: vi.fn() }))
vi.mock('ant-design-vue', () => ({ notification: {} }))

it('断线时取消登录，重投只回送取消结果，下次独立触发仍可登录', async () => {
  vi.stubGlobal('window', { electronAPI: { getLogger: () => ({ warn: vi.fn() }) } })
  const { bootstrapSystemNotices, disposeSystemNotices } = await import('./systemNotices')
  const { dispatchMessage } = await import('./websocket/subscriptions')
  const deliver = (requestId: string) =>
    dispatchMessage({ id: WS_ID_MAIN, type: WS_DESKTOP_SESSION_LOGIN_NEEDED, data: { requestId } })
  let cancel!: (retry: boolean) => void
  prompt
    .mockReturnValueOnce(
      new Promise<boolean>(resolve => {
        cancel = resolve
      })
    )
    .mockResolvedValue(true)
  bootstrapSystemNotices()
  try {
    deliver('first')
    await vi.waitFor(() => expect(prompt).toHaveBeenCalledTimes(1))
    send.mockReturnValueOnce(false)
    cancel(false)
    const cancelled = { requestId: 'first', retryStartup: false }
    await vi.waitFor(() =>
      expect(send).toHaveBeenCalledWith(WS_ID_MAIN, WS_DESKTOP_SESSION_LOGIN_FINISHED, cancelled)
    )

    send.mockReturnValue(true)
    deliver('first')
    await vi.waitFor(() => expect(send).toHaveBeenCalledTimes(2))
    expect(send).toHaveBeenLastCalledWith(WS_ID_MAIN, WS_DESKTOP_SESSION_LOGIN_FINISHED, cancelled)
    expect(prompt).toHaveBeenCalledTimes(1)

    deliver('next')
    await vi.waitFor(() =>
      expect(send).toHaveBeenLastCalledWith(WS_ID_MAIN, WS_DESKTOP_SESSION_LOGIN_FINISHED, {
        requestId: 'next',
        retryStartup: true,
      })
    )
    expect(prompt).toHaveBeenCalledTimes(2)
  } finally {
    disposeSystemNotices()
    vi.unstubAllGlobals()
  }
})
