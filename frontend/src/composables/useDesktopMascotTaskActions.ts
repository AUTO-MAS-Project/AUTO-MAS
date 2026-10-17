import { onScopeDispose, type Ref } from 'vue'
import type {
  DesktopMascotHostAPI,
  DesktopMascotTaskAction,
  DesktopMascotTaskControl,
  DesktopMascotTaskHostAPI,
  DesktopMascotTaskMenu,
} from '@/types/desktopMascot'

interface DesktopMascotTaskActionsOptions {
  active: Readonly<Ref<boolean>>
  canOperate(): boolean
  api: DesktopMascotTaskHostAPI & Pick<DesktopMascotHostAPI, 'showDesktopMascotNotice'>
  onStarted(task: { taskId: string; selectedTaskId: string; taskLabel: string }): void
}

interface DesktopMascotTaskActionsCapabilities {
  tasks: DesktopMascotTaskControl
  translate(key: string): string
  reportWarning(message: string, error: unknown): void
  showError(message: string): void
}

/** 任务业务留在应用作用域；原生桌宠仅请求菜单和回传选择。 */
export function useDesktopMascotTaskActions(
  options: DesktopMascotTaskActionsOptions,
  capabilities: DesktopMascotTaskActionsCapabilities
): void {
  const { api } = options
  const { tasks, translate: t, reportWarning, showError } = capabilities
  let disposed = false
  let pending = false
  let latestRequestId = 0
  let taskOptionsRequest: ReturnType<DesktopMascotTaskControl['list']> | undefined
  let startItems: DesktopMascotTaskMenu['start'] = []
  const canOperate = () => !disposed && options.active.value && options.canOperate()
  const showNotice = (text: string, reaction?: 'failure') => {
    if (disposed) return
    void api.showDesktopMascotNotice(text, reaction).catch(error => {
      reportWarning('显示桌宠任务提醒失败:', error)
    })
  }

  const loadMenu = async (requestId: number): Promise<void> => {
    latestRequestId = requestId
    taskOptionsRequest?.cancel()
    startItems = []
    let startFailed = false
    if (canOperate() && !pending) {
      const request = tasks.list()
      taskOptionsRequest = request
      // 给宿主超时留出余量；开始列表失败仍可展示当前运行任务。
      const timeout = setTimeout(() => request.cancel(), 2000)
      try {
        const items = await request.result
        if (disposed || latestRequestId !== requestId) return
        startItems = items
      } catch (error) {
        if (disposed || latestRequestId !== requestId) return
        startFailed = true
        reportWarning('获取桌宠可选任务失败:', error)
      } finally {
        clearTimeout(timeout)
        if (taskOptionsRequest === request) taskOptionsRequest = undefined
      }
    }
    if (disposed || latestRequestId !== requestId) return
    await api.setDesktopMascotTaskMenu(requestId, {
      enabled: canOperate() && !pending,
      start: startItems,
      stop: tasks.running(),
      startFailed,
    })
  }

  const performAction = async ({ action, taskId }: DesktopMascotTaskAction): Promise<void> => {
    if (!canOperate() || pending) return
    const selected = startItems.find(item => item.taskId === taskId)
    if (
      action === 'start'
        ? !selected
        : !tasks.running().some(task => task.taskId === taskId && task.enabled)
    )
      return
    pending = true
    showNotice(
      t(`setting.basic.${action === 'start' ? 'mascotStartingTask' : 'mascotStoppingTask'}`)
    )
    try {
      if (action === 'start') {
        const response = await tasks.start(taskId)
        if (disposed) return
        options.onStarted({
          taskId: response.taskId,
          selectedTaskId: taskId,
          taskLabel: selected?.label || taskId,
        })
      } else {
        await tasks.stop(taskId)
      }
      // 开始、完成及中止结果沿用共享任务事件，不按 HTTP 返回合成执行结果。
    } catch (error) {
      if (disposed) return
      const text =
        (error instanceof Error ? error.message : String(error)) ||
        t(`scheduler.toast.${action === 'start' ? 'startTaskFailed' : 'stopTaskFailed'}`)
      showError(text)
      showNotice(text, 'failure')
    } finally {
      pending = false
    }
  }

  const disposeMenuRequest = api.onDesktopMascotTaskMenuRequest(requestId => {
    void loadMenu(requestId).catch(error => reportWarning('同步桌宠任务菜单失败:', error))
  })
  const disposeAction = api.onDesktopMascotTaskAction(action => {
    void performAction(action)
  })
  onScopeDispose(() => {
    disposed = true
    taskOptionsRequest?.cancel()
    disposeMenuRequest()
    disposeAction()
  })
}
