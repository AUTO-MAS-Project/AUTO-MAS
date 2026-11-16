import { ipcMain, type BrowserWindow } from 'electron'
import { isApplicationWindowSender } from './analyticsHandlers'
import { installFluxdown } from '../services/fluxdownInstallService'

/** 只开放主窗口主 frame 的安装动作，辅助窗口、iframe 和远程页面均不可调用。 */
export function registerFluxdownInstallHandlers(
  getMainWindow: () => BrowserWindow | null,
  getBackendUrl: () => string
): void {
  ipcMain.handle('fluxdown:install', (event, mirror: unknown) => {
    if (!isApplicationWindowSender(event, getMainWindow(), { allowDevelopment: true })) {
      throw new Error('不允许此页面安装 FluxDown')
    }
    return installFluxdown(getBackendUrl(), mirror)
  })
}
