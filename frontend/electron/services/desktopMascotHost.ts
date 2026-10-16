import type { BrowserWindow } from 'electron'
import type {
  DesktopMascotColors,
  DesktopMascotIdleMessage,
  DesktopMascotMenuLabels,
} from '../../src/types/desktopMascot'
import type { MascotAssets } from '../../src/types/mascotPack'
import { broadcastMascotChange, registerDesktopMascotHandlers } from '../ipc/mascotHandlers'
import { getLogger } from './logger'
import { DesktopMascotService, type DesktopMascotPreferences } from './desktopMascotService'

interface DesktopMascotHostOptions {
  readPreferences(): DesktopMascotPreferences
  savePreferences(patch: Partial<DesktopMascotPreferences>): void
  getMainWindow(): BrowserWindow | null
  resolveAssets(
    selection: Pick<DesktopMascotPreferences, 'appearanceId' | 'desktopMascotId'>
  ): MascotAssets | null
}

/** 只装配桌宠服务与宿主接线；窗口行为和资源校验仍由已有服务负责。 */
export function createDesktopMascotHost(options: DesktopMascotHostOptions) {
  const logger = getLogger('桌面桌宠')
  const reportError = (error: unknown): void => {
    logger.error('桌面桌宠更新失败:', error)
    const win = options.getMainWindow()
    if (win && !win.isDestroyed()) win.webContents.send('desktop-mascot:error')
  }
  const serviceOptions = {
    readPreferences: options.readPreferences,
    resolveAssets: options.resolveAssets,
    savePosition: (position: Electron.Point) =>
      options.savePreferences({ desktopMascotPosition: position }),
    saveAnimationPaused: (paused: boolean) =>
      options.savePreferences({ desktopMascotAnimationPaused: paused }),
    saveIdleMessagePaused: (paused: boolean) =>
      options.savePreferences({ desktopMascotIdleMessagePaused: paused }),
    getMainWindow: options.getMainWindow,
    onError: reportError,
  }
  let service: DesktopMascotService | undefined
  let disposed = false
  let detachMainWindow: (() => void) | undefined
  // 通信输入属于应用宿主，运行实例释放后仍可接收；重建时只恢复当前状态，不重播提醒。
  let ready = false
  let labels: DesktopMascotMenuLabels | undefined
  let colors: DesktopMascotColors | undefined
  let idleMessage: DesktopMascotIdleMessage | undefined
  let working = false
  let animate = true
  const disposeHandlers = registerDesktopMascotHandlers(
    {
      setReady(nextReady, nextLabels, nextColors): void {
        if (disposed) return
        ready = nextReady
        if (nextLabels) labels = nextLabels
        if (nextColors) colors = nextColors
        service?.setReady(ready, labels, colors)
      },
      setIdleMessage(message): void {
        if (disposed) return
        idleMessage = message
        service?.setIdleMessage(message)
      },
      setActivity(nextWorking, nextAnimate): void {
        if (disposed) return
        working = nextWorking
        animate = nextAnimate
        service?.setActivity(working, animate)
      },
      getData: sender => service?.getData(sender) ?? null,
      handlePointer: (sender, action) => service?.handlePointer(sender, action),
      setDecodedImage: (sender, imageUrl, pngDataUrl) =>
        service?.setDecodedImage(sender, imageUrl, pngDataUrl),
      showNotice: (text, reaction) => service?.showNotice(text, reaction),
    },
    options.getMainWindow
  )

  const unmount = (): void => {
    const previous = service
    service = undefined
    previous?.dispose()
  }

  const sync = (): void => {
    if (disposed) return
    try {
      service?.sync()
    } catch (error) {
      reportError(error)
    }
  }

  return {
    mount(): void {
      if (disposed || service) return
      service = new DesktopMascotService(serviceOptions)
      if (idleMessage) service.setIdleMessage(idleMessage)
      service.setActivity(working, animate)
      service.setReady(ready, labels, colors)
    },
    unmount,
    sync,
    attachMainWindow(win: BrowserWindow): void {
      if (disposed) return
      detachMainWindow?.()
      ready = false
      service?.setReady(false)
      const onClosed = (): void => {
        if (options.getMainWindow() !== win) return
        ready = false
        service?.setReady(false)
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
      unmount()
    },
  }
}
