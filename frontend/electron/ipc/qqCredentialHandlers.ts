import { ipcMain, type BrowserWindow } from 'electron'
import { isApplicationWindowSender } from './analyticsHandlers'
import { qqCredentials, type QqAction } from '../services/qqCredentialService'

/** 仅允许应用主窗口的主 frame 管理 QQ 凭据。 */
export function registerQqCredentialHandlers(
  getMainWindow: () => BrowserWindow | null,
  getBackendUrl: () => string
): void {
  const actions: QqAction[] = [
    'status',
    'groups',
    'target',
    'start',
    'check',
    'unbind',
    'get',
    'set',
  ]
  for (const action of actions) {
    ipcMain.handle(`qq-credentials:${action}`, (event, value: unknown) => {
      if (!isApplicationWindowSender(event, getMainWindow(), { allowDevelopment: true })) {
        throw new Error('不允许此页面管理 QQ 机器人')
      }
      return qqCredentials(getBackendUrl(), action, value)
    })
  }
}
