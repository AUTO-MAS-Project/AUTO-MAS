import { beginMainFeature } from '../services/featureAnalytics'
import { ipcMain } from 'electron'
import { discoverOkwwPath, discoverWutheringWavesPath } from '../services/okwwPathDiscoveryService'
import { getLogger } from '../services/logger'

const logger = getLogger('OK-WW路径发现')
let isRegistered = false

export function registerOkwwPathDiscoveryHandlers(): void {
  if (isRegistered) return
  isRegistered = true

  ipcMain.handle('okww-path-discovery:discover-okww', async () => {
    const operation = beginMainFeature('adapter_setup_finished')
    const result = await discoverOkwwPath()
    operation.finish({
      script_type: 'Okww',
      operation_kind: 'discover_path',
      engine_kind: 'unknown',
      outcome: result.success ? (result.candidates?.length ? 'success' : 'not_found') : 'unknown',
    })
    if (result.success) {
      logger.info(`已发现 ${result.candidates?.length || 0} 个 OK-WW 安装目录`)
    } else {
      logger.warn(`未发现 OK-WW 安装目录: ${result.error}`)
    }
    return result
  })

  ipcMain.handle('okww-path-discovery:discover-wuthering-waves', async () => {
    const operation = beginMainFeature('adapter_setup_finished')
    const result = await discoverWutheringWavesPath()
    operation.finish({
      script_type: 'Okww',
      operation_kind: 'launcher',
      engine_kind: 'unknown',
      outcome: result.success ? (result.candidates?.length ? 'success' : 'not_found') : 'unknown',
    })
    if (result.success) {
      logger.info(`已发现 ${result.candidates?.length || 0} 个鸣潮启动器路径`)
    } else {
      logger.warn(`未发现鸣潮启动器路径: ${result.error}`)
    }
    return result
  })
}
