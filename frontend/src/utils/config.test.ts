import { setImmediate as nextTurn } from 'node:timers/promises'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

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
  it('迁移 useTheme 的两个独立旧键，覆盖旧配置里的未使用默认值', async () => {
    disk = { language: 'en-US', themeMode: 'system', themeColor: 'blue' }
    legacy.set('theme-mode', 'dark')
    legacy.set('theme-color', 'green')
    const config = await import('./config')

    await expect(config.getConfig()).resolves.toMatchObject({
      themeMode: 'dark',
      themeColor: 'green',
    })
    expect(disk).toMatchObject({ language: 'en-US', themeMode: 'dark', themeColor: 'green' })
    expect(legacy.size).toBe(0)
  })

  it('迁移保存失败时保留旧键，下一次读取仍能重试', async () => {
    disk = { language: 'zh-CN' }
    legacy.set('theme-mode', 'dark')
    legacy.set('theme-color', 'green')
    saveConfig.mockRejectedValueOnce(new Error('disk unavailable'))
    const config = await import('./config')

    expect((await config.getConfig()).themeMode).toBe('dark')
    expect(legacy.size).toBe(2)
    await config.getConfig()
    expect(disk).toMatchObject({ themeMode: 'dark', themeColor: 'green' })
    expect(legacy.size).toBe(0)
  })

  it('迁移失败后用户显式保存的主题，不会被下次迁移用旧键覆盖', async () => {
    disk = { language: 'zh-CN' }
    legacy.set('theme-mode', 'dark')
    legacy.set('theme-color', 'green')
    saveConfig.mockRejectedValueOnce(new Error('disk unavailable'))
    const config = await import('./config')

    await config.getConfig()
    await config.saveConfig({ themeMode: 'light' })
    await config.getConfig()
    expect(disk).toMatchObject({ themeMode: 'light', themeColor: 'green' })
    expect(legacy.size).toBe(0)
  })

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

  it('迁移检查期间主进程更新配置，迁移不会覆盖最新文件', async () => {
    legacy.set('app-config', JSON.stringify({ language: 'en-US' }))
    const config = await import('./config')
    const { started, release } = delayFirstRead()
    const loading = config.getConfig()
    await started.promise
    disk = { ...disk, UI: { location: '200,300' }, themeColor: 'green' }
    release.resolve()
    await loading

    expect(disk).toMatchObject({ UI: { location: '200,300' }, themeColor: 'green' })
    expect(legacy.size).toBe(0)
  })

  it('文件配置缺少主题字段时，会迁移旧主题偏好并落盘', async () => {
    disk = { language: 'en-US' }
    legacy.set('theme-settings', JSON.stringify({ themeMode: 'dark', themeColor: 'green' }))
    const config = await import('./config')

    await expect(config.getConfig()).resolves.toMatchObject({
      themeMode: 'dark',
      themeColor: 'green',
    })
    expect(disk).toMatchObject({
      language: 'en-US',
      themeMode: 'dark',
      themeColor: 'green',
    })
    expect(legacy.size).toBe(0)
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

  it('解锁写入先开始、偏好保存随后开始时，两项修改都保留', async () => {
    disk = { themeMode: 'light', themeColor: 'blue' }
    const config = await import('./config')
    const { started, release } = delayFirstRead()
    const unlock = config.saveConfig({ mysteryUnlockedDate: '2026-10-02' })
    await started.promise
    const preference = config.saveConfig({ language: 'ja-JP' })
    await nextTurn()
    release.resolve()
    await Promise.all([unlock, preference])

    expect(disk).toMatchObject({ language: 'ja-JP', mysteryUnlockedDate: '2026-10-02' })
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
    const failed = expect(config.saveConfig({ language: 'en-US' })).rejects.toThrow(
      'disk unavailable'
    )
    const next = config.saveConfig({ themeColor: 'green' })
    await failed
    await next

    expect(disk).toMatchObject({ themeColor: 'green', mysteryUnlockedDate: '2026-10-02' })
    expect(disk?.language).toBeUndefined()
  })

  it('迁移检查先开始时，后续配置保存不会被旧快照覆盖', async () => {
    legacy.set('app-config', JSON.stringify({ language: 'en-US' }))
    const config = await import('./config')
    const { started, release } = delayFirstRead()
    const loading = config.getConfig()
    await started.promise
    const lock = config.saveConfig({ mysteryUnlockedDate: '' })
    await nextTurn()
    release.resolve()
    await Promise.all([loading, lock])

    expect(disk?.mysteryUnlockedDate).toBe('')
    expect(legacy.size).toBe(0)
  })

  it('保存先开始时，后续迁移读取最新配置', async () => {
    disk = null
    legacy.set('app-config', JSON.stringify({ language: 'en-US' }))
    const config = await import('./config')
    const { started, release } = delayFirstRead()
    const patch = config.saveConfig({ themeColor: 'green' })
    await started.promise
    const loading = config.getConfig()
    await nextTurn()
    release.resolve()
    await patch
    const loaded = await loading

    expect(disk).toMatchObject({ language: 'en-US', themeColor: 'green' })
    expect(loaded.themeColor).toBe('green')
    expect(legacy.size).toBe(0)
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

  it('IPC 读取失败仍返回默认配置', async () => {
    const config = await import('./config')
    loadConfig.mockRejectedValueOnce(new Error('IPC unavailable'))

    expect(await config.getConfig()).toMatchObject({ themeMode: 'system', themeColor: 'blue' })
  })

  it('迁移检查异常会拒绝，修复存储后可重新加载', async () => {
    const config = await import('./config')
    getItem.mockImplementationOnce(() => {
      throw new Error('storage unavailable')
    })

    await expect(config.getConfig()).rejects.toThrow('storage unavailable')
    expect(await config.getConfig()).toMatchObject({ themeMode: 'light', themeColor: 'blue' })
  })
})
