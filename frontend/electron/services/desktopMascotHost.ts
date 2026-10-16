import type { BrowserWindow } from 'electron'
import { broadcastMascotChange, registerDesktopMascotHandlers } from '../ipc/mascotHandlers'
import { getLogger } from './logger'
import { DesktopMascotService, type DesktopMascotPreferences } from './desktopMascotService'

interface DesktopMascotHostOptions {
  readPreferences(): DesktopMascotPreferences
  savePreferences(patch: Partial<DesktopMascotPreferences>): void
  getMainWindow(): BrowserWindow | null
}

/** 只装配桌宠服务与宿主接线；窗口行为和资源校验仍由已有服务负责。 */
export function createDesktopMascotHost(options: DesktopMascotHostOptions) {
  const logger = getLogger('桌面桌宠')
  const reportError = (error: unknown): void => {
    logger.error('桌面桌宠更新失败:', error)
    const win = options.getMainWindow()
    if (win && !win.isDestroyed()) win.webContents.send('desktop-mascot:error')
  }
  const service = new DesktopMascotService({
    readPreferences: options.readPreferences,
    savePosition: position => options.savePreferences({ desktopMascotPosition: position }),
    saveAnimationPaused: paused =>
      options.savePreferences({ desktopMascotAnimationPaused: paused }),
    saveIdleMessagePaused: paused =>
      options.savePreferences({ desktopMascotIdleMessagePaused: paused }),
    getMainWindow: options.getMainWindow,
    onError: reportError,
  })
  let disposed = false
  let detachMainWindow: (() => void) | undefined
  const disposeHandlers = registerDesktopMascotHandlers(service, options.getMainWindow)

  const sync = (): void => {
    if (disposed) return
    try {
      service.sync()
    } catch (error) {
      reportError(error)
    }
  }

  return {
    sync,
    attachMainWindow(win: BrowserWindow): void {
      if (disposed) return
      detachMainWindow?.()
      service.setReady(false)
      const onClosed = (): void => {
        if (options.getMainWindow() === win) service.setReady(false)
      }
      win.once('closed', onClosed)
      detachMainWindow = () => win.removeListener('closed', onClosed)
    },
    configChanged(patch: unknown): void {
      if (disposed || !patch || typeof patch !== 'object') return
      if (
        [
          'appearanceId',
          'desktopMascotId',
          'desktopMascotEnabled',
          'desktopMascotAnimationPaused',
          'desktopMascotIdleMessagePaused',
        ].some(key => key in patch)
      ) {
        sync()
        if (['desktopMascotId', 'desktopMascotEnabled'].some(key => key in patch)) {
          broadcastMascotChange()
        }
      }
    },
    dispose(): void {
      if (disposed) return
      disposed = true
      disposeHandlers()
      detachMainWindow?.()
      service.setReady(false)
    },
  }
}
