<template>
  <div class="user-edit-container">
    <MaaFWUserEditHeader
      :save-status="saveStatus"
      :save-error-message="saveErrorMessage"
      :script-id="scriptId"
      :script-name="scriptName"
      :is-edit="isEdit"
      @cancel="handleCancel"
    />

    <div class="user-edit-content">
      <a-card class="config-card" :loading="loading">
        <template #title>
          <div class="card-title">
            <img
              :src="projectIconUrl || SCRIPT_LOGOS.MaaFW"
              alt="MaaFW"
              width="22"
              height="22"
              class="title-logo"
              @error="handleProjectIconError"
            />
            <span>{{ scriptName || 'MFW' }}</span>
          </div>
        </template>

        <a-form
          v-if="isEdit"
          ref="formRef"
          :model="formData"
          :rules="rules"
          layout="vertical"
          class="config-form"
        >
          <BasicInfoSection
            :form-data="formData"
            :preset-options="presetOptions"
            :selected-preset-label="selectedPresetLabel"
            :interface-dependent-disabled="interfaceDependentDisabled"
            :account-record-tooltip="accountRecordTooltip"
            @save="handleFieldSave"
            @preset-menu-click="handlePresetMenuClick"
            @mode-change="handleConfigModeChange"
          />

          <a-flex
            class="section-header"
            justify="space-between"
            align="center"
            wrap="wrap"
            gap="small"
          >
            <h3>{{ t('edit.taskQueueConfiguration') }}</h3>
            <a-space>
              <span>{{ t('edit.enableQuickConfiguration') }}</span>
              <a-switch
                :checked="formData.Info.IfQuickConfig"
                :disabled="loading || isInitializing || isSaving"
                :aria-label="t('edit.enableQuickConfiguration')"
                @change="handleQuickConfigChange"
              />
            </a-space>
          </a-flex>
          <TaskQueueSection
            v-if="formData.Info.IfQuickConfig"
            v-model:add-task-cascader-value="addTaskCascaderValue"
            v-model:show-preset-modal="showPresetModal"
            :interface-loading="interfaceLoading"
            :script-path="scriptPath"
            :preview-data="previewData"
            :interface-dependent-disabled="interfaceDependentDisabled"
            :available-tasks="availableTasks"
            :ordered-tasks="orderedTasks"
            :add-task-cascader-options="addTaskCascaderOptions"
            :preset-templates="presetTemplates"
            :task-by-name="taskByName"
            :selected-task="selectedTask"
            :selected-task-id="selectedQueuedTask?.id || ''"
            :task-snapshot="taskSnapshot"
            :effective-controller-name="effectiveControllerName"
            :effective-resource-name="effectiveResourceName"
            @reorder-tasks="applyQueuedTaskIds"
            @reload-interface="reloadInterface"
            @add-task-cascader-change="handleAddTaskCascaderChange"
            @apply-preset-template="applyPresetTemplate"
            @append-preset-template="appendPresetTemplate"
            @select-task="selectTask"
            @move-task="moveTask"
            @task-drag-end="handleTaskDragEnd"
            @task-option-update="handleTaskOptionUpdate"
            @delete-selected-task="deleteSelectedTask"
          />

          <ExtraScriptSection
            v-model:form-data="formData"
            :loading="loading"
            @save="handleFieldSave"
          />

          <UserNotifyConfig
            v-model="formData.Notify"
            :loading="loading"
            :script-id="scriptId"
            :user-id="userId"
            @save="handleFieldSave"
          />
        </a-form>
      </a-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import {
  computed,
  markRaw,
  nextTick,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  shallowRef,
  watch,
} from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { FormInstance, Rule } from 'ant-design-vue/es/form'
import { message, Modal } from 'ant-design-vue'
import ExtraScriptSection from '@/components/ExtraScriptSection.vue'
import UserNotifyConfig from '@/components/UserNotifyConfig.vue'
import { buildMaaFWAssetUrl, useMaaFWApi } from '@/composables/useMaaFWApi'
import { useScriptApi } from '@/composables/useScriptApi'
import { useUserApi } from '@/composables/useUserApi'
import { isSupportedMaaFWControllerType } from '@/types/script'
import { SCRIPT_LOGOS } from '@/utils/scriptLogos'
import { buildMaaFWTaskInstanceId, resolveMaaFWTaskName } from '@/utils/maafwTaskInstance'
import MaaFWUserEditHeader from './MaaFWUserEdit/MaaFWUserEditHeader.vue'
import BasicInfoSection from './MaaFWUserEdit/BasicInfoSection.vue'
import TaskQueueSection from './MaaFWUserEdit/TaskQueueSection.vue'
import type {
  MaaFWGroupInfo,
  MaaFWInterfacePreviewData,
  MaaFWQueuedTaskItem,
  MaaFWScriptConfig,
  MaaFWTaskInfo,
  MaaFWTaskOptionValue,
  MaaFWTaskSnapshot,
  MaaFWUserConfig,
} from '@/types/script'

