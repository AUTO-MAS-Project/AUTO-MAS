import { systemPreferences, type BrowserWindow } from 'electron'
import type {
  DesktopMascotColors,
  DesktopMascotIdleMessage,
  DesktopMascotMenuAction,
  DesktopMascotMenuCapability,
  DesktopMascotMenuData,
  DesktopMascotMenuLabels,
  DesktopMascotMenuResult,
  DesktopMascotTaskAction,
  DesktopMascotTaskMenu,
} from '../../src/types/desktopMascot'
import type { MascotAssets, MascotMenuDefinition } from '../../src/types/mascotPack'
import { broadcastMascotChange, registerDesktopMascotHandlers } from '../ipc/mascotHandlers'
import { getLogger } from './logger'
import type { DesktopMascotMenuOptions, DesktopMascotMenuRuntime } from './desktopMascotMenuService'
import { DEFAULT_MASCOT_MENU } from './mascotMenuDefinition'
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
  createMenuRuntime(options: DesktopMascotMenuOptions): DesktopMascotMenuRuntime
}

/** 宿主提供能力，包提供菜单 UI；窗口运行时不解释任务业务或菜单结构。 */
export function createDesktopMascotHost(options: DesktopMascotHostOptions) {
  const logger = getLogger('桌面桌宠')
  let service: DesktopMascotRuntime | undefined
  let menu: DesktopMascotMenuRuntime | undefined
  let disposed = false
  let detachMainWindow: (() => void) | undefined
  // 共享输入由宿主保留，重建窗口只恢复当前状态，不重播历史提醒。
  let ready = false
  let labels: DesktopMascotMenuLabels | undefined
  let colors: DesktopMascotColors | undefined
  let idleMessage: DesktopMascotIdleMessage | undefined
  let working = false
  let animate = true
  let presentation: MascotMenuDefinition = DEFAULT_MASCOT_MENU
  let taskMenu: DesktopMascotTaskMenu | null = null
  let menuRequestId = 0
  let activeMenuRequestId = 0
  let menuTimer: ReturnType<typeof setTimeout> | undefined
  let actionRequestId = 0
  let actionRequest:
    | {
        id: number
        resolve(result: DesktopMascotMenuResult): void
        timer: ReturnType<typeof setTimeout>
      }
    | undefined

  const unavailable = (): DesktopMascotMenuResult => ({
    success: false,
    message: labels?.capabilityUnavailable,
  })
  const finishAction = (result: DesktopMascotMenuResult): void => {
    if (!actionRequest) return
    const request = actionRequest
    actionRequest = undefined
    clearTimeout(request.timer)
    request.resolve(result)
  }
  const cancelMenuRequest = (): void => {
    const id = activeMenuRequestId
    clearTimeout(menuTimer)
    menuTimer = undefined
    activeMenuRequestId = 0
    taskMenu = null
    const win = options.getMainWindow()
    if (id && win && !win.isDestroyed()) win.webContents.send('desktop-mascot:task-menu-closed', id)
  }
  const reportError = (error: unknown): void => {
    logger.error('桌面桌宠更新失败:', error)
    const win = options.getMainWindow()
    if (win && !win.isDestroyed()) win.webContents.send('desktop-mascot:error')
  }
  const menuData = (): DesktopMascotMenuData | null => {
    if (!ready || !labels || !colors) return null
    const menuLabels = labels
    const preferences = options.readPreferences()
    const animationPaused =
      preferences.desktopMascotAnimationPaused === true ||
      (typeof preferences.desktopMascotAnimationPaused !== 'boolean' &&
        systemPreferences.getAnimationSettings().prefersReducedMotion)
    const idlePaused = preferences.desktopMascotIdleMessagePaused === true
    const tasks = (action: 'start' | 'stop'): DesktopMascotMenuCapability => ({
      id: `task.${action}`,
      label: action === 'start' ? menuLabels.quickStart : menuLabels.stopTask,
      enabled: Boolean(
        taskMenu?.enabled &&
        !(action === 'start' && (taskMenu.startFailed || taskMenu.startLoading))
      ),
      loading: action === 'start' && taskMenu?.startLoading === true,
      disabledReason:
        !taskMenu?.enabled || (action === 'start' && taskMenu.startFailed)
          ? menuLabels.tasksUnavailable
          : action === 'start' && taskMenu.startLoading
            ? menuLabels.loadingTasks
            : undefined,
      options: (taskMenu?.[action] ?? []).map(item => ({
        value: item.taskId,
        label: item.label,
        enabled: item.enabled,
      })),
      emptyLabel:
        !taskMenu || (action === 'start' && taskMenu.startFailed)
          ? menuLabels.tasksUnavailable
          : action === 'start'
            ? menuLabels.noTasks
            : menuLabels.noRunningTasks,
    })
    return {
      protocolVersion: 1,
      presentation,
      colors,
      unavailableLabel: labels.capabilityUnavailable,
      capabilities: [
        tasks('start'),
        tasks('stop'),
        {
          id: 'idle.refresh',
          label: labels.refreshIdleMessage,
          enabled: !idlePaused && !working,
          disabledReason: idlePaused || working ? labels.refreshUnavailable : undefined,
        },
        {
          id: 'idle.toggle',
          label: idlePaused ? labels.resumeIdleMessage : labels.pauseIdleMessage,
          enabled: true,
          checked: idlePaused,
        },
        {
          id: 'animation.toggle',
          label: animationPaused ? labels.resumeAnimation : labels.pauseAnimation,
          enabled: true,
          checked: animationPaused,
        },
      ],
    }
  }
  const updateMenu = (): void => {
    const data = menuData()
    if (data) menu?.update(data)
    else menu?.close()
  }
  const executeTask = (action: DesktopMascotTaskAction): Promise<DesktopMascotMenuResult> => {
    const win = options.getMainWindow()
    if (disposed || !ready || !win || win.isDestroyed() || actionRequest)
      return Promise.resolve(unavailable())
    const id = ++actionRequestId
    return new Promise(resolve => {
      actionRequest = { id, resolve, timer: setTimeout(() => finishAction(unavailable()), 30000) }
      win.webContents.send('desktop-mascot:task-action', action, id)
    })
  }
  const execute = async (action: DesktopMascotMenuAction): Promise<DesktopMascotMenuResult> => {
    const data = menuData()
    const declared = presentation.items.some(
      item => 'capability' in item && item.capability === action.capability
    )
    const capability = data?.capabilities.find(item => item.id === action.capability)
    if (disposed || !declared || !capability?.enabled) return unavailable()
    if (capability.options) {
      if (typeof action.value !== 'string') return unavailable()
      if (!capability.options.some(item => item.value === action.value && item.enabled))
        return unavailable()
      return executeTask({
        action: capability.id === 'task.start' ? 'start' : 'stop',
        taskId: action.value,
      })
    }
    if (action.value !== undefined) return unavailable()
    if (action.capability === 'idle.refresh') {
      const win = options.getMainWindow()
      if (!win || win.isDestroyed()) return unavailable()
      win.webContents.send('desktop-mascot:refresh-idle-message')
    } else {
      options.savePreferences(
        action.capability === 'idle.toggle'
          ? { desktopMascotIdleMessagePaused: !capability.checked }
          : { desktopMascotAnimationPaused: !capability.checked }
      )
      service?.syncPreferences()
      updateMenu()
    }
    return { success: true }
  }
  const serviceOptions: DesktopMascotOptions = {
    readPreferences: options.readPreferences,
    resolveAssets: () => {
      menu?.close()
      cancelMenuRequest()
      const { appearanceId, desktopMascotId } = options.readPreferences()
      const assets = options.resolveAssets({ appearanceId, desktopMascotId })
      presentation = assets?.mascot?.menu ?? DEFAULT_MASCOT_MENU
      return assets
    },
    savePosition: position => options.savePreferences({ desktopMascotPosition: position }),
    getInitialBounds: () => options.getMainWindow()?.getBounds(),
    onContextMenu: position => {
      if (disposed) return
      cancelMenuRequest()
      const data = menuData()
      if (!data) return
      menu?.open(position, data)
      const win = options.getMainWindow()
      if (!win || win.isDestroyed()) return
      const id = ++menuRequestId
      activeMenuRequestId = id
      // 任务列表超时只停用任务能力，本地留言和动画仍可操作。
      menuTimer = setTimeout(() => {
        menuTimer = undefined
        if (activeMenuRequestId === id) updateMenu()
      }, 3000)
      win.webContents.send('desktop-mascot:task-menu-request', id)
    },
    onClosed: () => {
      menu?.close()
      cancelMenuRequest()
    },
    onError: reportError,
  }
  const disposeHandlers = registerDesktopMascotHandlers(
    {
      setReady(nextReady, nextLabels, nextColors): void {
        if (disposed) return
        ready = nextReady
        if (!ready) {
          cancelMenuRequest()
          finishAction(unavailable())
        }
        if (nextLabels) labels = nextLabels
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
        updateMenu()
      },
      getData: sender => service?.getData(sender) ?? null,
      handlePointer: (sender, action, session) => service?.handlePointer(sender, action, session),
      startDrag: (sender, offset) => service?.startDrag(sender, offset) ?? false,
      setDecodedImage: (sender, imageUrl, pngDataUrl) =>
        service?.setDecodedImage(sender, imageUrl, pngDataUrl),
      showNotice: (text, reaction) => service?.showNotice(text, reaction),
    },
    options.getMainWindow,
    (id, nextMenu) => {
      if (id !== activeMenuRequestId || disposed) return
      clearTimeout(menuTimer)
      menuTimer = undefined
      taskMenu = nextMenu
      updateMenu()
    },
    (id, result) => {
      if (actionRequest?.id === id) finishAction(result)
    }
  )

  const unmount = (): void => {
    cancelMenuRequest()
    finishAction(unavailable())
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
    cancelMenuRequest()
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
        execute,
        onError: reportError,
        onClosed: cancelMenuRequest,
      })
      service = options.createRuntime(serviceOptions)
      if (idleMessage) service.setIdleMessage(idleMessage)
      service.setActivity(working, animate)
      service.setReady(ready, colors)
    },
    unmount,
    sync,
    attachMainWindow(win: BrowserWindow): void {
      if (disposed) return
      detachMainWindow?.()
      ready = false
      cancelMenuRequest()
      finishAction(unavailable())
      menu?.close()
      service?.setReady(false)
      const onClosed = (): void => {
        if (options.getMainWindow() !== win) return
        ready = false
        cancelMenuRequest()
        finishAction(unavailable())
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
          service?.syncPreferences()
          updateMenu()
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
