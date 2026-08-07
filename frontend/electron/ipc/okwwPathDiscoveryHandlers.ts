import { ipcMain } from 'electron'
import { discoverOkwwPath, discoverWutheringWavesPath } from '../services/okwwPathDiscoveryService'
import { getLogger } from '../services/logger'

const logger = getLogger('OK-WW路径发现')
let isRegistered = false

export function registerOkwwPathDiscoveryHandlers(): void {
  if (isRegistered) return
  isRegistered = true

  ipcMain.handle('okww-path-discovery:discover-okww', async () => {
    const result = await discoverOkwwPath()
    if (result.success) {
      logger.info(`已发现 OK-WW 安装目录: ${result.path}`)
    } else {
      logger.warn(`未发现 OK-WW 安装目录: ${result.error}`)
    }
    return result
  })

  ipcMain.handle('okww-path-discovery:discover-wuthering-waves', async () => {
    const result = await discoverWutheringWavesPath()
    if (result.success) {
      logger.info(`已发现鸣潮启动器路径: ${result.path}`)
    } else {
      logger.warn(`未发现鸣潮启动器路径: ${result.error}`)
    }
    return result
  })
}
