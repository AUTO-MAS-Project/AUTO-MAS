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
let legacy: Map<string, string>
const loadConfig = vi.fn()
const saveConfig = vi.fn()
const resetConfig = vi.fn()
const getItem = vi.fn()

beforeEach(() => {
  vi.resetModules()
  vi.resetAllMocks()
  disk = { themeMode: 'light', themeColor: 'blue', mysteryUnlockedDate: '2026-10-02' }
  legacy = new Map()
  loadConfig.mockImplementation(async () => (disk ? { ...disk } : null))
  saveConfig.mockImplementation(async (config, defaults) => {
    disk = { ...defaults, ...disk, ...config }
  })
  resetConfig.mockImplementation(async () => {
    disk = null
  })
  getItem.mockImplementation((key: string) => legacy.get(key) ?? null)
  vi.stubGlobal('window', {
    electronAPI: {
      loadConfig,
      saveConfig,
      resetConfig,
      getLogger: () => ({ info: vi.fn(), error: vi.fn() }),
    },
  })
  vi.stubGlobal('localStorage', {
    getItem,
    removeItem: (key: string) => legacy.delete(key),
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
    const { started, release } = delayFirstRead()
    const preference = config.saveConfig({ language: 'en-US' })
    await started.promise
    disk.UI = { location: '200,300', size: '1200,900' }
    release.resolve()
    await preference

    expect(disk).toMatchObject({
      language: 'en-US',
      UI: { location: '200,300', size: '1200,900' },
    })
  })

  it('偏好保存先开始、锁定随后开始时，两项修改都保留', async () => {
    const config = await import('./config')
    const { started, release } = delayFirstRead()
    const preference = config.saveConfig({ language: 'en-US' })
    await started.promise
    const lock = config.saveConfig({ mysteryUnlockedDate: '' })
    await nextTurn()
    release.resolve()
    await Promise.all([preference, lock])

    expect(disk).toMatchObject({ language: 'en-US', mysteryUnlockedDate: '' })
  })

  it('同一字段保留最后一次请求的值', async () => {
    const config = await import('./config')
    const { started, release } = delayFirstRead()
    const first = config.saveConfig({ language: 'en-US' })
    await started.promise
    const second = config.saveConfig({ language: 'ja-JP' })
    await nextTurn()
    release.resolve()
    await Promise.all([first, second])

    expect(disk?.language).toBe('ja-JP')
  })

  it('一次写入失败会通知调用方，后续写入仍能执行', async () => {
    const config = await import('./config')
    saveConfig.mockRejectedValueOnce(new Error('disk unavailable'))
    const failed = config.saveConfig({ language: 'en-US' })
    const next = config.saveConfig({ themeColor: 'green' })
    await expect(failed).rejects.toThrow('disk unavailable')
    await next

    expect(disk).toMatchObject({ themeColor: 'green', mysteryUnlockedDate: '2026-10-02' })
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