const { t } = useI18n()

const logger = window.electronAPI.getLogger('MaaFW用户编辑')

type MaaFWDisplayItem = {
  name: string
  label?: string | null
}

type AddTaskCascaderOption = {
  value: string
  label: string
  children?: AddTaskCascaderOption[]
}

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

const router = useRouter()
const route = useRoute()
const { addUser, getUsers, updateUser } = useUserApi()
const { getScript } = useScriptApi()
const { loading: interfaceLoading, previewInterface } = useMaaFWApi()

const formRef = ref<FormInstance>()
const pageLoading = ref(true)
const loading = computed(() => pageLoading.value)
const isInitializing = ref(true)
const isSaving = ref(false)
const hasUnsavedChanges = ref(false)
const saveStatus = ref<'idle' | 'saving' | 'saved' | 'error'>('idle')
const saveErrorMessage = ref('')
let saveStatusTimer: ReturnType<typeof setTimeout> | null = null
let pendingSaves = 0
let saveQueue: Promise<void> = Promise.resolve()

const enqueueSave = async (action: () => Promise<void>) => {
  pendingSaves += 1
  isSaving.value = true
  hasUnsavedChanges.value = true
  saveStatus.value = 'saving'
  const next = saveQueue.catch(() => undefined).then(action)
  saveQueue = next.catch(() => undefined)
  try {
    await next
    saveStatus.value = 'saved'
    saveErrorMessage.value = ''
    if (saveStatusTimer) clearTimeout(saveStatusTimer)
    saveStatusTimer = setTimeout(() => {
      saveStatus.value = 'idle'
      saveStatusTimer = null
    }, 2000)
  } catch (error) {
    saveStatus.value = 'error'
    saveErrorMessage.value = error instanceof Error ? error.message : String(error)
    throw error
  } finally {
    pendingSaves -= 1
    isSaving.value = pendingSaves > 0
    if (pendingSaves === 0 && saveStatus.value === 'saved') {
      hasUnsavedChanges.value = false
    }
  }
}

const scriptId = route.params.scriptId as string
let userId = route.params.userId as string
const isEdit = ref(!!userId)

const scriptName = ref('')
const scriptPath = ref('')
const scriptConfig = ref<MaaFWScriptConfig | null>(null)
const preferAdbController = ref(false)
const previewData = shallowRef<MaaFWInterfacePreviewData | null>(null)

const projectIconUrl = computed(() =>
  buildMaaFWAssetUrl(previewData.value?.path, previewData.value?.project.icon)
)

const handleProjectIconError = (event: Event) => {
  const image = event.currentTarget as HTMLImageElement | null
  if (!image || image.dataset.maafwIconFallbackApplied === 'true') return
  image.dataset.maafwIconFallbackApplied = 'true'
  image.src = SCRIPT_LOGOS.MaaFW
}
const selectedTaskId = ref('')
const addTaskCascaderValue = ref<string[]>([])
const showPresetModal = ref(false)
const taskSnapshot = ref<MaaFWTaskSnapshot>({
  taskOrder: [],
  taskChecked: {},
  taskOptions: {},
})

