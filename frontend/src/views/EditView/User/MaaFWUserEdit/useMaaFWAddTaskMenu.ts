import { computed, h, ref, watch, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { buildMaaFWTaskInstanceIds } from '@/utils/maafwTaskInstance'
import type {
  MaaFWGroupInfo,
  MaaFWInterfacePreviewData,
  MaaFWTaskInfo,
  MaaFWTaskSnapshot,
} from '@/types/script'
import { markMaaFWTasksSeen, resolveMaaFWNewTaskNames } from '../maafwTaskChanges'
import MaaFWNewBadge from './MaaFWNewBadge.vue'
import type { MaaFWTaskQueue } from './useMaaFWTaskQueue'
import type { MaaFWUserTaskContext } from './useMaaFWUserTaskContext'
import type { AddTaskCascaderOption } from '../../MaaFWFlavor/sectionContracts'

type AddTaskSecondLevelItem =
  | { type: 'task'; key: string; label: string; task: MaaFWTaskInfo }
  | { type: 'group'; key: string; label: string; taskCount: number; tasks: MaaFWTaskInfo[] }

type AddTaskMenuGroup = {
  key: string
  label: string
  taskCount: number
  items: AddTaskSecondLevelItem[]
}

const ADD_TASK_UNGROUPED_KEY = '__ungrouped__'

interface MaaFWAddTaskMenuOptions {
  scriptId: string
  previewData: Ref<MaaFWInterfacePreviewData | null>
  taskSnapshot: Ref<MaaFWTaskSnapshot>
  context: MaaFWUserTaskContext
  queue: MaaFWTaskQueue
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
}: MaaFWAddTaskMenuOptions) {
  const { t } = useI18n()
  const { taskByName, partitionTaskOrder, isManagedTaskId, getDisplayName } = context
  const { availableTasks, selectedTaskId, ensureTaskOptionMap, persistQueuedSnapshot } = queue

  const addTaskCascaderValue = ref<string[]>([])

  const groupByName = computed(() => {
    const entries = (previewData.value?.groups || []).map(group => [group.name, group] as const)
    return new Map<string, MaaFWGroupInfo>(entries)
  })
  const getGroupDisplayName = (groupName: string) => {
    if (groupName === ADD_TASK_UNGROUPED_KEY) return t('edit.ungrouped')
    const group = groupByName.value.get(groupName)
    return group?.label || groupName
  }
  const getGroupPathDisplayName = (groupNames: string[]) =>
    groupNames.map(groupName => getGroupDisplayName(groupName)).join(' / ')
  const ensureAddTaskMenuGroup = (groupMap: Map<string, AddTaskMenuGroup>, groupKey: string) => {
    const existing = groupMap.get(groupKey)
    if (existing) return existing
    const group: AddTaskMenuGroup = {
      key: groupKey,
      label: getGroupDisplayName(groupKey),
      taskCount: 0,
      items: [],
    }
    groupMap.set(groupKey, group)
    return group
  }
  const addTaskMenuGroups = computed(() => {
    const groupMap = new Map<string, AddTaskMenuGroup>()
    for (const group of previewData.value?.groups || []) {
      groupMap.set(group.name, {
        key: group.name,
        label: getDisplayName(group),
        taskCount: 0,
        items: [],
      })
    }

    for (const task of availableTasks.value) {
      const taskGroups = task.group.filter(group => group.trim())
      const firstGroupKey = taskGroups[0] || ADD_TASK_UNGROUPED_KEY
      const group = ensureAddTaskMenuGroup(groupMap, firstGroupKey)
      group.taskCount += 1

      if (taskGroups.length <= 1) {
        group.items.push({
          type: 'task',
          key: `task:${task.name}`,
          label: getDisplayName(task),
          task,
        })
        continue
      }

      const secondGroupNames = taskGroups.slice(1)
      const secondGroupKey = `group:${secondGroupNames.join('/')}`
      const existing = group.items.find(
        (item): item is Extract<AddTaskSecondLevelItem, { type: 'group' }> =>
          item.type === 'group' && item.key === secondGroupKey
      )
      if (existing) {
        existing.taskCount += 1
        existing.tasks.push(task)
        continue
      }

      group.items.push({
        type: 'group',
        key: secondGroupKey,
        label: getGroupPathDisplayName(secondGroupNames),
        taskCount: 1,
        tasks: [task],
      })
    }

    return Array.from(groupMap.values()).filter(group => group.taskCount > 0)
  })
  // 用户没见过的任务（项目更新新增或改了 name）：在「添加任务」里标 NEW，加进队列后消掉
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

  /** 选项文字后面挂 NEW 标签（任务）或一个点（含新任务的分组） */
  const markedOption = (
    text: string,
    mark: 'badge' | 'dot' | null
  ): Pick<AddTaskCascaderOption, 'label' | 'searchText'> => ({
    label: mark
      ? h('span', { style: { display: 'inline-flex', alignItems: 'center', gap: '6px' } }, [
          text,
          h(MaaFWNewBadge, { dot: mark === 'dot' }),
        ])
      : text,
    searchText: text,
  })

  /** 分组里的项 → 级联选项：任务直接可选，二级分组再展开一层 */
  const toCascaderItems = (items: AddTaskMenuGroup['items']): AddTaskCascaderOption[] =>
    items.map(item =>
      item.type === 'task'
        ? {
            value: `task:${item.task.name}`,
            ...markedOption(item.label, isNewTask(item.task) ? 'badge' : null),
          }
        : {
            value: item.key,
            ...markedOption(
              `${item.label} (${item.taskCount})`,
              item.tasks.some(isNewTask) ? 'dot' : null
            ),
            children: item.tasks.map(task => ({
              value: `task:${task.name}`,
              ...markedOption(getDisplayName(task), isNewTask(task) ? 'badge' : null),
            })),
          }
    )

  const menuGroupHasNewTask = (group: AddTaskMenuGroup) =>
    group.items.some(item =>
      item.type === 'task' ? isNewTask(item.task) : item.tasks.some(isNewTask)
    )

  const addTaskCascaderOptions = computed<AddTaskCascaderOption[]>(() => {
    const groups = addTaskMenuGroups.value
    // interface 没给任务分组时只有一档「未分组」，再套一层级联就成了「左栏一个选项、
    // 右栏一长条」，比直接铺开更难找。这种情况把任务提到顶层，去掉那层壳。
    if (groups.length === 1 && groups[0].key === ADD_TASK_UNGROUPED_KEY) {
      return toCascaderItems(groups[0].items)
    }
    return groups.map(group => ({
      value: `group:${group.key}`,
      ...markedOption(
        `${group.label} (${group.taskCount})`,
        menuGroupHasNewTask(group) ? 'dot' : null
      ),
      children: toCascaderItems(group.items),
    }))
  })

  watch(addTaskMenuGroups, groups => {
    if (groups.length === 0) addTaskCascaderValue.value = []
  })

  const addTaskToQueue = async (taskName: string) => {
    if (!taskByName.value.has(taskName) || isManagedTaskId(taskName)) {
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
      markMaaFWTasksSeen(scriptId, [taskName])
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
