import { randomUUID } from 'node:crypto'
import { dialog, ipcMain, type BrowserWindow, type IpcMainInvokeEvent } from 'electron'
import { isApplicationWindowSender } from './analyticsHandlers'
import type { UpgradeBackupDirectory, UpgradeBackupSelection } from '../../src/types/upgradeBackup'

export const upgradeBackupToken = randomUUID()

export function registerUpgradeBackupHandlers(
  window: () => BrowserWindow | null,
  endpoint: () => string,
  ownsBackend: () => boolean
) {
  let pending: UpgradeBackupSelection | null = null
  let moving = false

  function requireWindow(event: IpcMainInvokeEvent): BrowserWindow {
    const target = window()
    if (!ownsBackend() || !target || !isApplicationWindowSender(event, target))
      throw new Error('不允许此窗口管理更新备份')
    return target
  }

  async function request(body?: { directory: string | null; expected: string }) {
    const url = new URL('/api/setting/backup/directory', endpoint())
    if (!['127.0.0.1', '[::1]', 'localhost'].includes(url.hostname))
      throw new Error('只能管理本机更新备份')
    const response = await fetch(url, {
      headers: {
        'X-Auto-Mas-Upgrade-Backup': upgradeBackupToken,
        'Content-Type': 'application/json',
      },
      ...(body === undefined ? {} : { method: 'POST', body: JSON.stringify(body) }),
    })
    if (!response.ok) throw new Error(`更新备份目录操作失败 (${response.status})`)
    return (await response.json()) as UpgradeBackupDirectory
  }

  ipcMain.handle('upgrade-backup:directory', event => {
    requireWindow(event)
    return request()
  })

  ipcMain.handle('upgrade-backup:choose-directory', async (event, reset: boolean) => {
    const target = requireWindow(event)
    if (moving) throw new Error('正在迁移更新备份')
    pending = null
    const current = await request()
    const selected = await dialog.showOpenDialog(target, {
      defaultPath: reset === true ? current.defaultDirectory : current.resolvedDirectory,
      properties: ['openDirectory'],
    })
    if (selected.canceled || !selected.filePaths[0]) return null
    pending = {
      id: randomUUID(),
      current: current.resolvedDirectory,
      target: selected.filePaths[0],
    }
    return pending
  })

  ipcMain.handle('upgrade-backup:cancel-directory', (event, id: unknown) => {
    requireWindow(event)
    if (pending?.id === id) pending = null
  })

  ipcMain.handle('upgrade-backup:confirm-directory', async (event, id: unknown) => {
    requireWindow(event)
    if (!pending || pending.id !== id || moving) throw new Error('备份目录选择已失效')
    const selection = pending
    pending = null
    moving = true
    try {
      return await request({
        directory: selection.target,
        expected: selection.current,
      })
    } finally {
      moving = false
    }
  })
}