const getDefaultMaaFWUserData = (): MaaFWUserConfig => ({
  Info: {
    Name: '',
    Status: true,
    Mode: '用户',
    // 快速配置：独立于配置来源的用户级开关（生成模型 MaaFWUserConfig_Info 已含该字段）
    IfQuickConfig: true,
    RemainedDay: -1,
    IfScriptBeforeTask: false,
    ScriptBeforeTask: '',
    IfScriptAfterTask: false,
    ScriptAfterTask: '',
    Notes: '',
    Tag: '',
    Account: '',
    Password: '',
  },
  Task: {
    SelectedPreset: '',
    TaskSnapshot: '{ }',
  },
  Notify: {
    Enabled: false,
    IfSendStatistic: false,
    IfSendMail: false,
    ToAddress: '',
    IfServerChan: false,
    ServerChanKey: '',
  },
  Data: {
    LastProxyDate: '',
    ProxyTimes: 0,
    IfPassCheck: true,
    LastProxyStatus: '未知',
    PeriodTaskRecords: '{ }',
  },
})

const formData = reactive({
  userName: '',
  ...getDefaultMaaFWUserData(),
})

const rules = computed<Record<string, Rule[]>>(() => ({
  userName: [
    { required: true, message: t('edit.enterUsername'), trigger: 'blur' },
    { min: 1, max: 50, message: t('edit.usernameMustBe1'), trigger: 'blur' },
  ],
}))

const accountRecordTooltip =
  '账号 / 密码仅用于本地记录，不会自动传入脚本；需要传参请在下方任务选项中配置'

