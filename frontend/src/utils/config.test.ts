import { setImmediate as nextTurn } from 'node:timers/promises'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'

function deferred() {
  let resolve!: () => void
  const promise = new Promise<void>(done => {
    resolve = done
  })
  return { promise, resolve }
}

let disk: Record<string, unknown> | null
const loadConfig = vi.fn()
const saveConfig = vi.fn()
const resetConfig = vi.fn()

beforeEach(() => {
  vi.resetModules()
  vi.resetAllMocks()
  disk = { themeMode: 'light', themeColor: 'blue', customBackgroundPath: '/old.png' }
  loadConfig.mockImplementation(async () => (disk ? { ...disk } : null))
  saveConfig.mockImplementation(async (config, defaults) => {
    disk = { ...defaults, ...disk, ...config }
  })
  resetConfig.mockImplementation(async () => {
    disk = null
  })
  vi.stubGlobal('window', {
    electronAPI: {
      loadConfig,
      saveConfig,
      resetConfig,
      getLogger: () => ({ info: vi.fn(), error: vi.fn() }),
    },
  })
  vi.stubGlobal('localStorage', {
    getItem: () => null,
    removeItem: vi.fn(),
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

function delayFirstRead() {
  const started = deferred()
  const release = deferred()
  loadConfig.mockImplementationOnce(async () => {
    const snapshot = disk ? { ...disk } : null
    started.resolve()
    await release.promise
    return snapshot
  })
  return { started, release }
}

describe('共享前端配置读写', () => {
  it('前端读取后主进程更新窗口设置，保存偏好不会回写旧窗口设置', async () => {
    disk = { themeMode: 'light', UI: { location: '100,100', size: '1600,1000' } }
    const config = await import('./config')
    const firstRead = delayFirstRead()
    const preference = config.saveConfig({ language: 'en-US' })
    await firstRead.started.promise
    disk.UI = { location: '200,300', size: '1200,900' }
    firstRead.release.resolve()
    await preference
    expect(disk).toMatchObject({
      language: 'en-US',
      UI: { location: '200,300', size: '1200,900' },
    })
    const sameField = delayFirstRead()
    const first = config.saveConfig({ language: 'en-US' })
    await sameField.started.promise
    const second = config.saveConfig({ language: 'ja-JP' })
    const lock = config.saveConfig({ customSurfaceOpacity: 0.5 })
    await nextTurn()
    sameField.release.resolve()
    await Promise.all([first, second, lock])
    expect(disk).toMatchObject({
      language: 'ja-JP',
      customSurfaceOpacity: 0.5,
      UI: { location: '200,300', size: '1200,900' },
    })
    disk = { themeMode: 'light', themeColor: 'blue', customBackgroundPath: '/old.png' }
    saveConfig.mockRejectedValueOnce(new Error('disk unavailable'))
    const failed = config.saveConfig({ language: 'en-US' })
    const next = config.saveConfig({ themeColor: 'green' })
    await expect(failed).rejects.toThrow('disk unavailable')
    await next
    expect(disk).toMatchObject({ themeColor: 'green', customBackgroundPath: '/old.png' })
    expect(disk?.language).toBeUndefined()
  })

  it('重置等待之前的写入完成，不会被在途写入复原', async () => {
    const config = await import('./config')
    const { started, release } = delayFirstRead()
    const patch = config.saveConfig({ language: 'en-US' })
    await started.promise
    const reset = config.resetConfig()
    await nextTurn()
    release.resolve()
    await Promise.all([patch, reset])

    expect(disk).toBeNull()
  })
})
