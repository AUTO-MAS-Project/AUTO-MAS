import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { BrowserWindow } from 'electron'
import { registerUpgradeBackupHandlers } from './upgradeBackupHandlers'

const native = vi.hoisted(() => ({
  handlers: new Map<string, (event: unknown, value?: unknown) => Promise<unknown> | void>(),
  choose: vi.fn(),
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
    directory: null,
    resolvedDirectory: 'C:/MAS/backup',
    defaultDirectory: 'C:/MAS/backup',
  }
  const fetch = vi.fn(async (_url: URL, options?: RequestInit) => {
    const parsed = options?.body ? JSON.parse(String(options.body)) : null
    return Response.json(
      parsed
        ? { ...initial, directory: parsed.directory, resolvedDirectory: parsed.directory }
        : initial
    )
  })

  beforeEach(() => {
    native.handlers.clear()
    native.choose.mockReset()
    fetch.mockClear()
    vi.stubGlobal('fetch', fetch)
    registerUpgradeBackupHandlers(
      () => ({ isDestroyed: () => false }) as BrowserWindow,
      () => 'http://127.0.0.1:36163',
      () => true
    )
  })

  afterEach(() => vi.unstubAllGlobals())

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
      expected: 'C:/MAS/backup',
    })
    await expect(invoke('confirm-directory', selection.id)).rejects.toThrow()
  })

  it('恢复默认也通过系统选择器，关闭选择器时不迁移', async () => {
    native.choose.mockResolvedValue({ canceled: true, filePaths: [] })
    expect(await invoke('choose-directory', true)).toBeNull()
    expect(native.choose).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ defaultPath: 'C:/MAS/backup', properties: ['openDirectory'] })
    )
    expect(fetch.mock.calls.filter(([, options]) => options?.method === 'POST')).toHaveLength(0)
  })
})
