import { onScopeDispose, type Ref } from 'vue'
import { message } from 'ant-design-vue'
import { TaskCreateIn } from '@/api'
import { translate as t } from '@/i18n'
import { useAudioPlayer } from '@/composables/useAudioPlayer'
import { useTaskApi } from '@/composables/useTaskApi'

interface TrayTaskActionsOptions {
  active: Readonly<Ref<boolean>>
  canStart(): boolean
  onStarted(task: { taskId: string; selectedTaskId: string; taskLabel: string }): void
}

/** 托盘启动入口跟随应用作用域，不依赖标题栏组件的挂载。 */
export function useTrayTaskActions(options: TrayTaskActionsOptions): void {
  const logger = window.electronAPI.getLogger('托盘任务')
  const { startTask } = useTaskApi()
  const { playSound } = useAudioPlayer()
  let disposed = false
  const dispose = window.electronAPI.onTrayActionRequest?.(request => {
    if (request.action !== 'startTask' || !options.active.value || !options.canStart()) return
    const { taskId, label } = request
    if (!taskId) {
      logger.warn('托盘启动任务缺少任务 ID，忽略')
      return
    }
    void startTask({ taskId, mode: TaskCreateIn.mode.AUTO_PROXY })
      .then(response => {
        if (disposed) return
        options.onStarted({
          taskId: response.taskId,
          selectedTaskId: taskId,
          taskLabel: label || taskId,
        })
        message.success(t('scheduler.toast.taskBegun'))
        void playSound('task_started').catch(error => {
          logger.warn('播放任务启动音频失败:', error)
        })
      })
      .catch(error => {
        if (disposed) return
        const errorMsg = error instanceof Error ? error.message : String(error)
        logger.error('托盘启动任务失败:', errorMsg)
        message.error(errorMsg)
      })
  })
  onScopeDispose(() => {
    disposed = true
    dispose?.()
  })
}
