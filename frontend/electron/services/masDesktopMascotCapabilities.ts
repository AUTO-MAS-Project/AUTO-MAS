import { systemPreferences, type BrowserWindow } from 'electron'
import type {
  DesktopMascotMenuLabels,
  DesktopMascotMenuResult,
  DesktopMascotMenuAction,
  DesktopMascotMenuCapability,
  DesktopMascotTaskAction,
  DesktopMascotTaskMenu,
} from '../../src/types/desktopMascot'
import { registerDesktopMascotHandlers } from '../ipc/mascotHandlers'
import type {
  DesktopMascotCapabilities,
  DesktopMascotHostInputs,
  DesktopMascotPreferences,
} from './desktopMascotTypes'

interface MasDesktopMascotCapabilitiesOptions {
  readPreferences(): DesktopMascotPreferences
  savePreferences(patch: Partial<DesktopMascotPreferences>): void
  getMainWindow(): BrowserWindow | null
  onPreferencesChanged(): void
}

/** MAS 能力及 IPC 适配；只向运行宿主提供快照、订阅和操作契约。 */
export function createMasDesktopMascotCapabilities(options: MasDesktopMascotCapabilitiesOptions) {
  let disposed = false
  let ready = false
  let working = false
  let labels: DesktopMascotMenuLabels | undefined
  let taskMenu: DesktopMascotTaskMenu | null = null
  let menuRequestId = 0
  let activeMenuRequestId = 0
  let actionRequestId = 0
  let actionRequest:
    | {
        id: number
        resolve(result: DesktopMascotMenuResult): void
        timer: ReturnType<typeof setTimeout>
      }
    | undefined
  const listeners = new Set<() => void>()
  const publish = (): void => listeners.forEach(listener => listener())
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
    activeMenuRequestId = 0
    taskMenu = null
    const win = options.getMainWindow()
    if (id && win && !win.isDestroyed()) win.webContents.send('desktop-mascot:task-menu-closed', id)
  }
  const snapshot = (): ReturnType<DesktopMascotCapabilities['snapshot']> => {
    if (!ready || !labels) return null
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
    const data = snapshot()
    const capability = data?.capabilities.find(item => item.id === action.capability)
    if (disposed || !capability?.enabled) return unavailable()
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
      options.onPreferencesChanged()
      publish()
    }
    return { success: true }
  }
  return {
    snapshot,
    execute,
    subscribe(listener: () => void): () => void {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
    open(): void {
      if (disposed) return
      cancelMenuRequest()
      const win = options.getMainWindow()
      if (!ready || !win || win.isDestroyed()) return
      const id = ++menuRequestId
      activeMenuRequestId = id
      win.webContents.send('desktop-mascot:task-menu-request', id)
    },
    close: cancelMenuRequest,
    reset(): void {
      cancelMenuRequest()
      finishAction(unavailable())
    },
    register(inputs: DesktopMascotHostInputs): () => void {
      return registerDesktopMascotHandlers(
        {
          ...inputs,
          setReady(nextReady, nextLabels, colors): void {
            ready = nextReady
            if (nextLabels) labels = nextLabels
            inputs.setReady(ready, colors)
            publish()
          },
          setActivity(nextWorking, animate): void {
            working = nextWorking
            inputs.setActivity(working, animate)
            publish()
          },
        },
        options.getMainWindow,
        (id, nextMenu) => {
          if (id !== activeMenuRequestId || disposed) return
          taskMenu = nextMenu
          publish()
        },
        (id, result) => {
          if (actionRequest?.id === id) finishAction(result)
        }
      )
    },
    dispose(): void {
      disposed = true
      cancelMenuRequest()
      finishAction(unavailable())
      listeners.clear()
    },
  }
}
