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
import { getDevelopmentServerUrl } from '../services/instanceConfig'
import { validateAnalyticsEvent } from '../services/analyticsPolicy'
import { claimStartupAttempt, finishStartupAttempt } from '../services/startupHardware/monitor'

let mainWindow: () => BrowserWindow | null = () => null

/** 同 preload 也被日志窗等复用，因此同时校验窗口、主 frame 和本地应用文件。 */
export function isAnalyticsSender(event: IpcMainEvent | IpcMainInvokeEvent): boolean {
  return isApplicationWindowSender(event, mainWindow())
}

/** 专用辅助窗口仍须单独限定窗口身份与业务消息，不能走通用事件桥。 */
export function isApplicationWindowSender(
  event: IpcMainEvent | IpcMainInvokeEvent,
  window: BrowserWindow | null,
  options: { allowDevelopment?: boolean } = {}
): boolean {
  if (!window || window.isDestroyed() || event.sender !== window.webContents) return false
  if (event.senderFrame !== window.webContents.mainFrame) return false
  try {
    const url = new URL(event.senderFrame.url)
    const devServer = getDevelopmentServerUrl()
    if (options.allowDevelopment && devServer) {
      const development = new URL(devServer)
      return url.origin === development.origin && url.pathname === development.pathname
    }
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
  ipcMain.handle('analytics:initialization-begin', event => {
    if (!isApplicationWindowSender(event, mainWindow(), { allowDevelopment: true }))
      return { generation: null, attempt: null }
    refreshAnalyticsPreference()
    return { generation: analyticsService.getContext(), attempt: claimStartupAttempt() }
  })
  ipcMain.on(
    'analytics:initialization-finish',
    (event, context: unknown, attempt: unknown, payload: unknown) => {
      if (!isApplicationWindowSender(event, mainWindow(), { allowDevelopment: true })) return
      const valid = validateAnalyticsEvent(payload, true)
      if (valid?.name !== 'initialization_finished_v2') return
      refreshAnalyticsPreference()
      const summary = finishStartupAttempt(attempt, valid.props.outcome, valid.props.failed_stage)
      if (summary && isAnalyticsSender(event))
        analyticsService.recordRendererEvent(context, valid, () => summary)
    }
  )
  ipcMain.on('analytics:event', (event, context: unknown, payload: unknown) => {
    if (!isAnalyticsSender(event)) return
    refreshAnalyticsPreference()
    analyticsService.recordRendererEvent(context, payload)
  })
}
