import { Service, TaskCreateIn } from '@/api'
import { useTaskApi } from './useTaskApi'
import {
  getTaskRuntimeStates,
  onTaskRuntimeEvent,
  type TaskRuntimeState,
} from './useTaskRuntimeState'
import type {
  DesktopMascotTaskControl,
  DesktopMascotTaskEvents,
  DesktopMascotTaskSnapshot,
} from '@/types/desktopMascot'
import { resolveTaskCompletionFeedback, scriptHasStatus } from '@/utils/taskFailures'

const RUNNING_STATUSES = new Set(['运行', '运行中'])

const taskName = (task: TaskRuntimeState): string | null =>
  task.taskName ||
  task.taskInfo
    .map(info => info.name)
    .filter(Boolean)
    .join('、') ||
  null

const taskSnapshot = (task: TaskRuntimeState): DesktopMascotTaskSnapshot => ({
  taskId: task.taskId,
  name: taskName(task),
  working: task.taskInfo.some(info => scriptHasStatus(info, RUNNING_STATUSES)),
})

/** 将 MAS 任务契约转换成桌宠需要的能力和事件，不另建状态或连接。 */
export function useDesktopMascotTaskAdapter(): {
  control: DesktopMascotTaskControl
  events: DesktopMascotTaskEvents
} {
  const taskApi = useTaskApi()
  return {
    control: {
      list() {
        const request = Service.getTaskComboxApiInfoComboxTaskPost()
        return {
          result: request.then(response => {
            if (response.code !== 200) throw new Error(response.message)
            return response.data.flatMap(item =>
              item.value ? [{ taskId: item.value, label: item.label, enabled: true }] : []
            )
          }),
          cancel: () => request.cancel(),
        }
      },
      running: () =>
        getTaskRuntimeStates()
          .filter(
            task => task.phase !== 'completed' && task.mode !== null && task.mode !== 'ScriptConfig'
          )
          .map(task => ({
            taskId: task.taskId,
            label: taskName(task) || task.taskId,
            enabled: !task.stopping,
          })),
      start: async taskId => {
        const response = await taskApi.startTask(
          { taskId, mode: TaskCreateIn.mode.AUTO_PROXY },
          { source: 'mascot' }
        )
        return { taskId: response.taskId }
      },
      stop: taskApi.stopTask,
    },
    events: {
      snapshot: () =>
        getTaskRuntimeStates()
          .filter(task => task.phase !== 'completed' && task.mode !== 'ScriptConfig')
          .map(taskSnapshot),
      subscribe: listener =>
        onTaskRuntimeEvent(event => {
          if (event.type === 'snapshot') {
            listener({
              type: 'snapshot',
              tasks: event.states.filter(task => task.mode !== 'ScriptConfig').map(taskSnapshot),
              activeTaskIds: event.activeTaskIds,
            })
            return
          }
          if (event.type === 'removed') {
            listener(event)
            return
          }
          const { state } = event
          if (state.mode === 'ScriptConfig') return
          const task = taskSnapshot(state)
          if (event.type === 'info' && task.working) {
            listener({ type: 'started', task })
          } else if (event.type === 'completed' && state.outcome) {
            const feedback = resolveTaskCompletionFeedback({
              outcome: state.outcome,
              task_info: state.taskInfo,
            })
            listener({
              type: 'completed',
              task,
              result:
                feedback.kind === 'error'
                  ? 'failure'
                  : feedback.kind === 'cancelled'
                    ? 'stopped'
                    : feedback.kind,
            })
          }
        }),
    },
  }
}
