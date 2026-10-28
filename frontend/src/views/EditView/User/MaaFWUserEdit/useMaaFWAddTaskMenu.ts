import { computed, h, ref, watch, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { buildMaaFWTaskInstanceIds } from '@/utils/maafwTaskInstance'
import type { MaaFWInterfacePreviewData, MaaFWTaskInfo, MaaFWTaskSnapshot } from '@/types/script'
import { markMaaFWTasksSeen, resolveMaaFWNewTaskNames } from '../maafwTaskChanges'
import MaaFWNewBadge from './MaaFWNewBadge.vue'
import {
  MAAFW_ADD_TASK_UNGROUPED_KEY,
  buildMaaFWAddTaskMenuGroups,
  maafwAddTaskSearchText,
  type MaaFWAddTaskMenuGroup,
} from './maafwAddTaskMenu'
import type { MaaFWTaskQueue } from './useMaaFWTaskQueue'
import type { MaaFWUserTaskContext } from './useMaaFWUserTaskContext'
import type { AddTaskCascaderOption } from '../../MaaFWFlavor/sectionContracts'

interface MaaFWAddTaskMenuOptions {
  scriptId: string
  previewData: Ref<MaaFWInterfacePreviewData | null>
  taskSnapshot: Ref<MaaFWTaskSnapshot>
  context: MaaFWUserTaskContext
  queue: MaaFWTaskQueue
  /** 用户页加载成功、菜单能用了：这之后露面的 NEW 才算用户见过 */
  ready: Ref<boolean>
}

/**
 * 「添加任务」级联菜单：按 interface 分组组织候选任务，给用户没见过的任务标 NEW，
 * 选中后按 repeat_count 加入队列并落盘。
 */
export function useMaaFWAddTaskMenu({
  scriptId,
  previewData,
  taskSnapshot,
  context,
  queue,
  ready,
}: MaaFWAddTaskMenuOptions) {
  const { t } = useI18n()
  const { taskByName, partitionTaskOrder, isManagedTaskId, isUnselectableTaskId, getDisplayName } =
    context
  const { availableTasks, selectedTaskId, ensureTaskOptionMap, persistQueuedSnapshot } = queue

  const addTaskCascaderValue = ref<string[]>([])

  // PI v2：任务写了几个分组就出现在几个分组里（分组是归属关系，不是路径）
  const addTaskMenuGroups = computed(() =>
    buildMaaFWAddTaskMenuGroups(availableTasks.value, previewData.value?.groups || []).map(group =>
      group.key === MAAFW_ADD_TASK_UNGROUPED_KEY
        ? { ...group, label: t('core.edit.ungrouped') }
        : group
    )
  )
  // 用户没见过的任务（项目更新新增或改了 name）：在「添加任务」里标 NEW，只标这一次（加进队列的当场消掉）
  const newTaskNames = ref<ReadonlySet<string>>(new Set())
  watch(previewData, data => {
    if (!data) return
    newTaskNames.value = resolveMaaFWNewTaskNames(
      scriptId,
      data.tasks.map(task => task.name)
    )
  })
  const isNewTask = (task: MaaFWTaskInfo) => newTaskNames.value.has(task.name)
  const hasNewTasks = computed(() => availableTasks.value.some(isNewTask))
  // 页面加载成功后，菜单里露了面的 NEW 就记成见过：这次照常标，下次进来不再标。
  // 加载失败离页、或当前资源 / 控制器下不在菜单里的任务没露面，不算见过
  watch(
    [ready, () => availableTasks.value.filter(isNewTask).map(task => task.name)],
    ([isReady, names]) => {
      if (isReady) markMaaFWTasksSeen(scriptId, names)
    }
  )

  /** 选项文字后面挂 NEW 标签（任务）或一个点（含新任务的分组） */
  const markedLabel = (text: string, mark: 'badge' | 'dot' | null) =>
    mark
      ? h('span', { style: { display: 'inline-flex', alignItems: 'center', gap: '6px' } }, [
          text,
          h(MaaFWNewBadge, { dot: mark === 'dot' }),
        ])
      : text

  /** 分组里的任务 → 级联选项；搜索除了显示名，也认任务名与入口名 */
  const toCascaderItems = (tasks: MaaFWTaskInfo[]): AddTaskCascaderOption[] =>
    tasks.map(task => {
      const text = getDisplayName(task)
      return {
        value: `task:${task.name}`,
        label: markedLabel(text, isNewTask(task) ? 'badge' : null),
        searchText: maafwAddTaskSearchText(task, text),
      }
    })

  const addTaskCascaderOptions = computed<AddTaskCascaderOption[]>(() => {
    const groups = addTaskMenuGroups.value
    // interface 没给任务分组时只有一档「未分组」，再套一层级联就成了「左栏一个选项、
    // 右栏一长条」，比直接铺开更难找。这种情况把任务提到顶层，去掉那层壳。
    if (groups.length === 1 && groups[0].key === MAAFW_ADD_TASK_UNGROUPED_KEY) {
      return toCascaderItems(groups[0].tasks)
    }
    return groups.map((group: MaaFWAddTaskMenuGroup) => {
      const text = `${group.label} (${group.tasks.length})`
      return {
        value: `group:${group.key}`,
        label: markedLabel(text, group.tasks.some(isNewTask) ? 'dot' : null),
        searchText: text,
        children: toCascaderItems(group.tasks),
      }
    })
  })

  watch(addTaskMenuGroups, groups => {
    if (groups.length === 0) addTaskCascaderValue.value = []
  })

  const addTaskToQueue = async (taskName: string) => {
    if (
      !taskByName.value.has(taskName) ||
      isManagedTaskId(taskName) ||
      isUnselectableTaskId(taskName)
    ) {
      addTaskCascaderValue.value = []
      return
    }

    // 任务声明了 repeatable / repeat_count 时一次加入 N 份，各自独立（与手动复制同一体系）
    const taskIds = buildMaaFWTaskInstanceIds(
      taskName,
      taskByName.value.get(taskName)?.repeatCount,
      taskSnapshot.value.taskOrder
    )
    taskSnapshot.value.taskOrder = partitionTaskOrder([...taskSnapshot.value.taskOrder, ...taskIds])
    for (const taskId of taskIds) {
      taskSnapshot.value.taskChecked[taskId] = true
      ensureTaskOptionMap(taskId)
    }
    selectedTaskId.value = taskIds[0]
    addTaskCascaderValue.value = []
    if (newTaskNames.value.has(taskName)) {
      newTaskNames.value = new Set([...newTaskNames.value].filter(name => name !== taskName))
    }
    await persistQueuedSnapshot()
  }

  const handleAddTaskCascaderChange = async (value: unknown) => {
    if (!Array.isArray(value)) return
    const selectedValue = value[value.length - 1]
    if (typeof selectedValue !== 'string' || !selectedValue.startsWith('task:')) return
    await addTaskToQueue(selectedValue.slice('task:'.length))
  }

  return {
    addTaskCascaderValue,
    addTaskCascaderOptions,
    hasNewTasks,
    handleAddTaskCascaderChange,
  }
}