const controllerOptions = computed(() =>
  (previewData.value?.controllers || []).filter(controller =>
    isSupportedMaaFWControllerType(controller.type)
  )
)
const presetOptions = computed(() => previewData.value?.presets || [])
const taskByName = computed(() => {
  const entries = (previewData.value?.tasks || []).map(task => [task.name, task] as const)
  return new Map<string, MaaFWTaskInfo>(entries)
})
// 队列元素是任务实例 id：同一个任务可以加入多次，首份的 id 就是裸任务名，
// 第二份起是 `<任务名>__MAS_DUP__<随机后缀>`。
const validTaskNames = computed(() => new Set(taskByName.value.keys()))
const resolveTaskName = (taskId: string) => resolveMaaFWTaskName(taskId, validTaskNames.value)
const getTaskInfoById = (taskId: string) => taskByName.value.get(resolveTaskName(taskId))
const isPretaskId = (taskId: string) => getTaskInfoById(taskId)?.entry === 'MXU_PRETASK'
const partitionTaskOrder = (taskIds: string[]) => {
  const uniqueIds = taskIds.filter((taskId, index, values) => values.indexOf(taskId) === index)
  return [
    ...uniqueIds.filter(taskId => isPretaskId(taskId)),
    ...uniqueIds.filter(taskId => !isPretaskId(taskId)),
  ]
}
const getDefaultControllerName = () => {
  if (preferAdbController.value) {
    const adbController = controllerOptions.value.find(controller => controller.type === 'Adb')
    if (adbController) return adbController.name
  }
  return controllerOptions.value[0]?.name || ''
}
const resolveControllerName = (controllerName?: string) => {
  if (controllerName && controllerOptions.value.some(item => item.name === controllerName)) {
    return controllerName
  }
  return getDefaultControllerName()
}
const effectiveControllerName = computed(() => {
  const scriptController = scriptConfig.value?.Info.Controller || ''
  return resolveControllerName(scriptController)
})
const getResourceOptionsByController = (controllerName: string) => {
  const resources = previewData.value?.resources || []
  if (!controllerName) return resources
  return resources.filter(
    resource => resource.controller.length === 0 || resource.controller.includes(controllerName)
  )
}
const resolveResourceName = (
  resourceName?: string,
  controllerName = effectiveControllerName.value
) => {
  const resources = getResourceOptionsByController(controllerName)
  if (resourceName && resources.some(item => item.name === resourceName)) {
    return resourceName
  }
  return resources[0]?.name || ''
}
const effectiveResourceName = computed(() => {
  const scriptResource = scriptConfig.value?.Info.Resource || ''
  return resolveResourceName(scriptResource)
})
const interfaceDependentDisabled = computed(() => interfaceLoading.value || !previewData.value)
const isTaskActiveForCurrentContext = (task: MaaFWTaskInfo) => {
  const controllerName = effectiveControllerName.value
  const resourceName = effectiveResourceName.value
  if (!controllerName || !resourceName) {
    return false
  }
  if (task.controller.length > 0 && !task.controller.includes(controllerName)) {
    return false
  }
  if (task.resource.length > 0 && !task.resource.includes(resourceName)) {
    return false
  }
  return true
}
const orderedTasks = computed<MaaFWQueuedTaskItem[]>(() => {
  const queuedItems = taskSnapshot.value.taskOrder
    .map(taskId => ({ id: taskId, task: getTaskInfoById(taskId) }))
    .filter(
      (item): item is { id: string; task: MaaFWTaskInfo } =>
        item.task !== undefined && isTaskActiveForCurrentContext(item.task)
    )
  const copyTotals = new Map<string, number>()
  for (const item of queuedItems) {
    copyTotals.set(item.task.name, (copyTotals.get(item.task.name) || 0) + 1)
  }
  const copyCounters = new Map<string, number>()
  return queuedItems.map(item => {
    const copyIndex = (copyCounters.get(item.task.name) || 0) + 1
    copyCounters.set(item.task.name, copyIndex)
    return { ...item, copyIndex, copyTotal: copyTotals.get(item.task.name) || 1 }
  })
})
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
const availableTasks = computed(() => activeTasks.value)
const groupByName = computed(() => {
  const entries = (previewData.value?.groups || []).map(group => [group.name, group] as const)
  return new Map<string, MaaFWGroupInfo>(entries)
})
const getGroupDisplayName = (groupName: string) => {
  if (groupName === ADD_TASK_UNGROUPED_KEY) return '未分组'
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
const addTaskCascaderOptions = computed<AddTaskCascaderOption[]>(() =>
  addTaskMenuGroups.value.map(group => ({
    value: `group:${group.key}`,
    label: `${group.label} (${group.taskCount})`,
    children: group.items.map(item =>
      item.type === 'task'
        ? { value: `task:${item.task.name}`, label: item.label }
        : {
            value: item.key,
            label: `${item.label} (${item.taskCount})`,
            children: item.tasks.map(task => ({
              value: `task:${task.name}`,
              label: getDisplayName(task),
            })),
          }
    ),
  }))
)
const presetTemplates = computed(() => {
  const activeTaskNames = new Set(activeTasks.value.map(task => task.name))
  return presetOptions.value
    .map(preset => {
      const snapshot = normalizeTaskSnapshot(preset.snapshot, previewData.value)
      const taskNames = snapshot.taskOrder.filter(taskName => activeTaskNames.has(taskName))
      return { preset, taskNames }
    })
    .filter(template => template.taskNames.length > 0)
})
const selectedQueuedTask = computed(
  () =>
    orderedTasks.value.find(item => item.id === selectedTaskId.value) ||
    orderedTasks.value[0] ||
    null
)
const selectedTask = computed(() => selectedQueuedTask.value?.task || null)
watch(
  () => formData.Info.Name,
  newVal => {
    if (formData.userName !== newVal) {
      formData.userName = newVal || ''
    }
  },
  { immediate: true }
)

watch(
  () => formData.userName,
  newVal => {
    if (formData.Info.Name !== newVal) {
      formData.Info.Name = newVal || ''
    }
  }
)

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

watch(addTaskMenuGroups, groups => {
  if (groups.length === 0) addTaskCascaderValue.value = []
})

const getDisplayName = (item: MaaFWDisplayItem) => {
  return item.label || item.name
}

const selectedPresetLabel = computed(() => {
  const presetName = formData.Task.SelectedPreset
  if (!presetName) return '切换预设'

  const preset = presetOptions.value.find(item => item.name === presetName)
  return preset ? getDisplayName(preset) : '切换预设'
})

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
    Object.entries(taskSnapshot.value.taskOptions).filter(([taskId]) => queuedTaskIdSet.has(taskId))
  )
  formData.Task.SelectedPreset = ''
  await savePresetAndSnapshot()
}

