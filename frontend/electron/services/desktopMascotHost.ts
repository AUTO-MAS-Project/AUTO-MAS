import type { BrowserWindow } from 'electron'
import type {
  DesktopMascotColors,
  DesktopMascotIdleMessage,
  DesktopMascotMenuData,
} from '../../src/types/desktopMascot'
import type { MascotAssets, MascotMenuDefinition } from '../../src/types/mascotPack'
import { broadcastMascotChange } from '../ipc/mascotHandlers'
import { getLogger } from './logger'
import type { DesktopMascotMenuOptions, DesktopMascotMenuRuntime } from './desktopMascotMenuService'
import type {
  DesktopMascotCapabilities,
  DesktopMascotHostInputs,
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
  capabilities: DesktopMascotCapabilities
  defaultMenu: MascotMenuDefinition
  registerHandlers(inputs: DesktopMascotHostInputs): () => void
  createRuntime(options: DesktopMascotOptions): DesktopMascotRuntime
  createMenuRuntime(options: DesktopMascotMenuOptions): DesktopMascotMenuRuntime
}

/** 运行宿主协调窗口、包和能力契约，不解释 MAS 任务或具体菜单能力。 */
export function createDesktopMascotHost(options: DesktopMascotHostOptions) {
  const logger = getLogger('桌面桌宠')
  const capabilities = options.capabilities
  let service: DesktopMascotRuntime | undefined
  let menu: DesktopMascotMenuRuntime | undefined
  let disposed = false
  let detachMainWindow: (() => void) | undefined
  // 共享输入由宿主保留，重建窗口只恢复当前状态，不重播历史提醒。
  let ready = false
  let colors: DesktopMascotColors | undefined
  let idleMessage: DesktopMascotIdleMessage | undefined
  let working = false
  let animate = true
  let presentation = options.defaultMenu
  const reportError = (error: unknown): void => {
    logger.error('桌面桌宠更新失败:', error)
    const win = options.getMainWindow()
    if (win && !win.isDestroyed()) win.webContents.send('desktop-mascot:error')
  }
  const menuData = (): DesktopMascotMenuData | null => {
    if (!ready || !colors) return null
    const snapshot = capabilities.snapshot()
    return snapshot ? { protocolVersion: 1, presentation, colors, ...snapshot } : null
  }
  const updateMenu = (): void => {
    const data = menuData()
    if (data) menu?.update(data)
    else menu?.close()
  }
  const syncPreferences = (): void => {
    if (disposed) return
    service?.syncPreferences()
    updateMenu()
  }
  const serviceOptions: DesktopMascotOptions = {
    readPreferences: options.readPreferences,
    resolveAssets: () => {
      menu?.close()
      capabilities.close()
      const { appearanceId, desktopMascotId } = options.readPreferences()
      const assets = options.resolveAssets({ appearanceId, desktopMascotId })
      presentation = assets?.mascot?.menu ?? options.defaultMenu
      return assets
    },
    savePosition: position => options.savePreferences({ desktopMascotPosition: position }),
    getInitialBounds: () => options.getMainWindow()?.getBounds(),
    onContextMenu: position => {
      if (disposed) return
      capabilities.close()
      const data = menuData()
      if (!data) return
      menu?.open(position, data)
      capabilities.open()
    },
    onClosed: () => {
      menu?.close()
      capabilities.close()
    },
    onError: reportError,
  }
  const unsubscribe = capabilities.subscribe(updateMenu)
  const disposeHandlers = options.registerHandlers({
    setReady(nextReady, nextColors): void {
      if (disposed) return
      ready = nextReady
      if (!ready) capabilities.reset()
      if (nextColors) colors = nextColors
      service?.setReady(ready, colors)
      updateMenu()
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
  })

  const unmount = (): void => {
    capabilities.reset()
    const previousMenu = menu
    menu = undefined
    previousMenu?.dispose()
    const previous = service
    service = undefined
    previous?.dispose()
  }
  const sync = (): void => {
    if (disposed) return
    menu?.close()
    capabilities.close()
    try {
      service?.sync()
    } catch (error) {
      reportError(error)
    }
  }
  return {
    mount(): void {
      if (disposed || service) return
      menu = options.createMenuRuntime({
        execute: async action => {
          const data = menuData()
          if (
            disposed ||
            !data ||
            !presentation.items.some(
              item => 'capability' in item && item.capability === action.capability
            ) ||
            !data.capabilities.some(item => item.id === action.capability && item.enabled)
          )
            return { success: false, message: data?.unavailableLabel }
          return capabilities.execute(action)
        },
        onError: reportError,
        onClosed: () => capabilities.close(),
      })
      service = options.createRuntime(serviceOptions)
      if (idleMessage) service.setIdleMessage(idleMessage)
      service.setActivity(working, animate)
      service.setReady(ready, colors)
    },
    unmount,
    sync,
    syncPreferences,
    attachMainWindow(win: BrowserWindow): void {
      if (disposed) return
      detachMainWindow?.()
      ready = false
      capabilities.reset()
      menu?.close()
      service?.setReady(false)
      const onClosed = (): void => {
        if (options.getMainWindow() !== win) return
        ready = false
        capabilities.reset()
        menu?.close()
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
          syncPreferences()
        } catch (error) {
          reportError(error)
        }
      }
    },
    dispose(): void {
      if (disposed) return
      disposed = true
      disposeHandlers()
      unsubscribe()
      detachMainWindow?.()
      unmount()
      capabilities.dispose()
    },
  }
}
