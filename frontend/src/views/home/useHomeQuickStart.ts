import { translate as t } from '@/i18n'
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import { Service } from '@/api/services/Service'
import { useAudioPlayer } from '@/composables/useAudioPlayer'
import { getConfig, saveConfig } from '@/utils/config'
import { navigateTo } from '@/router'
import {
  launchHomeTasks,
  normalizeHomeQuickStartSelection,
  retainSelectedTaskIds,
  toHomeTaskOptions,
  type HomeTaskOption,
} from '@/views/home/homeQuickStartTasks'
import { pickHomeGreeting } from '@/views/home/homeGreeting'
import { useSchedulerLogic } from '@/views/scheduler/useSchedulerLogic'

export const useHomeQuickStart = () => {
  const logger = window.electronAPI.getLogger('首页')
  const { playSound } = useAudioPlayer()
  const { trackStartedTask } = useSchedulerLogic()

  const homeGreeting = pickHomeGreeting()
  const commandTitle = ref(homeGreeting.text)
  const commandAuthor = ref(homeGreeting.author)

  const refreshGreeting = () => {
    const nextGreeting = pickHomeGreeting(commandTitle.value)
    commandTitle.value = nextGreeting.text
    commandAuthor.value = nextGreeting.author
  }

  const schedulerTasksLoading = ref(false)
  // 任务列表拉取失败：下拉里给一句提示，重新展开下拉即重试
  const schedulerTasksUnavailable = ref(false)
  const startingHomeTask = ref(false)

  const schedulerTaskOptions = ref<HomeTaskOption[]>([])
  const selectedHomeTaskIds = ref<string[]>([])
  const selectedHomeMode = ref<TaskCreateIn.mode>(TaskCreateIn.mode.AUTO_PROXY)
  let savedSelectedTaskIds: string[] = []
  let selectionTouched = false
  let selectionSaveQueue = Promise.resolve()

  const sameTaskIds = (left: string[], right: string[]) => {
    return left.length === right.length && left.every((taskId, index) => taskId === right[index])
  }

  const logWarning = (warning: string, error: unknown) => {
    const errorMessage = error instanceof Error ? error.message : String(error)
    logger.warn(`${warning}: ${errorMessage}`)
  }

  const queueSelectionSave = (taskIds: string[]) => {
    const normalizedTaskIds = normalizeHomeQuickStartSelection(taskIds)
    const saveTask = selectionSaveQueue.then(() =>
      saveConfig({ homeQuickStartSelectedTaskIds: normalizedTaskIds })
    )
    selectionSaveQueue = saveTask.catch(error => {
      logWarning('保存首页快速启动选择失败', error)
    })
    return saveTask.catch(() => undefined)
  }

  const restoreSelectedHomeTaskIds = async () => {
    try {
      const config = await getConfig()
      if (selectionTouched) return
      savedSelectedTaskIds = normalizeHomeQuickStartSelection(config.homeQuickStartSelectedTaskIds)
      selectedHomeTaskIds.value = [...savedSelectedTaskIds]
    } catch (error) {
      logWarning('读取首页快速启动选择失败', error)
    }
  }

  const updateSelectedHomeTaskIds = (taskIds: string[]) => {
    const normalizedTaskIds = normalizeHomeQuickStartSelection(taskIds)
    selectionTouched = true
    savedSelectedTaskIds = normalizedTaskIds
    selectedHomeTaskIds.value = [...normalizedTaskIds]
    void queueSelectionSave(normalizedTaskIds)
  }

  const applyRealTaskOptions = (taskOptions: HomeTaskOption[]) => {
    schedulerTaskOptions.value = taskOptions
    const previousSavedTaskIds = savedSelectedTaskIds
    const baseTaskIds = selectionTouched
      ? selectedHomeTaskIds.value
      : selectedHomeTaskIds.value.length
        ? selectedHomeTaskIds.value
        : savedSelectedTaskIds
    const retainedTaskIds = retainSelectedTaskIds(baseTaskIds, taskOptions)
    savedSelectedTaskIds = retainedTaskIds

    if (!sameTaskIds(selectedHomeTaskIds.value, retainedTaskIds)) {
      selectedHomeTaskIds.value = retainedTaskIds
    }
    if (!sameTaskIds(previousSavedTaskIds, retainedTaskIds)) {
      void queueSelectionSave(retainedTaskIds)
    }
  }

  const fetchSchedulerTaskOptions = async (options?: { quiet?: boolean }) => {
    schedulerTasksLoading.value = true

    try {
      const response = await Service.getTaskComboxApiInfoComboxTaskPost()
      if (response.code === 200 && Array.isArray(response.data)) {
        schedulerTasksUnavailable.value = false
        applyRealTaskOptions(toHomeTaskOptions(response.data))
        return
      }

      schedulerTasksUnavailable.value = true
      if (!options?.quiet) {
        message.warning(t('home.quickStart.listUnavailable'))
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.warn(`获取首页任务列表失败: ${errorMsg}`)
      schedulerTasksUnavailable.value = true
      if (!options?.quiet) {
        message.warning(t('home.quickStart.listUnavailable'))
      }
    } finally {
      schedulerTasksLoading.value = false
    }
  }

  const onSchedulerDropdownVisibleChange = (open: boolean) => {
    if (open) {
      fetchSchedulerTaskOptions({ quiet: true })
    }
  }

  const startHomeTask = async () => {
    if (schedulerTasksLoading.value) return

    const taskIds = retainSelectedTaskIds(selectedHomeTaskIds.value, schedulerTaskOptions.value)
    if (!taskIds.length) {
      message.error(t('home.quickStart.selectTask'))
      return
    }

    startingHomeTask.value = true
    try {
      const outcome = await launchHomeTasks({
        taskIds,
        options: schedulerTaskOptions.value,
        fallbackLabel: t('home.quickStart.fallbackLabel'),
        failureReason: t('home.quickStart.startFailed'),
        startTask: taskId =>
          Service.addTaskApiDispatchStartPost({
            taskId,
            mode: selectedHomeMode.value,
          }),
        onTaskStarted: result => {
          trackStartedTask({
            taskId: result.taskId,
            selectedTaskId: result.selectedTaskId,
            selectedMode: selectedHomeMode.value,
            taskLabel: result.taskLabel,
            modeLabel: '自动代理',
          })
        },
      })

      for (const failure of outcome.failed) {
        logger.warn(`首页开始任务失败: ${failure.taskLabel}: ${failure.reason}`)
      }

      if (outcome.started.length) {
        message.success(
          t('home.quickStart.startedCount', {
            p0: outcome.started.length,
            p1: taskIds.length,
          })
        )
      }
      if (outcome.failed.length) {
        const failureSummary = outcome.failed
          .map(failure => `${failure.taskLabel}: ${failure.reason}`)
          .join('; ')
        message.error(t('home.quickStart.startFailedItems', { p0: failureSummary }))
      }
      if (outcome.started.length) {
        await navigateTo('/scheduler')
        void playSound('task_started')
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`首页开始任务失败: ${errorMsg}`)
      message.error(t('home.quickStart.startError'))
    } finally {
      startingHomeTask.value = false
    }
  }

  return {
    commandTitle,
    commandAuthor,
    refreshGreeting,
    schedulerTasksLoading,
    schedulerTasksUnavailable,
    startingHomeTask,
    schedulerTaskOptions,
    selectedHomeTaskIds,
    restoreSelectedHomeTaskIds,
    updateSelectedHomeTaskIds,
    fetchSchedulerTaskOptions,
    onSchedulerDropdownVisibleChange,
    startHomeTask,
  }
}
