import { computed, ref, watch, type Ref } from 'vue'
import {
  buildPresetAppliedSnapshot,
  selectPresetQueueEntries,
  type MaaFWPresetQueueEntry,
} from '../maafwPresetQueue'
import { maafwMissingTaskName } from '../maafwTaskChanges'
import { isManagedMaaFWTask, withoutManagedMaaFWTasks } from '../maafwManagedTasks'
import {
  buildMaaFWQueueReplacement,
  countMaaFWQueueReplacementImports,
  describeMaaFWQueueSource,
  maafwPasswordFields,
  type MaaFWQueueSource,
} from '../maafwQueueSource'
import type {
  MaaFWInterfacePreviewData,
  MaaFWQueueEntry,
  MaaFWQueuedTaskItem,
  MaaFWTaskInfo,
  MaaFWTaskOptionValue,
  MaaFWTaskSnapshot,
} from '@/types/script'
import { normalizeTaskSnapshot } from './maafwTaskSnapshot'
import type { MaaFWUserFormState } from './useMaaFWUserForm'
import type { MaaFWUserTaskContext } from './useMaaFWUserTaskContext'

interface MaaFWTaskQueueOptions {
  previewData: Ref<MaaFWInterfacePreviewData | null>
  taskSnapshot: Ref<MaaFWTaskSnapshot>
  formData: MaaFWUserFormState
  context: MaaFWUserTaskContext
  /** 返回这次是否真的写进了后端 */
  savePresetAndSnapshot: () => Promise<boolean>
}

type QueueEntryDraft =
  | { id: string; task: MaaFWTaskInfo; missing?: false }
  | { id: string; missing: true; name: string }

/**
 * 用户页任务队列：显示顺序（含 interface 已没有的虚影）、选中项、预设模板、
 * 增删移动与选项修改，以及按当前控制器 / 资源修剪队列。改动都经 `savePresetAndSnapshot` 落盘。
 */
