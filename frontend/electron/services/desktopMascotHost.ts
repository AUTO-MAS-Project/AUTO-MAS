import type { BrowserWindow } from 'electron'
import type {
  DesktopMascotColors,
  DesktopMascotIdleMessage,
  DesktopMascotMenuLabels,
  DesktopMascotTaskMenu,
} from '../../src/types/desktopMascot'
import type { MascotAssets } from '../../src/types/mascotPack'
import { broadcastMascotChange, registerDesktopMascotHandlers } from '../ipc/mascotHandlers'
import { getLogger } from './logger'
import type {
  DesktopMascotOptions,
  DesktopMascotPreferences,
  DesktopMascotRuntime,
} from './desktopMascotTypes'

export interface DesktopMascotHostPreferences extends DesktopMascotPreferences {
  appearanceId?: string | null
  /** 为空时跟随主题；有值时使用独立安装的桌宠。 */
  desktopMascotId?: string | null
}

interface DesktopMascotHostOptions {
  readPreferences(): DesktopMascotHostPreferences
  savePreferences(patch: Partial<DesktopMascotHostPreferences>): void
  getMainWindow(): BrowserWindow | null
  resolveAssets(
    selection: Pick<DesktopMascotHostPreferences, 'appearanceId' | 'desktopMascotId'>
  ): MascotAssets | null
  createRuntime(options: DesktopMascotOptions): DesktopMascotRuntime
}

/** 只装配桌宠服务与宿主接线；窗口行为和资源校验仍由已有服务负责。 */
export function createDesktopMascotHost(options: DesktopMascotHostOptions) {
  const logger = getLogger('桌面桌宠')
  let menuRequestId = 0
  let menuRequest: {
    id: number
    resolve(menu: DesktopMascotTaskMenu | null): void
    timer: ReturnType<typeof setTimeout>
  } | null = null
  const finishMenuRequest = (menu: DesktopMascotTaskMenu | null): void => {
    if (!menuRequest) return
    const request = menuRequest
    menuRequest = null
    clearTimeout(request.timer)
    request.resolve(menu)
  }
  const reportError = (error: unknown): void => {
    logger.error('桌面桌宠更新失败:', error)
    const win = options.getMainWindow()
    if (win && !win.isDestroyed()) win.webContents.send('desktop-mascot:error')
  }
  const serviceOptions: DesktopMascotOptions = {
    readPreferences: options.readPreferences,
    resolveAssets: () => {
      const { appearanceId, desktopMascotId } = options.readPreferences()
      return options.resolveAssets({ appearanceId, desktopMascotId })
    },
    savePosition: (position: Electron.Point) =>
      options.savePreferences({ desktopMascotPosition: position }),
    saveAnimationPaused: (paused: boolean) =>
      options.savePreferences({ desktopMascotAnimationPaused: paused }),
    saveIdleMessagePaused: (paused: boolean) =>
      options.savePreferences({ desktopMascotIdleMessagePaused: paused }),
    getInitialBounds: () => options.getMainWindow()?.getBounds(),
    loadTaskMenu: () => {
      finishMenuRequest(null)
      const win = options.getMainWindow()
      if (disposed || !ready || !win || win.isDestroyed()) return Promise.resolve(null)
      const id = ++menuRequestId
      return new Promise(resolve => {
        menuRequest = {
          id,
          resolve,
          // 后端或主界面无响应时，仍可使用原有动画和留言菜单。
          timer: setTimeout(() => finishMenuRequest(null), 3000),
        }
        win.webContents.send('desktop-mascot:task-menu-request', id)
      })
    },
    onTaskAction: action => {
      const win = options.getMainWindow()
      if (!disposed && ready && win && !win.isDestroyed())
        win.webContents.send('desktop-mascot:task-action', action)
    },
    onRefreshIdleMessage: () => {
      const win = options.getMainWindow()
      if (!disposed && ready && win && !win.isDestroyed())
        win.webContents.send('desktop-mascot:refresh-idle-message')
    },
    onError: reportError,
  }
  let service: DesktopMascotRuntime | undefined
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
        if (!ready) finishMenuRequest(null)
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
      handlePointer: (sender, action, session) => service?.handlePointer(sender, action, session),
      startDrag: (sender, offset) => service?.startDrag(sender, offset) ?? false,
      setDecodedImage: (sender, imageUrl, pngDataUrl) =>
        service?.setDecodedImage(sender, imageUrl, pngDataUrl),
      showNotice: (text, reaction) => service?.showNotice(text, reaction),
    },
    options.getMainWindow,
    (id, menu) => {
      if (menuRequest?.id === id) finishMenuRequest(menu)
    }
  )

  const unmount = (): void => {
    finishMenuRequest(null)
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
      service = options.createRuntime(serviceOptions)
      if (idleMessage) service.setIdleMessage(idleMessage)
      service.setActivity(working, animate)
      service.setReady(ready, labels, colors)
    },
    unmount,
    sync,
    attachMainWindow(win: BrowserWindow): void {
      if (disposed) return
      detachMainWindow?.()
      finishMenuRequest(null)
      ready = false
      service?.setReady(false)
      const onClosed = (): void => {
        if (options.getMainWindow() !== win) return
        ready = false
        finishMenuRequest(null)
        service?.setReady(false)
      }
      win.once('closed', onClosed)
      detachMainWindow = () => win.removeListener('closed', onClosed)
    },
    configChanged(patch: unknown): void {
      if (disposed || !patch || typeof patch !== 'object') return
      if (['appearanceId', 'desktopMascotId', 'desktopMascotEnabled'].some(key => key in patch)) {
        sync()
        if (['desktopMascotId', 'desktopMascotEnabled'].some(key => key in patch)) {
          const preferences = options.readPreferences()
          broadcastMascotChange({
            id: preferences.desktopMascotId ?? null,
            enabled: preferences.desktopMascotEnabled !== false,
          })
        }
      } else if (
        ['desktopMascotFps', 'desktopMascotAnimationPaused', 'desktopMascotIdleMessagePaused'].some(
          key => key in patch
        )
      ) {
        try {
          service?.syncPreferences()
        } catch (error) {
          reportError(error)
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