const pruneQueuedTasksForCurrentContext = async (persist = true) => {
  if (!previewData.value) return false

  const activeTaskNames = new Set(activeTasks.value.map(task => task.name))
  const nextOrder = taskSnapshot.value.taskOrder.filter(taskId =>
    activeTaskNames.has(resolveTaskName(taskId))
  )
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

const addTaskToQueue = async (taskName: string) => {
  if (!taskByName.value.has(taskName)) {
    addTaskCascaderValue.value = []
    return
  }

  const taskId = buildMaaFWTaskInstanceId(taskName, new Set(taskSnapshot.value.taskOrder))
  taskSnapshot.value.taskOrder = partitionTaskOrder([...taskSnapshot.value.taskOrder, taskId])
  taskSnapshot.value.taskChecked[taskId] = true
  ensureTaskOptionMap(taskId)
  selectedTaskId.value = taskId
  addTaskCascaderValue.value = []
  await persistQueuedSnapshot()
}

const handleAddTaskCascaderChange = async (value: unknown) => {
  if (!Array.isArray(value)) return
  const selectedValue = value[value.length - 1]
  if (typeof selectedValue !== 'string' || !selectedValue.startsWith('task:')) return
  await addTaskToQueue(selectedValue.slice('task:'.length))
}

const applyPresetTemplate = async (presetName: string) => {
  const template = presetTemplates.value.find(item => item.preset.name === presetName)
  if (!template) return

  const presetSnapshot = normalizeTaskSnapshot(template.preset.snapshot, previewData.value)
  const pretaskIds = taskSnapshot.value.taskOrder.filter(taskId => isPretaskId(taskId))
  const nextTaskIds = partitionTaskOrder([...pretaskIds, ...template.taskNames])
  const nextTaskIdSet = new Set(nextTaskIds)
  taskSnapshot.value.taskOrder = nextTaskIds
  taskSnapshot.value.taskChecked = Object.fromEntries(nextTaskIds.map(taskId => [taskId, true]))
  taskSnapshot.value.taskOptions = Object.fromEntries(
    Object.entries(presetSnapshot.taskOptions).filter(([taskId]) => nextTaskIdSet.has(taskId))
  )
  selectedTaskId.value = nextTaskIds[0] || ''
  formData.Task.SelectedPreset = presetName
  showPresetModal.value = false
  await savePresetAndSnapshot()
}

const appendPresetTemplate = async (presetName: string) => {
  const template = presetTemplates.value.find(item => item.preset.name === presetName)
  if (!template) return

  const presetSnapshot = normalizeTaskSnapshot(template.preset.snapshot, previewData.value)
  // 追加预设只补齐队列里还没有的任务；要再来一份同样的任务，用「添加任务」手动加。
  const existingTaskNames = new Set(
    taskSnapshot.value.taskOrder.map(taskId => resolveTaskName(taskId))
  )
  const appendedNames = template.taskNames.filter(taskName => !existingTaskNames.has(taskName))
  const nextTaskIds = partitionTaskOrder([...taskSnapshot.value.taskOrder, ...appendedNames])
  const nextTaskIdSet = new Set(nextTaskIds)
  taskSnapshot.value.taskOrder = nextTaskIds
  taskSnapshot.value.taskChecked = Object.fromEntries(nextTaskIds.map(taskId => [taskId, true]))
  taskSnapshot.value.taskOptions = Object.fromEntries(
    [
      ...Object.entries(taskSnapshot.value.taskOptions),
      ...Object.entries(presetSnapshot.taskOptions),
    ].filter(([taskId]) => nextTaskIdSet.has(taskId))
  )
  selectedTaskId.value = appendedNames[0] || nextTaskIds[0] || ''
  formData.Task.SelectedPreset = ''
  showPresetModal.value = false
  await savePresetAndSnapshot()
}

const deleteSelectedTask = async () => {
  const taskId = selectedQueuedTask.value?.id
  if (!taskId) return

  const nextOrder = taskSnapshot.value.taskOrder.filter(item => item !== taskId)
  taskSnapshot.value.taskOrder = nextOrder
  delete taskSnapshot.value.taskChecked[taskId]
  delete taskSnapshot.value.taskOptions[taskId]
  selectedTaskId.value = nextOrder[0] || ''
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

const parseTaskSnapshot = (
  raw: string | MaaFWTaskSnapshot | Record<string, unknown> | null | undefined
) => {
  if (!raw) return {}
  if (typeof raw !== 'string') return raw
  try {
    return JSON.parse(raw)
  } catch {
    return {}
  }
}

const normalizeTaskSnapshot = (
  raw: string | MaaFWTaskSnapshot | Record<string, unknown> | null | undefined,
  preview: MaaFWInterfacePreviewData | null
): MaaFWTaskSnapshot => {
  const parsed = parseTaskSnapshot(raw) as Partial<MaaFWTaskSnapshot>
  const tasks = preview?.tasks || []
  const knownTaskNames = new Set(tasks.map(task => task.name))
  const order = Array.isArray(parsed.taskOrder)
    ? parsed.taskOrder.filter(taskId =>
        knownTaskNames.has(resolveMaaFWTaskName(taskId, knownTaskNames))
      )
    : []
  const taskChecked: Record<string, boolean> = Object.fromEntries(
    order.filter(taskId => parsed.taskChecked?.[taskId] !== false).map(taskId => [taskId, true])
  )
  const queuedOrder = order.filter(taskId => taskChecked[taskId])
  const queuedTaskIds = new Set(queuedOrder)

  const taskOptions = Object.fromEntries(
    Object.entries(parsed.taskOptions || {}).filter(([taskId]) => queuedTaskIds.has(taskId))
  )

  return {
    taskOrder: queuedOrder,
    taskChecked,
    taskOptions,
  }
}

const applyUserData = (userData: Partial<MaaFWUserConfig>) => {
  const defaults = getDefaultMaaFWUserData()
  Object.assign(formData.Info, { ...defaults.Info, ...userData.Info })
  Object.assign(formData.Task, { ...defaults.Task, ...userData.Task })
  Object.assign(formData.Notify, { ...defaults.Notify, ...userData.Notify })
  Object.assign(formData.Data, { ...defaults.Data, ...userData.Data })
}

const handleFieldSave = async (key: string, value: unknown) => {
  if (isInitializing.value || !userId) return

  return await enqueueSave(async () => {
    const parts = key.split('.')
    let userData: Record<string, unknown> = {}
    let current = userData

    for (let i = 0; i < parts.length - 1; i++) {
      current[parts[i]] = {}
      current = current[parts[i]] as Record<string, unknown>
    }
    current[parts[parts.length - 1]] = value

    if (key === 'userName') {
      userData = { Info: { Name: value } }
    }

    const success = await updateUser(scriptId, userId, userData)
    if (!success) throw new Error(t('edit.couldNotSaveUser2', { p0: key }))
    logger.info(`用户配置已保存: ${key}`)
  })
    .then(() => true)
    .catch(error => {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`保存失败: ${errorMsg}`)
      return false
    })
}

const handleQuickConfigChange = async (value: boolean) => {
  const previous = formData.Info.IfQuickConfig
  formData.Info.IfQuickConfig = value
  if (!(await handleFieldSave('Info.IfQuickConfig', value))) {
    formData.Info.IfQuickConfig = previous
  }
}

// 配置来源切换：校验 value ∈ options → 赋值 Info.Mode → 保存
const handleConfigModeChange = async (value: boolean | string) => {
  if (typeof value !== 'string' || !['脚本', '用户', '直控'].includes(value)) return
  formData.Info.Mode = value as '脚本' | '用户' | '直控'
  await handleFieldSave('Info.Mode', formData.Info.Mode)
}

const savePresetAndSnapshot = async () => {
  if (isInitializing.value || !userId) return

  const taskSnapshotValue = JSON.stringify(taskSnapshot.value)
  const selectedPreset = formData.Task.SelectedPreset || ''
  formData.Task.TaskSnapshot = taskSnapshotValue
  await enqueueSave(async () => {
    const success = await updateUser(scriptId, userId, {
      Task: {
        SelectedPreset: selectedPreset,
        TaskSnapshot: taskSnapshotValue,
      },
    })
    if (!success) throw new Error('任务预设保存失败')
  }).catch(error => {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存任务预设失败: ${errorMsg}`)
  })
}

const loadScriptInfo = async () => {
  pageLoading.value = true
  try {
    const script = await getScript(scriptId)
    if (!script) {
      message.error(t('edit.scriptDoesNotExist2'))
      handleCancel()
      return
    }
    if (script.type !== 'MaaFW') {
      message.error(t('edit.scriptTypeNotMfw'))
      handleCancel()
      return
    }

    scriptName.value = script.name
    const loadedScriptConfig = script.config as MaaFWScriptConfig
    scriptConfig.value = loadedScriptConfig
    scriptPath.value = loadedScriptConfig.Info?.Path || ''
    preferAdbController.value = Boolean(
      loadedScriptConfig.Emulator?.Id && loadedScriptConfig.Emulator.Id !== '-'
    )
    await reloadInterface(false)

    if (isEdit.value) {
      await loadUserData()
    } else {
      await createUserImmediately()
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载脚本信息失败: ${errorMsg}`)
    message.error(t('edit.couldNotLoadScript2'))
    handleCancel()
  } finally {
    pageLoading.value = false
  }
}

const createUserImmediately = async () => {
  try {
    const result = await addUser(scriptId)
    if (result?.userId) {
      userId = result.userId
      isEdit.value = true
      router.replace({
        name: 'MaaFWUserEdit',
        params: { ...route.params, userId: result.userId },
      })
      await loadUserData()
    } else {
      message.error(t('edit.couldNotCreateUser'))
      handleCancel()
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`创建用户失败: ${errorMsg}`)
    message.error(t('edit.couldNotCreateUser'))
    handleCancel()
  }
}

const loadUserData = async () => {
  try {
    const userResponse = await getUsers(scriptId, userId)

    if (userResponse?.code === 200) {
      const userIndex = userResponse.index.find(index => index.uid === userId)
      const userData = userResponse.data[userId] as Partial<MaaFWUserConfig> | undefined

      if (userIndex?.type === 'MaaFWUserConfig' && userData) {
        applyUserData(userData)
        taskSnapshot.value = normalizeTaskSnapshot(formData.Task.TaskSnapshot, previewData.value)
        await syncControllerResourceSelection()
        formData.Task.TaskSnapshot = JSON.stringify(taskSnapshot.value)
        await nextTick()
        formData.userName = formData.Info.Name || ''
        hasUnsavedChanges.value = false
        isInitializing.value = false
      } else {
        message.error(t('edit.userDoesNotExist'))
        handleCancel()
      }
    } else {
      message.error(t('edit.couldNotFetchUser'))
      handleCancel()
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载用户数据失败: ${errorMsg}`)
    message.error(t('edit.couldNotLoadUser2'))
    isInitializing.value = false
    handleCancel()
  }
}

const reloadInterface = async (showMessage = true) => {
  if (!scriptPath.value) {
    if (showMessage) message.warning(t('edit.importMfwProjectScript'))
    return
  }

  previewData.value = null
  const data = await previewInterface(scriptPath.value)
  if (data) {
    previewData.value = markRaw(data)
    taskSnapshot.value = normalizeTaskSnapshot(taskSnapshot.value, data)
    await syncControllerResourceSelection()
    await nextTick()
    if (showMessage) message.success(t('edit.interfaceLoaded'))
  }
}

const handlePresetMenuClick = async ({ key }: { key: string | number }) => {
  await applyPresetTemplate(String(key))
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

const handleCancel = () => {
  if (isSaving.value || hasUnsavedChanges.value) {
    Modal.confirm({
      title: t('edit.youHaveUnsavedChanges'),
      content: t('edit.leaveWithoutSavingUnsaved'),
      okText: t('edit.leave'),
      cancelText: t('edit.keepEditing'),
      onOk: () => router.push('/scripts'),
    })
    return
  }
  router.push('/scripts')
}

const handleBeforeUnload = (event: BeforeUnloadEvent) => {
  if (!isSaving.value && !hasUnsavedChanges.value) return
  event.preventDefault()
  event.returnValue = ''
}

onMounted(() => {
  window.addEventListener('beforeunload', handleBeforeUnload)
  if (!scriptId) {
    message.error(t('edit.missingScriptIdParameter'))
    handleCancel()
    return
  }

  loadScriptInfo()
})

onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', handleBeforeUnload)
  if (saveStatusTimer) clearTimeout(saveStatusTimer)
})
</script>

<style scoped>
.user-edit-container {
  padding: 32px;
  min-height: 100vh;
  background: var(--ant-color-bg-layout);
}

.user-edit-content {
  max-width: 1400px;
  margin: 0 auto;
}

.config-card {
  border-radius: 12px;
  border: 1px solid var(--ant-color-border-secondary);
}

.config-card :deep(.ant-card-body) {
  padding: 24px;
}

.card-title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.title-logo {
  width: 22px;
  height: 22px;
  object-fit: contain;
}

@media (max-width: 768px) {
  .user-edit-container {
    padding: 16px;
  }
}
</style>
