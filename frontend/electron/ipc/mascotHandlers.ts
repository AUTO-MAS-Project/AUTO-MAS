import { app, BrowserWindow, ipcMain } from 'electron'
import * as fs from 'fs'
import * as path from 'path'
import type { MascotSummary } from '../../src/types/mascotPack'
import { getAppRoot } from '../services/environmentService'
import { getLogger } from '../services/logger'
import { importMascotPackage, listMascots, removeMascot } from '../services/mascotPackageService'
import { patchConfigFile } from '../utils/configFile'
import { removeAppearanceSource } from '../services/onlineAppearanceService'

const logger = getLogger('桌宠包')
let registered = false

function forgetSource(id: string): void {
  try {
    removeAppearanceSource(app.getPath('userData'), id, logger, 'mascot')
  } catch (error) {
    logger.warn('清理桌宠来源记录失败:', error)
  }
}

export function broadcastMascotChange(): void {
  for (const window of BrowserWindow.getAllWindows()) {
    if (!window.isDestroyed()) window.webContents.send('mascot-changed')
  }
}

const summary = (mascot: MascotSummary): MascotSummary => ({
  id: mascot.id,
  name: mascot.name,
  ...(mascot.description ? { description: mascot.description } : {}),
  ...(mascot.previewUrl ? { previewUrl: mascot.previewUrl } : {}),
})

export function registerMascotHandlers(onChanged: () => void): void {
  if (registered) return
  registered = true
  const notify = (): void => {
    onChanged()
    broadcastMascotChange()
  }
  ipcMain.handle('mascot:list', () => listMascots(app.getPath('userData')))
  ipcMain.handle('mascot:import', (_event, zipPath: unknown, replace: unknown = false) => {
    if (typeof zipPath !== 'string' || !zipPath.toLowerCase().endsWith('.zip')) {
      return { success: false, code: 'INVALID_PACKAGE', error: '请选择 ZIP 桌宠包' }
    }
    const { mascot, existing, ...result } = importMascotPackage(
      app.getPath('userData'),
      path.resolve(zipPath),
      replace === true
    )
    if (result.success) {
      logger.info(`桌宠已导入: ${mascot?.id}`)
      if (mascot) forgetSource(mascot.id)
      notify()
    } else {
      logger.warn(`桌宠导入失败: ${result.error}`)
    }
    return {
      ...result,
      ...(mascot ? { mascot: summary(mascot) } : {}),
      ...(existing ? { existing: summary(existing) } : {}),
    }
  })
  ipcMain.handle('mascot:remove', (_event, id: unknown) => {
    if (typeof id !== 'string') return { success: false, error: '桌宠 ID 无效' }
    const result = removeMascot(app.getPath('userData'), id)
    if (result.success) {
      logger.info(`桌宠已移除: ${id}`)
      forgetSource(id)
      try {
        const configPath = path.join(getAppRoot(), 'config', 'frontend_config.json')
        const config = fs.existsSync(configPath)
          ? JSON.parse(fs.readFileSync(configPath, 'utf8'))
          : {}
        if (config.desktopMascotId === id) patchConfigFile(configPath, { desktopMascotId: null })
      } catch (error) {
        logger.warn('清理已移除桌宠的选择失败:', error)
      }
      notify()
    }
    return result
  })
}
