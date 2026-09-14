import { beforeEach, describe, expect, it, vi } from 'vitest'

const loadDevicesRequest = vi.fn()
const showError = vi.fn()

vi.mock('@/api', () => ({
  Service: {
    getEmulatorDevicesComboxApiInfoComboxEmulatorDevicesPost: loadDevicesRequest,
  },
}))

vi.mock('ant-design-vue', () => ({
  message: {
    error: showError,
  },
}))

const deferred = <T>() => {
  let resolve!: (_value: T) => void
  const promise = new Promise<T>(resolvePromise => {
    resolve = resolvePromise
  })
  return { promise, resolve }
}

describe('useEmulatorDeviceOptions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // 缓存是模块级的，每个用例都要从干净的模块开始
    vi.resetModules()
  })

  it('tracks loading without blocking the caller', async () => {
    const request = deferred<{ code: number; data: { label: string; value: string }[] }>()
    loadDevicesRequest.mockReturnValueOnce(request.promise)
    const { emulatorDeviceLoading, emulatorDeviceOptions, loadEmulatorDeviceOptions } =
      await import('./useEmulatorDeviceOptions').then(module => module.useEmulatorDeviceOptions())

    const loadingPromise = loadEmulatorDeviceOptions('emulator-a')

    expect(emulatorDeviceLoading.value).toBe(true)
    expect(emulatorDeviceOptions.value).toEqual([])

    request.resolve({ code: 200, data: [{ label: '实例 0', value: '0' }] })
    await loadingPromise

    expect(emulatorDeviceLoading.value).toBe(false)
    expect(emulatorDeviceOptions.value).toEqual([{ label: '实例 0', value: '0' }])
  })

  it('keeps the latest response when requests finish out of order', async () => {
    const first = deferred<{ code: number; data: { label: string; value: string }[] }>()
    const second = deferred<{ code: number; data: { label: string; value: string }[] }>()
    loadDevicesRequest.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const { emulatorDeviceOptions, loadEmulatorDeviceOptions } =
      await import('./useEmulatorDeviceOptions').then(module => module.useEmulatorDeviceOptions())

    const firstPromise = loadEmulatorDeviceOptions('emulator-a')
    const secondPromise = loadEmulatorDeviceOptions('emulator-b')

    second.resolve({ code: 200, data: [{ label: '新实例', value: '1' }] })
    await secondPromise
    first.resolve({ code: 200, data: [{ label: '旧实例', value: '0' }] })
    await firstPromise

    expect(emulatorDeviceOptions.value).toEqual([{ label: '新实例', value: '1' }])
  })

  it('invalidates a pending response when options are cleared', async () => {
    const request = deferred<{ code: number; data: { label: string; value: string }[] }>()
    loadDevicesRequest.mockReturnValueOnce(request.promise)
    const {
      clearEmulatorDeviceOptions,
      emulatorDeviceLoading,
      emulatorDeviceOptions,
      loadEmulatorDeviceOptions,
    } = await import('./useEmulatorDeviceOptions').then(module => module.useEmulatorDeviceOptions())

    const loadingPromise = loadEmulatorDeviceOptions('emulator-a')
    clearEmulatorDeviceOptions()
    request.resolve({ code: 200, data: [{ label: '旧实例', value: '0' }] })
    await loadingPromise

    expect(emulatorDeviceLoading.value).toBe(false)
    expect(emulatorDeviceOptions.value).toEqual([])
  })

  it('caches successful responses; clearing the page keeps the shared cache', async () => {
    loadDevicesRequest.mockResolvedValueOnce({
      code: 200,
      data: [{ label: '实例 0', value: '0' }],
    })
    const { clearEmulatorDeviceOptions, emulatorDeviceOptions, loadEmulatorDeviceOptions } =
      await import('./useEmulatorDeviceOptions').then(module => module.useEmulatorDeviceOptions())

    await loadEmulatorDeviceOptions('emulator-a')
    await loadEmulatorDeviceOptions('emulator-a')

    expect(loadDevicesRequest).toHaveBeenCalledTimes(1)
    expect(emulatorDeviceOptions.value).toEqual([{ label: '实例 0', value: '0' }])

    // 清空只是本页没选模拟器了，别的页面刚缓存的列表不该跟着没
    clearEmulatorDeviceOptions()
    expect(emulatorDeviceOptions.value).toEqual([])
    await loadEmulatorDeviceOptions('emulator-a')

    expect(loadDevicesRequest).toHaveBeenCalledTimes(1)
    expect(emulatorDeviceOptions.value).toEqual([{ label: '实例 0', value: '0' }])
  })

  it('shares cached options across composable instances until invalidated', async () => {
    loadDevicesRequest
      .mockResolvedValueOnce({ code: 200, data: [{ label: '#0 实例', value: '0' }] })
      .mockResolvedValueOnce({ code: 200, data: [{ label: '#1 实例', value: '1' }] })
    const module = await import('./useEmulatorDeviceOptions')
    const first = module.useEmulatorDeviceOptions()
    const second = module.useEmulatorDeviceOptions()

    await first.loadEmulatorDeviceOptions('emulator-a')
    await second.loadEmulatorDeviceOptions('emulator-a')

    // 另一个页面的 composable 直接吃到缓存，不再问后端
    expect(loadDevicesRequest).toHaveBeenCalledTimes(1)
    expect(second.emulatorDeviceOptions.value).toEqual([{ label: '#0 实例', value: '0' }])

    module.invalidateEmulatorDeviceOptions('emulator-a')
    await second.loadEmulatorDeviceOptions('emulator-a')

    expect(loadDevicesRequest).toHaveBeenCalledTimes(2)
    expect(second.emulatorDeviceOptions.value).toEqual([{ label: '#1 实例', value: '1' }])
  })

  it('expires cached options after the ttl', async () => {
    vi.useFakeTimers()
    try {
      loadDevicesRequest
        .mockResolvedValueOnce({ code: 200, data: [{ label: '旧', value: '0' }] })
        .mockResolvedValueOnce({ code: 200, data: [{ label: '新', value: '0' }] })
      const { emulatorDeviceOptions, loadEmulatorDeviceOptions } =
        await import('./useEmulatorDeviceOptions').then(module => module.useEmulatorDeviceOptions())

      await loadEmulatorDeviceOptions('emulator-a')
      vi.advanceTimersByTime(30_000)
      await loadEmulatorDeviceOptions('emulator-a')
      expect(loadDevicesRequest).toHaveBeenCalledTimes(1)

      vi.advanceTimersByTime(31_000)
      await loadEmulatorDeviceOptions('emulator-a')
      expect(loadDevicesRequest).toHaveBeenCalledTimes(2)
      expect(emulatorDeviceOptions.value).toEqual([{ label: '新', value: '0' }])
    } finally {
      vi.useRealTimers()
    }
  })

  it('settles empty and failed responses', async () => {
    loadDevicesRequest
      .mockResolvedValueOnce({ code: 200, data: [] })
      .mockResolvedValueOnce({ code: 500, message: '扫描失败', data: [] })
      .mockRejectedValueOnce(new Error('连接失败'))
    const { emulatorDeviceLoading, emulatorDeviceOptions, loadEmulatorDeviceOptions } =
      await import('./useEmulatorDeviceOptions').then(module => module.useEmulatorDeviceOptions())

    await loadEmulatorDeviceOptions('empty')
    expect(emulatorDeviceLoading.value).toBe(false)
    expect(emulatorDeviceOptions.value).toEqual([])

    await loadEmulatorDeviceOptions('failed')
    expect(emulatorDeviceLoading.value).toBe(false)
    expect(emulatorDeviceOptions.value).toEqual([])
    expect(showError).toHaveBeenCalledWith('扫描失败')

    await loadEmulatorDeviceOptions('rejected')
    expect(emulatorDeviceLoading.value).toBe(false)
    expect(emulatorDeviceOptions.value).toEqual([])
    expect(showError).toHaveBeenCalledWith('加载模拟器实例选项失败: 连接失败')
  })
})
