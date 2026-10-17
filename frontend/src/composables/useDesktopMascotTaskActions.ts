import { onScopeDispose, ref, watch, type Ref } from 'vue'
import type {
  DesktopMascotHostAPI,
  DesktopMascotMenuResult,
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
  const pending = ref(false)
  let latestRequestId = 0
  let taskOptionsRequest: ReturnType<DesktopMascotTaskControl['list']> | undefined
  let taskOptionsTimer: ReturnType<typeof setTimeout> | undefined
  let startItems: DesktopMascotTaskMenu['start'] = []
  let startState: 'unloaded' | 'loading' | 'loaded' | 'failed' = 'unloaded'
  const cancelTaskOptions = (): void => {
    clearTimeout(taskOptionsTimer)
    taskOptionsTimer = undefined
    const request = taskOptionsRequest
    taskOptionsRequest = undefined
    request?.cancel()
  }
  const canOperate = () => !disposed && options.active.value && options.canOperate()
  const publishMenu = async (requestId: number): Promise<void> => {
    if (disposed || requestId !== latestRequestId) return
    await api.setDesktopMascotTaskMenu(requestId, {
      enabled: canOperate() && !pending.value,
      start: startItems,
      stop: tasks.running(),
      startFailed: startState === 'failed',
      startLoading: startState === 'loading',
    })
  }
  const showNotice = (text: string, reaction?: 'failure') => {
    if (disposed) return
    void api.showDesktopMascotNotice(text, reaction).catch(error => {
      reportWarning('显示桌宠任务提醒失败:', error)
    })
  }

  const loadMenu = async (requestId: number): Promise<void> => {
    latestRequestId = requestId
    cancelTaskOptions()
    startItems = []
    startState = 'unloaded'
    if (canOperate() && !pending.value) {
      const request = tasks.list()
      taskOptionsRequest = request
      startState = 'loading'
      void publishMenu(requestId).catch(error => reportWarning('同步桌宠任务菜单失败:', error))
      // 给宿主超时留出余量；开始列表失败仍可展示当前运行任务。
      const timeout = setTimeout(() => request.cancel(), 2000)
      taskOptionsTimer = timeout
      try {
        const items = await request.result
        if (disposed || latestRequestId !== requestId) return
        startItems = items
        startState = 'loaded'
      } catch (error) {
        if (disposed || latestRequestId !== requestId) return
        startState = 'failed'
        reportWarning('获取桌宠可选任务失败:', error)
      } finally {
        clearTimeout(timeout)
        if (taskOptionsRequest === request) {
          taskOptionsRequest = undefined
          taskOptionsTimer = undefined
        }
      }
    }
    await publishMenu(requestId)
  }

  const performAction = async ({
    action,
    taskId,
  }: DesktopMascotTaskAction): Promise<DesktopMascotMenuResult> => {
    const unavailable = { success: false, message: t('setting.basic.mascotTasksUnavailable') }
    if (!canOperate() || pending.value) return unavailable
    const selected = startItems.find(item => item.taskId === taskId)
    if (
      action === 'start'
        ? !selected?.enabled
        : !tasks.running().some(task => task.taskId === taskId && task.enabled)
    )
      return unavailable
    pending.value = true
    showNotice(
      t(`setting.basic.${action === 'start' ? 'mascotStartingTask' : 'mascotStoppingTask'}`)
    )
    try {
      if (action === 'start') {
        const response = await tasks.start(taskId)
        if (disposed) return unavailable
        options.onStarted({
          taskId: response.taskId,
          selectedTaskId: taskId,
          taskLabel: selected?.label || taskId,
        })
      } else {
        await tasks.stop(taskId)
      }
      // 开始、完成及中止结果沿用共享任务事件，不按 HTTP 返回合成执行结果。
      return { success: true }
    } catch (error) {
      if (disposed) return unavailable
      const text =
        (error instanceof Error ? error.message : String(error)) ||
        t(`scheduler.toast.${action === 'start' ? 'startTaskFailed' : 'stopTaskFailed'}`)
      showError(text)
      showNotice(text, 'failure')
      return { success: false, message: text }
    } finally {
      pending.value = false
    }
  }

  const disposeMenuRequest = api.onDesktopMascotTaskMenuRequest(requestId => {
    void loadMenu(requestId).catch(error => reportWarning('同步桌宠任务菜单失败:', error))
  })
  const disposeAction = api.onDesktopMascotTaskAction((action, requestId) => {
    void performAction(action)
      .then(result => {
        if (!disposed) return api.setDesktopMascotTaskActionResult(requestId, result)
      })
      .catch(error => reportWarning('同步桌宠任务操作结果失败:', error))
  })
  const disposeMenuClosed = api.onDesktopMascotTaskMenuClosed(requestId => {
    if (requestId !== latestRequestId) return
    latestRequestId = 0
    cancelTaskOptions()
    startItems = []
    startState = 'unloaded'
  })
  // 菜单打开后持续反映连接、操作中状态和真实运行实例，不重复拉取配置列表。
  watch(
    () => [options.active.value, options.canOperate(), pending.value, tasks.running()],
    () => {
      if (latestRequestId && canOperate() && !pending.value && startState === 'unloaded') {
        void loadMenu(latestRequestId).catch(error => reportWarning('同步桌宠任务菜单失败:', error))
      } else if (latestRequestId)
        void publishMenu(latestRequestId).catch(error =>
          reportWarning('同步桌宠任务菜单失败:', error)
        )
    },
    { deep: true }
  )
  onScopeDispose(() => {
    disposed = true
    cancelTaskOptions()
    disposeMenuRequest()
    disposeAction()
    disposeMenuClosed()
  })
}
