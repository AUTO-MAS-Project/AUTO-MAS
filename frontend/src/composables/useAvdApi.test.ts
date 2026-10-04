import { beforeEach, describe, expect, it, vi } from 'vitest'

const statusRequest = vi.fn()
const addPathRequest = vi.fn()

class FakeApiError extends Error {
  body: unknown
  constructor(body: unknown) {
    super('Internal Server Error')
    this.body = body
  }
}

vi.mock('@/api', () => ({
  ApiError: FakeApiError,
  Emulator20Service: {
    avdStatusApiEmulator2AvdStatusPost: statusRequest,
    addPathApiEmulator2PathsAddPost: addPathRequest,
  },
}))

vi.mock('@/i18n', () => ({ t: (key: string) => `i18n:${key}` }))

const load = async () => (await import('./useAvdApi')).useAvdApi()

describe('useAvdApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('passes refresh through and returns the payload', async () => {
    statusRequest.mockResolvedValueOnce({ code: 200, ready: true })
    const api = await load()
    await expect(api.getStatus('E:\\avd', true)).resolves.toMatchObject({ ready: true })
    expect(statusRequest).toHaveBeenCalledWith({ root: 'E:\\avd', refresh: true })
    expect(api.loading.value).toBe(false)
    expect(api.error.value).toBeNull()
  })

  it('business failure: backend message, else the i18n fallback', async () => {
    const api = await load()
    statusRequest.mockResolvedValueOnce({ code: 500, message: '根目录不可用' })
    await expect(api.getStatus('E:\\avd')).rejects.toThrow('根目录不可用')
    expect(api.error.value).toBe('根目录不可用')
    statusRequest.mockResolvedValueOnce({ code: 500 })
    await expect(api.getStatus('E:\\avd')).rejects.toThrow('i18n:emulator2.avd.toast.statusFailed')
  })

  it('ApiError: reads body.message, falls back to the i18n text', async () => {
    const api = await load()
    statusRequest.mockRejectedValueOnce(new FakeApiError({ message: '后端崩了' }))
    await expect(api.getStatus('E:\\avd')).rejects.toThrow('后端崩了')
    statusRequest.mockRejectedValueOnce(new FakeApiError(null))
    // ApiError without a body message keeps its own message
    await expect(api.getStatus('E:\\avd')).rejects.toThrow('Internal Server Error')
  })

  it('tracks loading while a request is in flight', async () => {
    let resolve!: (_value: unknown) => void
    statusRequest.mockReturnValueOnce(new Promise(r => (resolve = r)))
    const api = await load()
    const pending = api.getStatus('E:\\avd')
    expect(api.loading.value).toBe(true)
    resolve({ code: 200 })
    await pending
    expect(api.loading.value).toBe(false)
  })

  it('adding a root that is already there is returned, not thrown', async () => {
    addPathRequest.mockResolvedValueOnce({ code: 200, ok: false, reason: 'already_added' })
    const api = await load()
    await expect(api.addRoot('emu', 'E:\\avd')).resolves.toMatchObject({
      ok: false,
      reason: 'already_added',
    })
    expect(addPathRequest).toHaveBeenCalledWith({
      emulatorId: 'emu',
      installPath: 'E:\\avd',
      alias: null,
    })
  })
})
