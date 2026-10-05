import { app, BrowserWindow, ipcMain } from 'electron'
import * as fs from 'fs'
import * as path from 'path'
import {
  getAppearance,
  importAppearancePackage,
  isAppearanceGone,
  listAppearances,
  removeAppearance,
} from '../services/appearanceService'
import { getLogger } from '../services/logger'
import { getAppRoot } from '../services/environmentService'
import { clearAppearanceConfigIfCurrent } from '../utils/configFile'

const logger = getLogger('外观包')
let isRegistered = false

function userDataPath(): string {
  return app.getPath('userData')
}

function broadcastAppearanceChange(): void {
  for (const window of BrowserWindow.getAllWindows()) {
    if (!window.isDestroyed()) window.webContents.send('appearance-changed')
  }
}

function clearInvalidAppearance(id: string) {
  const configPath = path.join(getAppRoot(), 'config', 'frontend_config.json')
  const result = clearAppearanceConfigIfCurrent(configPath, id, () =>
    isAppearanceGone(userDataPath(), id)
  )
  if (result.cleared) {
    for (const window of BrowserWindow.getAllWindows()) {
      if (!window.isDestroyed()) {
        window.webContents.send('theme-config-changed', {
          themeMode: result.config.themeMode,
          themeColor: result.config.themeColor,
          appearanceId: null,
        })
      }
    }
  }
  return {
    success: true,
    cleared: result.cleared,
    appearanceId:
      typeof result.config.appearanceId === 'string' ? result.config.appearanceId : null,
  }
}

/** 注册自定义外观包的受限 IPC；素材始终由主进程校验并转换为 data URL。 */
export function registerAppearanceHandlers(): void {
  if (isRegistered) return
  isRegistered = true

  ipcMain.handle('appearance:list', () => listAppearances(userDataPath()))

  ipcMain.handle('appearance:get', (_event, id: unknown) => {
    if (typeof id !== 'string') return null
    return getAppearance(userDataPath(), id)
  })

  ipcMain.handle('appearance:clear-invalid', (_event, expectedId: unknown) => {
    if (typeof expectedId !== 'string' || !/^[a-z0-9][a-z0-9_-]{0,63}$/.test(expectedId)) {
      return { success: false, error: '外观 ID 无效' }
    }
    try {
      return clearInvalidAppearance(expectedId)
    } catch (error) {
      logger.warn(`清理失效外观配置失败: ${error instanceof Error ? error.message : String(error)}`)
      return { success: false, error: '清理失效外观配置失败' }
    }
  })

  ipcMain.handle('appearance:import', (_event, zipPath: unknown, replace = false) => {
    if (typeof zipPath !== 'string' || !zipPath.toLowerCase().endsWith('.zip')) {
      return { success: false, code: 'INVALID_PACKAGE', error: '请选择 ZIP 外观包' }
    }
    const resolved = path.resolve(zipPath)
    try {
      const stat = fs.statSync(resolved)
      if (!stat.isFile())
        return { success: false, code: 'INVALID_PACKAGE', error: '选择的路径不是文件' }
    } catch {
      return { success: false, code: 'INVALID_PACKAGE', error: '外观 ZIP 不存在' }
    }
    const result = importAppearancePackage(userDataPath(), resolved, replace === true)
    if (result.success) {
      logger.info(`外观包已导入: ${result.appearance?.id ?? 'unknown'}`)
      broadcastAppearanceChange()
    } else {
      logger.warn(`外观包导入失败: ${result.error ?? result.code ?? 'unknown'}`)
    }
    return result
  })

  ipcMain.handle('appearance:remove', (_event, id: unknown) => {
    if (typeof id !== 'string') return { success: false, error: '外观 ID 无效' }
    const result = removeAppearance(userDataPath(), id)
    if (result.success) {
      logger.info(`外观包已移除: ${id}`)
      try {
        clearInvalidAppearance(id)
      } catch (error) {
        logger.warn(
          `清理已移除外观配置失败: ${error instanceof Error ? error.message : String(error)}`
        )
      }
      broadcastAppearanceChange()
    } else {
      logger.warn(`外观包移除失败: ${id}，${result.error ?? '未知错误'}`)
    }
    return result
  })
}
