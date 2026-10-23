import {
  app,
  ipcMain,
  type BrowserWindow,
  type IpcMainEvent,
  type IpcMainInvokeEvent,
} from 'electron'
import * as path from 'path'
import { fileURLToPath } from 'url'
import { analyticsService, refreshAnalyticsPreference } from '../services/analyticsService'

let mainWindow: () => BrowserWindow | null = () => null

/** 同 preload 也被日志窗等复用，因此同时校验窗口、主 frame 和本地应用文件。 */
export function isAnalyticsSender(event: IpcMainEvent | IpcMainInvokeEvent): boolean {
  const window = mainWindow()
  if (!window || window.isDestroyed() || event.sender !== window.webContents) return false
  if (event.senderFrame !== window.webContents.mainFrame) return false
  try {
    const url = new URL(event.senderFrame.url)
    return (
      url.protocol === 'file:' &&
      fileURLToPath(url) === path.join(app.getAppPath(), 'dist', 'index.html')
    )
  } catch {
    return false
  }
}

export function registerAnalyticsHandlers(getMainWindow: () => BrowserWindow | null): void {
  mainWindow = getMainWindow
  ipcMain.handle('analytics:context', event => {
    if (!isAnalyticsSender(event)) return null
    refreshAnalyticsPreference()
    return analyticsService.getContext()
  })
  ipcMain.on('analytics:event', (event, context: unknown, payload: unknown) => {
    if (!isAnalyticsSender(event)) return
    refreshAnalyticsPreference()
    analyticsService.recordRendererEvent(context, payload)
  })
}
