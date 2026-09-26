import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  qq: { status: vi.fn(), start: vi.fn(), check: vi.fn(), unbind: vi.fn() },
}))
vi.mock('@/api', () => ({
  QqService: {
    getStatusApiSettingOpenclawQqStatusPost: mocks.qq.status,
    startLoginApiSettingOpenclawQqLoginStartPost: mocks.qq.start,
    checkLoginApiSettingOpenclawQqLoginCheckPost: mocks.qq.check,
    unbindApiSettingOpenclawQqUnbindPost: mocks.qq.unbind,
  },
}))
vi.mock('vue', async original => ({
  ...(await original<typeof import('vue')>()),
  onMounted: vi.fn(),
  onBeforeUnmount: vi.fn(),
}))
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }))
vi.mock('ant-design-vue', () => ({ message: { success: vi.fn(), error: vi.fn() } }))
vi.mock('qrcode', () => ({ default: { toDataURL: async () => 'data:qr' } }))
import { useClawBinding } from './useClawBinding'

beforeEach(() => {
  vi.resetAllMocks()
  vi.useFakeTimers()
})
afterEach(() => vi.useRealTimers())

describe('QQ QR binding', () => {
  const channel = 'qq' as const
  it('uses the selected service and stops polling after expiration', async () => {
    const api = mocks[channel]
    api.start.mockResolvedValue({ code: 200, sessionId: channel, qrUrl: 'qr' })
    api.check
      .mockResolvedValueOnce({ code: 200, state: 'waiting' })
      .mockResolvedValueOnce({ code: 200, state: 'expired' })
    const flow = useClawBinding(channel, vi.fn())
    await flow.start()
    await vi.advanceTimersByTimeAsync(10000)
    expect(api.check).toHaveBeenCalledTimes(2)
    expect(api.check).toHaveBeenCalledWith({ sessionId: channel })
    expect(flow.state.value).toBe('expired')
    flow.close()
  })
  it('ignores an old login response after reopening', async () => {
    const api = mocks[channel]
    let resolveOld!: (result: object) => void
    api.start.mockResolvedValue({ code: 200, sessionId: channel, qrUrl: 'qr' })
    api.check
      .mockReturnValueOnce(
        new Promise(resolve => {
          resolveOld = resolve
        })
      )
      .mockResolvedValueOnce({ code: 200, state: 'scanned' })
    const onChange = vi.fn()
    const flow = useClawBinding(channel, onChange)
    await flow.start()
    await flow.start()
    resolveOld({ code: 200, connected: true })
    await Promise.resolve()
    expect(flow.state.value).toBe('scanned')
    expect(onChange).not.toHaveBeenCalled()
    flow.close()
  })
})

it('defaults to enabled only for the first binding, not for a rebind', async () => {
  mocks.qq.start.mockResolvedValue({ code: 200, sessionId: 'qq', qrUrl: 'qr' })
  mocks.qq.check.mockResolvedValue({ code: 200, state: 'connected', connected: true })
  mocks.qq.status.mockResolvedValue({
    code: 200,
    enabled: true,
    connected: true,
    state: 'connected',
  })
  const onChange = vi.fn().mockResolvedValue(undefined)
  const flow = useClawBinding('qq', onChange)

  await flow.start()
  await vi.waitFor(() => expect(onChange).toHaveBeenCalledTimes(1))
  expect(onChange).toHaveBeenCalledWith(true)

  await flow.start()
  await vi.waitFor(() => expect(mocks.qq.check).toHaveBeenCalledTimes(2))
  expect(onChange).toHaveBeenCalledTimes(1)
  flow.close()
})
