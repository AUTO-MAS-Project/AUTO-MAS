import { onScopeDispose, type Ref } from 'vue'
import { message } from 'ant-design-vue'
import { Service, TaskCreateIn } from '@/api'
import { translate as t } from '@/i18n'
import { useAudioPlayer } from './useAudioPlayer'
import { useTaskApi } from './useTaskApi'
import { getTaskRuntimeStates } from './useTaskRuntimeState'
import type {
  DesktopMascotHostAPI,
  DesktopMascotTaskAction,
  DesktopMascotTaskHostAPI,
  DesktopMascotTaskMenu,
} from '@/types/desktopMascot'

interface DesktopMascotTaskActionsOptions {
  active: Readonly<Ref<boolean>>
  canOperate(): boolean
  api: DesktopMascotTaskHostAPI & Pick<DesktopMascotHostAPI, 'showDesktopMascotNotice'>
  onStarted(task: { taskId: string; selectedTaskId: string; taskLabel: string }): void
}

/** 任务业务留在应用作用域；原生桌宠仅请求菜单和回传选择。 */
export function useDesktopMascotTaskActions(options: DesktopMascotTaskActionsOptions): void {
  const logger = window.electronAPI.getLogger('桌宠任务')
  const { startTask, stopTask } = useTaskApi()
  const { playSound } = useAudioPlayer()
  const { api } = options
  let disposed = false
  let pending = false
  let latestRequestId = 0
  let taskOptionsRequest: ReturnType<typeof Service.getTaskComboxApiInfoComboxTaskPost> | undefined
  let startItems: DesktopMascotTaskMenu['start'] = []
  const canOperate = () => !disposed && options.active.value && options.canOperate()
  const runningTasks = () =>
    getTaskRuntimeStates().filter(
      task => task.phase !== 'completed' && task.mode !== null && task.mode !== 'ScriptConfig'
    )
  const showNotice = (text: string, reaction?: 'failure') => {
    if (disposed) return
    void api.showDesktopMascotNotice(text, reaction).catch(error => {
      logger.warn('显示桌宠任务提醒失败:', error)
    })
  }

  const loadMenu = async (requestId: number): Promise<void> => {
    latestRequestId = requestId
    taskOptionsRequest?.cancel()
    startItems = []
    let startFailed = false
    if (canOperate() && !pending) {
      const request = Service.getTaskComboxApiInfoComboxTaskPost()
      taskOptionsRequest = request
      // 给宿主超时留出余量；开始列表失败仍可展示当前运行任务。
      const timeout = window.setTimeout(() => request.cancel(), 2000)
      try {
        const response = await request
        if (disposed || latestRequestId !== requestId) return
        if (response.code !== 200) throw new Error(response.message)
        startItems = response.data.flatMap(item =>
          item.value ? [{ taskId: item.value, label: item.label, enabled: true }] : []
        )
      } catch (error) {
        if (disposed || latestRequestId !== requestId) return
        startFailed = true
        logger.warn('获取桌宠可选任务失败:', error)
      } finally {
        window.clearTimeout(timeout)
        if (taskOptionsRequest === request) taskOptionsRequest = undefined
      }
    }
    if (disposed || latestRequestId !== requestId) return
    await api.setDesktopMascotTaskMenu(requestId, {
      enabled: canOperate() && !pending,
      start: startItems,
      stop: runningTasks().map(task => ({
        taskId: task.taskId,
        label:
          task.taskName ||
          task.taskInfo
            .map(info => info.name)
            .filter(Boolean)
            .join('、') ||
          task.taskId,
        enabled: !task.stopping,
      })),
      startFailed,
    })
  }

  const performAction = async ({ action, taskId }: DesktopMascotTaskAction): Promise<void> => {
    if (!canOperate() || pending) return
    const selected = startItems.find(item => item.taskId === taskId)
    if (
      action === 'start'
        ? !selected
        : !runningTasks().some(task => task.taskId === taskId && !task.stopping)
    )
      return
    pending = true
    showNotice(
      t(`setting.basic.${action === 'start' ? 'mascotStartingTask' : 'mascotStoppingTask'}`)
    )
    try {
      if (action === 'start') {
        const response = await startTask({ taskId, mode: TaskCreateIn.mode.AUTO_PROXY })
        if (disposed) return
        options.onStarted({
          taskId: response.taskId,
          selectedTaskId: taskId,
          taskLabel: selected?.label || taskId,
        })
        void playSound('task_started').catch(error => logger.warn('播放任务启动音频失败:', error))
      } else {
        await stopTask(taskId)
      }
      // 开始、完成及中止结果沿用共享任务事件，不按 HTTP 返回合成执行结果。
    } catch (error) {
      if (disposed) return
      const text =
        (error instanceof Error ? error.message : String(error)) ||
        t(`scheduler.toast.${action === 'start' ? 'startTaskFailed' : 'stopTaskFailed'}`)
      logger.error('桌宠任务操作失败:', text)
      message.error(text)
      showNotice(text, 'failure')
    } finally {
      pending = false
    }
  }

  const disposeMenuRequest = api.onDesktopMascotTaskMenuRequest(requestId => {
    void loadMenu(requestId).catch(error => logger.warn('同步桌宠任务菜单失败:', error))
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
