import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { BrowserWindow } from 'electron'
import { registerUpgradeBackupHandlers } from './upgradeBackupHandlers'

const native = vi.hoisted(() => ({
  handlers: new Map<string, (event: unknown, value?: unknown) => Promise<unknown> | void>(),
  choose: vi.fn(),
  supported: vi.fn(),
}))

vi.mock('electron', () => ({
  dialog: { showOpenDialog: native.choose },
  ipcMain: {
    handle: (key: string, handler: (event: unknown, value?: unknown) => Promise<unknown> | void) =>
      native.handlers.set(key, handler),
  },
}))
vi.mock('./analyticsHandlers', () => ({ isApplicationWindowSender: () => true }))

function invoke(action: string, value?: unknown) {
  return native.handlers.get(`upgrade-backup:${action}`)?.({}, value)
}

describe('升级备份目录确认', () => {
  const initial = {
    directory: 'D:/current',
    resolvedDirectory: 'D:/current',
    defaultDirectory: 'C:/MAS/backup',
  }
  const fetch = vi.fn(async (_url: URL, options?: RequestInit) => {
    const parsed = options?.body ? JSON.parse(String(options.body)) : null
    return Response.json(
      parsed
        ? {
            ...initial,
            directory: parsed.directory,
            resolvedDirectory: parsed.directory ?? initial.defaultDirectory,
          }
        : initial
    )
  })

  beforeEach(() => {
    native.handlers.clear()
    native.choose.mockReset()
    native.supported.mockReset().mockReturnValue(true)
    fetch.mockClear()
    vi.stubGlobal('fetch', fetch)
    registerUpgradeBackupHandlers(
      () => ({ isDestroyed: () => false }) as BrowserWindow,
      () => 'http://127.0.0.1:36163',
      native.supported
    )
  })

  afterEach(() => vi.unstubAllGlobals())

  it('在不支持自动备份的启动模式下不访问后端', async () => {
    native.supported.mockReturnValue(false)
    expect(await invoke('directory')).toBeNull()
    await expect(invoke('choose-directory', false)).rejects.toThrow()
    expect(fetch).not.toHaveBeenCalled()
    expect(native.choose).not.toHaveBeenCalled()
  })

  it('选择后取消只读取设置，任意路径和已取消的选择均不能触发迁移', async () => {
    native.choose.mockResolvedValue({ canceled: false, filePaths: ['D:/selected'] })
    const selection = (await invoke('choose-directory', false)) as { id: string }
    await expect(invoke('confirm-directory', 'D:/other')).rejects.toThrow()
    await invoke('cancel-directory', selection.id)
    await expect(invoke('confirm-directory', selection.id)).rejects.toThrow()
    expect(fetch.mock.calls.filter(([, options]) => options?.method === 'POST')).toHaveLength(0)
  })

  it('确认仅迁移本次通过系统选择器选中的目录，并消费该选择', async () => {
    native.choose.mockResolvedValue({ canceled: false, filePaths: ['D:/selected'] })
    const selection = (await invoke('choose-directory', false)) as { id: string }
    expect(fetch.mock.calls.filter(([, options]) => options?.method === 'POST')).toHaveLength(0)

    const result = await invoke('confirm-directory', selection.id)
    expect(result).toMatchObject({ directory: 'D:/selected' })
    const posted = fetch.mock.calls.find(([, options]) => options?.method === 'POST')
    expect(JSON.parse(String(posted?.[1]?.body))).toEqual({
      directory: 'D:/selected',
      expected: initial.resolvedDirectory,
    })
    await expect(invoke('confirm-directory', selection.id)).rejects.toThrow()
  })

  it('恢复默认直接预览默认路径，取消不迁移，确认发送默认选项', async () => {
    native.choose.mockResolvedValue({ canceled: true, filePaths: [] })
    const selection = (await invoke('choose-directory', true)) as { id: string }
    expect(selection).toMatchObject({
      current: initial.resolvedDirectory,
      target: initial.defaultDirectory,
    })
    expect(native.choose).not.toHaveBeenCalled()
    await invoke('cancel-directory', selection.id)
    await expect(invoke('confirm-directory', selection.id)).rejects.toThrow()
    expect(fetch.mock.calls.filter(([, options]) => options?.method === 'POST')).toHaveLength(0)

    const renewed = (await invoke('choose-directory', true)) as { id: string }
    expect(await invoke('confirm-directory', renewed.id)).toMatchObject({
      directory: null,
      resolvedDirectory: initial.defaultDirectory,
    })
    const posted = fetch.mock.calls.find(([, options]) => options?.method === 'POST')
    expect(JSON.parse(String(posted?.[1]?.body))).toEqual({
      directory: null,
      expected: initial.resolvedDirectory,
    })
  })
})
