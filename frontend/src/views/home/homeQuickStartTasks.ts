import type { ComboBoxItem } from '@/api'
import type { TaskCreateOut } from '@/api/models/TaskCreateOut'

export interface HomeTaskOption {
  label: string
  value: string
}

interface HomeTaskStartFailure {
  taskLabel: string
  reason: string
}

interface HomeTaskStartResult {
  taskId: string
  selectedTaskId: string
  taskLabel: string
}

interface HomeTaskLaunchOutcome {
  started: HomeTaskStartResult[]
  failed: HomeTaskStartFailure[]
}

type StartTaskAction = (taskId: string) => Promise<TaskCreateOut>

export const normalizeHomeQuickStartSelection = (value: unknown): string[] => {
  if (!Array.isArray(value)) return []

  return value.filter(
    (taskId, index, selectedTaskIds) =>
      typeof taskId === 'string' &&
      taskId.length > 0 &&
      !taskId.startsWith('mock-') &&
      selectedTaskIds.indexOf(taskId) === index
  )
}

export const toHomeTaskOptions = (options: ComboBoxItem[]): HomeTaskOption[] => {
  return options
    .filter((option): option is ComboBoxItem & { value: string } => Boolean(option.value))
    .map(option => ({ label: option.label, value: option.value }))
}

export const retainSelectedTaskIds = (
  selectedTaskIds: string[],
  options: HomeTaskOption[]
): string[] => {
  const availableTaskIds = new Set(options.map(option => option.value))
  return normalizeHomeQuickStartSelection(selectedTaskIds).filter(taskId =>
    availableTaskIds.has(taskId)
  )
}

export const taskLabelOf = (taskId: string, options: HomeTaskOption[], fallbackLabel: string) => {
  return options.find(option => option.value === taskId)?.label || fallbackLabel
}

export const launchHomeTasks = async ({
  taskIds,
  options,
  fallbackLabel,
  failureReason,
  startTask,
  onTaskStarted,
}: {
  taskIds: string[]
  options: HomeTaskOption[]
  fallbackLabel: string
  failureReason: string
  startTask: StartTaskAction
  onTaskStarted: (result: HomeTaskStartResult) => void
}): Promise<HomeTaskLaunchOutcome> => {
  const outcome: HomeTaskLaunchOutcome = { started: [], failed: [] }

  for (const taskId of taskIds) {
    const taskLabel = taskLabelOf(taskId, options, fallbackLabel)
    let startedResult: HomeTaskStartResult | undefined
    try {
      const response = await startTask(taskId)
      if (response.code !== 200 || !response.taskId) {
        outcome.failed.push({
          taskLabel,
          reason: response.message || failureReason,
        })
        continue
      }

      startedResult = { taskId: response.taskId, selectedTaskId: taskId, taskLabel }
      outcome.started.push(startedResult)
    } catch (error) {
      outcome.failed.push({
        taskLabel,
        reason: error instanceof Error && error.message ? error.message : failureReason,
      })
    }

    if (startedResult) onTaskStarted(startedResult)
  }

  return outcome
}