export function useMaaFWTaskQueue({
  previewData,
  taskSnapshot,
  formData,
  context,
  savePresetAndSnapshot,
}: MaaFWTaskQueueOptions) {
  const {
    presetOptions,
    taskByName,
    validTaskNames,
    resolveTaskName,
    getTaskInfoById,
    isPretaskId,
    partitionTaskOrder,
    isTaskActiveForCurrentContext,
    managedTaskEntries,
  } = context

  const selectedTaskId = ref('')
  const showPresetModal = ref(false)

  const queueEntryName = (item: QueueEntryDraft) => (item.missing ? item.name : item.task.name)
  const orderedTasks = computed<MaaFWQueueEntry[]>(() => {
    const hasInterface = Boolean(previewData.value)
    const queuedItems = taskSnapshot.value.taskOrder.flatMap((taskId): QueueEntryDraft[] => {
      const task = getTaskInfoById(taskId)
      if (task) return isTaskActiveForCurrentContext(task) ? [{ id: taskId, task }] : []
      // interface 已经没有这个任务（项目更新改了 name）：留成虚影，由用户自己删
      return hasInterface ? [{ id: taskId, missing: true, name: maafwMissingTaskName(taskId) }] : []
    })
    const copyTotals = new Map<string, number>()
    for (const item of queuedItems) {
      const name = queueEntryName(item)
      copyTotals.set(name, (copyTotals.get(name) || 0) + 1)
    }
    const copyCounters = new Map<string, number>()
    return queuedItems.map(item => {
      const name = queueEntryName(item)
      const copyIndex = (copyCounters.get(name) || 0) + 1
      copyCounters.set(name, copyIndex)
      return { ...item, copyIndex, copyTotal: copyTotals.get(name) || 1 }
    })
  })
  const presentQueuedTasks = computed(() =>
    orderedTasks.value.filter((item): item is MaaFWQueuedTaskItem => !item.missing)
  )
  // 拖拽结束后子组件回传可见部分的新顺序；被 controller/resource 过滤掉的实例
  // 不在队列里显示，要原样接回去，不能被这次重排冲掉。
  const applyQueuedTaskIds = (taskIds: string[]) => {
    const visibleTaskIds = new Set(orderedTasks.value.map(item => item.id))
    const hiddenTaskIds = taskSnapshot.value.taskOrder.filter(taskId => !visibleTaskIds.has(taskId))
    taskSnapshot.value.taskOrder = partitionTaskOrder([...taskIds, ...hiddenTaskIds])
  }
  const activeTasks = computed(() =>
    (previewData.value?.tasks || []).filter(task => isTaskActiveForCurrentContext(task))
  )
  // 已在队列里的任务仍然留在候选中：同一个任务可以再加一份，各自带独立的选项。
  const availableTasks = computed(() =>
    withoutManagedMaaFWTasks(activeTasks.value, managedTaskEntries.value)
  )
  const availableTaskByName = computed(
    () => new Map(availableTasks.value.map(task => [task.name, task] as const))
  )
  const passwordFields = computed(() => maafwPasswordFields(previewData.value?.options || []))
  /** 别处的一份快照（同脚本其他用户的队列）在当前项目下的样子：哪些能导入、哪些失效、几项密码 */
  const describeQueueSnapshot = (
    raw: string | MaaFWTaskSnapshot | Record<string, unknown> | null | undefined
  ): MaaFWQueueSource =>
    describeMaaFWQueueSource(normalizeTaskSnapshot(raw, previewData.value, { keepMissing: true }), {
      taskByName: taskByName.value,
      availableTaskByName: availableTaskByName.value,
      isManagedTask: task => isManagedMaaFWTask(task, managedTaskEntries.value),
      passwordFields: passwordFields.value,
      displayName: task => task.label || task.name,
    })
  /** 「存为模板」要存的项：当前队列里去掉虚影与受管任务 */
  const templateDraftEntries = computed<MaaFWPresetQueueEntry[]>(() =>
    presentQueuedTasks.value
      .filter(item => !isManagedMaaFWTask(item.task, managedTaskEntries.value))
      .map(item => ({ id: item.id, task: item.task }))
  )
  const presetTemplates = computed(() => {
    // 预设里的受管任务（M9A 预设带着启动 / 关闭）不进队列：按「不可用」处理，应用时直接跳过
    const activeTaskByName = availableTaskByName.value
    return presetOptions.value
      .map(preset => {
        const snapshot = normalizeTaskSnapshot(preset.snapshot, previewData.value)
        // 预设里重复的任务是实例 id（`<任务名>__MAS_DUP__presetN`），按实例解析后再判断可用
        const entries = selectPresetQueueEntries(
          snapshot.taskOrder,
          activeTaskByName,
          validTaskNames.value
        )
        return { preset, entries, taskOptions: snapshot.taskOptions }
      })
      .filter(template => template.entries.length > 0)
  })
  const selectedQueuedTask = computed(
    () =>
      orderedTasks.value.find(item => item.id === selectedTaskId.value) ||
      orderedTasks.value[0] ||
      null
  )
  const selectedTask = computed(() => {
    const item = selectedQueuedTask.value
    return item && !item.missing ? item.task : null
  })

  watch(
    orderedTasks,
    items => {
      if (items.length === 0) {
        selectedTaskId.value = ''
        return
      }
      if (!items.some(item => item.id === selectedTaskId.value)) {
        selectedTaskId.value = items[0].id
      }
    },
    { immediate: true }
  )

  const selectTask = (taskId: string) => {
    selectedTaskId.value = taskId
  }

  const persistQueuedSnapshot = async () => {
    taskSnapshot.value.taskOrder = partitionTaskOrder(taskSnapshot.value.taskOrder)
    const queuedTaskIdSet = new Set(taskSnapshot.value.taskOrder)
    taskSnapshot.value.taskChecked = Object.fromEntries(
      taskSnapshot.value.taskOrder.map(taskId => [taskId, true])
    )
    taskSnapshot.value.taskOptions = Object.fromEntries(
      Object.entries(taskSnapshot.value.taskOptions).filter(([taskId]) =>
        queuedTaskIdSet.has(taskId)
      )
    )
    formData.Task.SelectedPreset = ''
    await savePresetAndSnapshot()
  }

  const pruneQueuedTasksForCurrentContext = async (persist = true) => {
    if (!previewData.value) return false

    const activeTaskNames = new Set(activeTasks.value.map(task => task.name))
    const nextOrder = taskSnapshot.value.taskOrder.filter(taskId => {
      const taskName = resolveTaskName(taskId)
      // interface 已经没有的任务不在这里清：它们留成虚影，由用户自己删
      return activeTaskNames.has(taskName) || !validTaskNames.value.has(taskName)
    })
    if (nextOrder.length === taskSnapshot.value.taskOrder.length) return false

    taskSnapshot.value.taskOrder = nextOrder
    selectedTaskId.value = nextOrder[0] || ''
    if (persist) {
      await persistQueuedSnapshot()
    }
    return true
  }

  const syncControllerResourceSelection = async () => {
    if (!previewData.value) return
    await pruneQueuedTasksForCurrentContext(false)
  }

  const applyPresetTemplate = async (presetName: string) => {
    const template = presetTemplates.value.find(item => item.preset.name === presetName)
    if (!template) return

    const nextSnapshot = buildPresetAppliedSnapshot(
      template.entries,
      template.taskOptions,
      taskSnapshot.value.taskOrder,
      isPretaskId
    )
    taskSnapshot.value.taskOrder = nextSnapshot.taskOrder
    taskSnapshot.value.taskChecked = nextSnapshot.taskChecked
    taskSnapshot.value.taskOptions = nextSnapshot.taskOptions
    selectedTaskId.value = nextSnapshot.taskOrder[0] || ''
    formData.Task.SelectedPreset = presetName
    showPresetModal.value = false
    await savePresetAndSnapshot()
  }

  /**
   * 用一份别处的快照（其他用户的队列）替换当前队列，语义同套用预设。
   * 写进了后端就返回实际导入的实例数，没写进去返回 null（失败提示由保存路径给出）。
   * `SelectedPreset` 必须写空：快照为空时运行器会按它的名字去找项目 preset。
   */
  const replaceQueueWith = async (
    source: Pick<MaaFWQueueSource, 'entries' | 'taskOptions'>
  ): Promise<number | null> => {
    const importedCount = countMaaFWQueueReplacementImports(source, taskSnapshot.value, isPretaskId)
    const nextSnapshot = buildMaaFWQueueReplacement(
      source,
      taskSnapshot.value,
      isPretaskId,
      passwordFields.value
    )
    taskSnapshot.value.taskOrder = nextSnapshot.taskOrder
    taskSnapshot.value.taskChecked = nextSnapshot.taskChecked
    taskSnapshot.value.taskOptions = nextSnapshot.taskOptions
    selectedTaskId.value = nextSnapshot.taskOrder[0] || ''
    formData.Task.SelectedPreset = ''
    showPresetModal.value = false
    return (await savePresetAndSnapshot()) ? importedCount : null
  }

  const deleteSelectedTask = async () => {
    const taskId = selectedQueuedTask.value?.id
    if (!taskId) return
    await deleteTask(taskId)
  }

  const deleteTask = async (taskId: string) => {
    const nextOrder = taskSnapshot.value.taskOrder.filter(item => item !== taskId)
    taskSnapshot.value.taskOrder = nextOrder
    delete taskSnapshot.value.taskChecked[taskId]
    delete taskSnapshot.value.taskOptions[taskId]
    // 队列行上直接删虚影时，右侧正在看的任务不跟着跳
    if (selectedQueuedTask.value?.id === taskId || !nextOrder.includes(selectedTaskId.value)) {
      selectedTaskId.value = nextOrder[0] || ''
    }
    await persistQueuedSnapshot()
  }

  const ensureTaskOptionMap = (taskId: string) => {
    const existing = taskSnapshot.value.taskOptions[taskId]
    if (existing) return existing

    taskSnapshot.value.taskOptions[taskId] = {}
    return taskSnapshot.value.taskOptions[taskId]
  }

  const handleTaskOptionUpdate = async (
    taskId: string,
    payload: { optionName: string; value: MaaFWTaskOptionValue }
  ) => {
    const options = ensureTaskOptionMap(taskId)
    options[payload.optionName] = payload.value
    formData.Task.SelectedPreset = ''
    await savePresetAndSnapshot()
  }

  const moveTask = async (taskId: string, direction: -1 | 1) => {
    const visibleTaskIds = orderedTasks.value.map(item => item.id)
    const visibleIndex = visibleTaskIds.indexOf(taskId)
    const targetTaskId = visibleTaskIds[visibleIndex + direction]
    if (!targetTaskId) return
    if (isPretaskId(taskId) !== isPretaskId(targetTaskId)) return

    const index = taskSnapshot.value.taskOrder.indexOf(taskId)
    const nextIndex = taskSnapshot.value.taskOrder.indexOf(targetTaskId)
    if (index < 0 || nextIndex < 0) return
    if (nextIndex < 0 || nextIndex >= taskSnapshot.value.taskOrder.length) return

    const order = [...taskSnapshot.value.taskOrder]
    const current = order[index]
    order[index] = order[nextIndex]
    order[nextIndex] = current
    taskSnapshot.value.taskOrder = order
    formData.Task.SelectedPreset = ''
    await savePresetAndSnapshot()
  }

  const handleTaskDragEnd = async () => {
    formData.Task.SelectedPreset = ''
    await persistQueuedSnapshot()
  }

  return {
    selectedTaskId,
    showPresetModal,
    orderedTasks,
    presentQueuedTasks,
    availableTasks,
    presetTemplates,
    selectedQueuedTask,
    selectedTask,
    applyQueuedTaskIds,
    selectTask,
    persistQueuedSnapshot,
    syncControllerResourceSelection,
    applyPresetTemplate,
    passwordFields,
    templateDraftEntries,
    describeQueueSnapshot,
    replaceQueueWith,
    deleteSelectedTask,
    deleteTask,
    ensureTaskOptionMap,
    handleTaskOptionUpdate,
    moveTask,
    handleTaskDragEnd,
  }
}

export type MaaFWTaskQueue = ReturnType<typeof useMaaFWTaskQueue>
