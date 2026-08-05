<template>
  <div class="user-edit-container">
    <MaaFWUserEditHeader
      :save-status="saveStatus"
      :save-error-message="saveErrorMessage"
      @cancel="handleCancel"
    />

    <div class="user-edit-content">
      <a-card class="config-card" :loading="loading">
        <template #title>
          <div class="card-title">
            <img
              :src="getScriptIcon(scriptType, scriptIconUrl)"
              :alt="scriptType || 'MaaFramework'"
              width="22"
              height="22"
              class="title-logo"
              @error="event => handleScriptIconError(event, scriptType)"
            />
            <span>{{ scriptName || 'MaaFramework 项目' }}</span>
          </div>
        </template>

        <MaaFWConfigurationReusePanel
          v-if="!isEdit"
          :script-id="scriptId"
          mode="new-user"
          :allow-external="true"
          :default-source-path="scriptPath"
          :existing-users="existingUsers"
          @blank="createUserImmediately"
          @applied="handleReuseApplied"
        />

        <a-form
          v-else
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
          />

          <TaskQueueSection
            v-model:queued-task-names="queuedTaskNames"
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
            :task-snapshot="taskSnapshot"
            :effective-controller-name="effectiveControllerName"
            :effective-resource-name="effectiveResourceName"
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

          <ExtraScriptSection :form-data="formData" :loading="loading" @save="handleFieldSave" />

          <NotifyConfigSection :form-data="formData" @save="handleFieldSave" />
        </a-form>
      </a-card>
    </div>
  </div>
</template>

<script setup lang="ts">
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
import { useMaaFWApi } from '@/composables/useMaaFWApi'
import type { MaaFWConfigurationApplyResult } from '@/composables/useMaaFWConfigurationReuse'
import { useScriptRegistryApi } from '@/composables/useScriptRegistryApi'
import MaaFWConfigurationReusePanel from '@/components/MaaFWConfigurationReusePanel.vue'
import { getScriptIcon, handleScriptIconError } from '@/utils/scriptRegistry'
import MaaFWUserEditHeader from './MaaFWUserEdit/MaaFWUserEditHeader.vue'
import BasicInfoSection from './MaaFWUserEdit/BasicInfoSection.vue'
import TaskQueueSection from './MaaFWUserEdit/TaskQueueSection.vue'
import NotifyConfigSection from './MaaFWUserEdit/NotifyConfigSection.vue'
import type {
  MaaFWGroupInfo,
  MaaFWInterfacePreviewData,
  MaaFWScriptConfig,
  MaaFWTaskInfo,
  MaaFWTaskOptionValue,
  MaaFWTaskSnapshot,
  MaaFWUserConfig,
} from '@/types/script'
import type { ScriptUserRecord } from '@/types/scriptRegistry'

const logger = window.electronAPI.getLogger('MaaFW用户编辑')

type MaaFWDisplayItem = {
  name: string
  label?: string | null
}

type AddTaskSecondLevelItem =
  | {
      type: 'task'
      key: string
      label: string
      task: MaaFWTaskInfo
    }
  | {
      type: 'group'
      key: string
      label: string
      taskCount: number
      tasks: MaaFWTaskInfo[]
    }

type AddTaskMenuGroup = {
  key: string
  label: string
  taskCount: number
  items: AddTaskSecondLevelItem[]
}

type AddTaskCascaderOption = {
  value: string
  label: string
  children?: AddTaskCascaderOption[]
}

const ADD_TASK_UNGROUPED_KEY = '__ungrouped__'

const router = useRouter()
const route = useRoute()
const registryApi = useScriptRegistryApi()
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
const pendingSave = ref<{ key: string; value: unknown } | null>(null)

const scriptId = route.params.scriptId as string
let userId = route.params.userId as string
const isEdit = ref(!!userId)

const scriptName = ref('')
const scriptType = ref('')
const scriptIconUrl = ref<string | null>(null)
const scriptPath = ref('')
const scriptConfig = ref<MaaFWScriptConfig | null>(null)
const existingUsers = ref<ScriptUserRecord[]>([])
const preferAdbController = ref(false)
const previewData = shallowRef<MaaFWInterfacePreviewData | null>(null)
const selectedTaskName = ref('')
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
    CustomWebhooks: [],
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
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 1, max: 50, message: '用户名长度应在1-50个字符之间', trigger: 'blur' },
  ],
}))

const accountRecordTooltip =
  '账号 / 密码仅用于本地记录，不会自动传入脚本；需要传参请在下方任务选项中配置'

const MAAFW_DIRECT_CONTROLLER_TYPES = ['Adb', 'Win32'] as const

type MaaFWDirectControllerType = (typeof MAAFW_DIRECT_CONTROLLER_TYPES)[number]

const isDirectControllerType = (
  controllerType?: string | null
): controllerType is MaaFWDirectControllerType =>
  MAAFW_DIRECT_CONTROLLER_TYPES.includes(controllerType as MaaFWDirectControllerType)

const controllerOptions = computed(() => previewData.value?.controllers || [])
const directControllerOptions = computed(() =>
  controllerOptions.value.filter(controller => isDirectControllerType(controller.type))
)
// 预设 schema（MaaFWPresetInfo）不携带 controller/resource 约束，直接展示全部预设
const presetOptions = computed(() => previewData.value?.presets || [])
const taskByName = computed(() => {
  const entries = (previewData.value?.tasks || []).map(task => [task.name, task] as const)
  return new Map<string, MaaFWTaskInfo>(entries)
})
const isPretaskName = (taskName: string) => taskByName.value.get(taskName)?.entry === 'MXU_PRETASK'
const partitionTaskOrder = (taskNames: string[]) => [
  ...taskNames.filter(taskName => isPretaskName(taskName)),
  ...taskNames.filter(taskName => !isPretaskName(taskName)),
]
const getDisplayName = (item: MaaFWDisplayItem) => {
  return item.label || item.name
}
const getDefaultControllerName = () => {
  if (preferAdbController.value) {
    const adbController = directControllerOptions.value.find(
      controller => controller.type === 'Adb'
    )
    if (adbController) return adbController.name
  }
  return directControllerOptions.value[0]?.name || ''
}
const resolveControllerName = (controllerName?: string) => {
  if (controllerName && directControllerOptions.value.some(item => item.name === controllerName)) {
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
const orderedTasks = computed(() => {
  const tasks = taskByName.value
  return taskSnapshot.value.taskOrder
    .map(taskName => tasks.get(taskName))
    .filter(
      (task): task is MaaFWTaskInfo => task !== undefined && isTaskActiveForCurrentContext(task)
    )
})
const queuedTaskNames = computed({
  get: () => orderedTasks.value.map(task => task.name),
  set: value => {
    const visibleTaskNames = new Set(orderedTasks.value.map(task => task.name))
    const hiddenTaskNames = taskSnapshot.value.taskOrder.filter(
      taskName => !visibleTaskNames.has(taskName)
    )
    taskSnapshot.value.taskOrder = partitionTaskOrder([...value, ...hiddenTaskNames])
  },
})
const activeTasks = computed(() =>
  (previewData.value?.tasks || []).filter(task => isTaskActiveForCurrentContext(task))
)
const availableTasks = computed(() => {
  const queuedTaskNames = new Set(taskSnapshot.value.taskOrder)
  return activeTasks.value.filter(task => !queuedTaskNames.has(task.name))
})
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
const addTaskMenuGroups = computed<AddTaskMenuGroup[]>(() => {
  const groupMap = new Map<string, AddTaskMenuGroup>()
  for (const group of previewData.value?.groups || []) {
    groupMap.set(group.name, {
      key: group.name,
      label: getGroupDisplayName(group.name),
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
const addTaskCascaderOptions = computed<AddTaskCascaderOption[]>(() => {
  return addTaskMenuGroups.value.map(group => ({
    value: `group:${group.key}`,
    label: `${group.label} (${group.taskCount})`,
    children: group.items.map(item => {
      if (item.type === 'task') {
        return {
          value: `task:${item.task.name}`,
          label: item.label,
        }
      }
      return {
        value: item.key,
        label: `${item.label} (${item.taskCount})`,
        children: item.tasks.map(task => ({
          value: `task:${task.name}`,
          label: getDisplayName(task),
        })),
      }
    }),
  }))
})
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
const selectedTask = computed(() => {
  return (
    orderedTasks.value.find(task => task.name === selectedTaskName.value) ||
    orderedTasks.value[0] ||
    null
  )
})
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
  tasks => {
    if (tasks.length === 0) {
      selectedTaskName.value = ''
      return
    }
    if (!tasks.some(task => task.name === selectedTaskName.value)) {
      selectedTaskName.value = tasks[0].name
    }
  },
  { immediate: true }
)

watch(addTaskMenuGroups, groups => {
  if (groups.length === 0) {
    addTaskCascaderValue.value = []
  }
})

const selectedPresetLabel = computed(() => {
  const presetName = formData.Task.SelectedPreset
  if (!presetName) return '切换预设'

  const preset = presetOptions.value.find(item => item.name === presetName)
  return preset ? getDisplayName(preset) : '切换预设'
})

const selectTask = (taskName: string) => {
  selectedTaskName.value = taskName
}

const persistQueuedSnapshot = async () => {
  taskSnapshot.value.taskOrder = partitionTaskOrder(taskSnapshot.value.taskOrder)
  const queuedTaskNames = new Set(taskSnapshot.value.taskOrder)
  taskSnapshot.value.taskChecked = Object.fromEntries(
    taskSnapshot.value.taskOrder.map(taskName => [taskName, true])
  )
  taskSnapshot.value.taskOptions = Object.fromEntries(
    Object.entries(taskSnapshot.value.taskOptions).filter(([taskName]) =>
      queuedTaskNames.has(taskName)
    )
  )
  formData.Task.SelectedPreset = ''
  await savePresetAndSnapshot()
}

const pruneQueuedTasksForCurrentContext = async (persist = true) => {
  if (!previewData.value) return false

  const activeTaskNames = new Set(activeTasks.value.map(task => task.name))
  const nextOrder = taskSnapshot.value.taskOrder.filter(taskName => activeTaskNames.has(taskName))
  if (nextOrder.length === taskSnapshot.value.taskOrder.length) return false

  taskSnapshot.value.taskOrder = nextOrder
  selectedTaskName.value = nextOrder[0] || ''
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
  if (!taskByName.value.has(taskName) || taskSnapshot.value.taskOrder.includes(taskName)) {
    addTaskCascaderValue.value = []
    return
  }

  taskSnapshot.value.taskOrder = partitionTaskOrder([...taskSnapshot.value.taskOrder, taskName])
  taskSnapshot.value.taskChecked[taskName] = true
  ensureTaskOptionMap(taskName)
  selectedTaskName.value = taskName
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
  const pretaskNames = taskSnapshot.value.taskOrder.filter(taskName => isPretaskName(taskName))
  const nextTaskNames = [...pretaskNames, ...template.taskNames]
  const nextTaskNameSet = new Set(nextTaskNames)
  taskSnapshot.value.taskOrder = nextTaskNames
  taskSnapshot.value.taskChecked = Object.fromEntries(
    nextTaskNames.map(taskName => [taskName, true])
  )
  taskSnapshot.value.taskOptions = Object.fromEntries([
    ...Object.entries(taskSnapshot.value.taskOptions).filter(([taskName]) =>
      pretaskNames.includes(taskName)
    ),
    ...Object.entries(presetSnapshot.taskOptions).filter(([taskName]) =>
      nextTaskNameSet.has(taskName)
    ),
  ])
  selectedTaskName.value = nextTaskNames[0] || ''
  formData.Task.SelectedPreset = presetName
  showPresetModal.value = false
  await savePresetAndSnapshot()
}

const appendPresetTemplate = async (presetName: string) => {
  const template = presetTemplates.value.find(item => item.preset.name === presetName)
  if (!template) return

  const existingTaskNames = new Set(taskSnapshot.value.taskOrder)
  const nextTaskNames = template.taskNames.filter(taskName => !existingTaskNames.has(taskName))
  if (nextTaskNames.length === 0) {
    message.info('预设中的任务已在队列中')
    showPresetModal.value = false
    return
  }

  for (const taskName of nextTaskNames) {
    taskSnapshot.value.taskChecked[taskName] = true
    ensureTaskOptionMap(taskName)
  }
  taskSnapshot.value.taskOrder = [...taskSnapshot.value.taskOrder, ...nextTaskNames]
  selectedTaskName.value = nextTaskNames[0] || selectedTaskName.value
  formData.Task.SelectedPreset = ''
  showPresetModal.value = false
  await persistQueuedSnapshot()
}

const deleteSelectedTask = async () => {
  const taskName = selectedTask.value?.name
  if (!taskName) return

  const nextOrder = taskSnapshot.value.taskOrder.filter(item => item !== taskName)
  taskSnapshot.value.taskOrder = nextOrder
  delete taskSnapshot.value.taskChecked[taskName]
  delete taskSnapshot.value.taskOptions[taskName]
  selectedTaskName.value = nextOrder[0] || ''
  await persistQueuedSnapshot()
}

const ensureTaskOptionMap = (taskName: string) => {
  const existing = taskSnapshot.value.taskOptions[taskName]
  if (existing) return existing

  taskSnapshot.value.taskOptions[taskName] = {}
  return taskSnapshot.value.taskOptions[taskName]
}

const handleTaskOptionUpdate = async (
  taskName: string,
  payload: { optionName: string; value: MaaFWTaskOptionValue }
) => {
  const options = ensureTaskOptionMap(taskName)
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
  const taskNames = tasks.map(task => task.name)
  const order = Array.isArray(parsed.taskOrder)
    ? parsed.taskOrder.filter(taskName => taskNames.includes(taskName))
    : []
  const taskChecked: Record<string, boolean> = Object.fromEntries(
    order
      .filter(taskName => parsed.taskChecked?.[taskName] !== false)
      .map(taskName => [taskName, true])
  )
  const taskMap = new Map(tasks.map(task => [task.name, task] as const))
  const checkedOrder = order.filter(taskName => taskChecked[taskName])
  const queuedOrder = [
    ...checkedOrder.filter(taskName => taskMap.get(taskName)?.entry === 'MXU_PRETASK'),
    ...checkedOrder.filter(taskName => taskMap.get(taskName)?.entry !== 'MXU_PRETASK'),
  ]
  const queuedTaskNames = new Set(queuedOrder)

  const taskOptions = Object.fromEntries(
    Object.entries(parsed.taskOptions || {}).filter(([taskName]) => queuedTaskNames.has(taskName))
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

const setSaveStatus = (status: 'idle' | 'saving' | 'saved' | 'error', errorMessage = '') => {
  if (saveStatusTimer) {
    clearTimeout(saveStatusTimer)
    saveStatusTimer = null
  }
  saveStatus.value = status
  saveErrorMessage.value = errorMessage
  if (status === 'saved') {
    saveStatusTimer = setTimeout(() => {
      saveStatus.value = 'idle'
      saveStatusTimer = null
    }, 2000)
  }
}

const handleFieldSave = async (key: string, value: unknown) => {
  if (isInitializing.value || !userId) return
  hasUnsavedChanges.value = true
  setSaveStatus('saving')
  if (isSaving.value) {
    pendingSave.value = { key, value }
    return
  }

  isSaving.value = true
  try {
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

    await registryApi.updateUser(scriptId, userId, userData)
    hasUnsavedChanges.value = false
    setSaveStatus('saved')
    logger.info(`用户配置已保存: ${key}`)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    setSaveStatus('error', errorMsg || '保存失败，请重试')
    logger.error(`保存失败: ${errorMsg}`)
  } finally {
    isSaving.value = false
    if (pendingSave.value) {
      const pending = pendingSave.value
      pendingSave.value = null
      void handleFieldSave(pending.key, pending.value)
    }
  }
}

const savePresetAndSnapshot = async () => {
  if (isInitializing.value || !userId) return
  hasUnsavedChanges.value = true
  setSaveStatus('saving')
  if (isSaving.value) return

  isSaving.value = true
  try {
    formData.Task.TaskSnapshot = JSON.stringify(taskSnapshot.value)
    await registryApi.updateUser(scriptId, userId, {
      Task: {
        SelectedPreset: formData.Task.SelectedPreset || '',
        TaskSnapshot: formData.Task.TaskSnapshot,
      },
    })
    hasUnsavedChanges.value = false
    setSaveStatus('saved')
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    setSaveStatus('error', errorMsg || '保存任务预设失败，请重试')
    logger.error(`保存任务预设失败: ${errorMsg}`)
  } finally {
    isSaving.value = false
  }
}

const loadScriptInfo = async () => {
  pageLoading.value = true
  try {
    const script = (await registryApi.getScripts(scriptId))[0]
    if (!script) {
      message.error('脚本不存在')
      handleCancel()
      return
    }

    scriptName.value = script.name
    scriptType.value = script.type
    scriptIconUrl.value = script.icon_url ?? null
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
      existingUsers.value = await registryApi.getUsers(scriptId)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载脚本信息失败: ${errorMsg}`)
    message.error('加载脚本信息失败')
    handleCancel()
  } finally {
    pageLoading.value = false
  }
}

const createUserImmediately = async () => {
  try {
    const result = await registryApi.addUser(scriptId)
    if (result?.id) {
      userId = result.id
      isEdit.value = true
      router.replace({
        name: 'MaaFWUserEdit',
        params: { ...route.params, userId: result.id },
      })
      await loadUserData()
    } else {
      message.error('创建用户失败')
      handleCancel()
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`创建用户失败: ${errorMsg}`)
    message.error('创建用户失败')
    handleCancel()
  }
}

const handleReuseApplied = async (result: MaaFWConfigurationApplyResult) => {
  userId = result.createdUser.id
  isEdit.value = true
  router.replace({
    name: 'MaaFWUserEdit',
    params: { ...route.params, userId },
  })
  await loadUserData()
}

const loadUserData = async () => {
  try {
    const userRecord = (await registryApi.getUsers(scriptId, userId))[0]
    const userData = userRecord?.config as Partial<MaaFWUserConfig> | undefined

    if (!userData) {
      message.error('用户不存在')
      handleCancel()
      return
    }

    applyUserData(userData)
    taskSnapshot.value = normalizeTaskSnapshot(formData.Task.TaskSnapshot, previewData.value)
    await syncControllerResourceSelection()
    formData.Task.TaskSnapshot = JSON.stringify(taskSnapshot.value)
    await nextTick()
    formData.userName = formData.Info.Name || ''
    hasUnsavedChanges.value = false
    setSaveStatus('idle')
    isInitializing.value = false
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载用户数据失败: ${errorMsg}`)
    message.error('加载用户数据失败')
  }
}

const reloadInterface = async (showMessage = true) => {
  if (!scriptPath.value) {
    if (showMessage) message.warning('请先在脚本页设置 MaaFramework 项目目录')
    return
  }

  const data = await previewInterface(scriptPath.value)
  if (data) {
    previewData.value = markRaw(data)
    const project = data.project
    const interfaceProjectName = [project.title, project.label, project.name]
      .map(value => (typeof value === 'string' ? value.trim() : ''))
      .find(Boolean)
    if (interfaceProjectName) scriptName.value = interfaceProjectName
    taskSnapshot.value = normalizeTaskSnapshot(taskSnapshot.value, data)
    await syncControllerResourceSelection()
    await nextTick()
    if (showMessage) message.success('interface 已读取')
  }
}

const handlePresetMenuClick = async ({ key }: { key: string | number }) => {
  await applyPresetTemplate(String(key))
}

const moveTask = async (taskName: string, direction: -1 | 1) => {
  const visibleTaskNames = orderedTasks.value.map(task => task.name)
  const visibleIndex = visibleTaskNames.indexOf(taskName)
  const targetTaskName = visibleTaskNames[visibleIndex + direction]
  if (!targetTaskName) return
  if (isPretaskName(taskName) !== isPretaskName(targetTaskName)) return

  const index = taskSnapshot.value.taskOrder.indexOf(taskName)
  const nextIndex = taskSnapshot.value.taskOrder.indexOf(targetTaskName)
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
      title: '有未保存的更改',
      content: '确定要离开吗？未保存的更改可能会丢失。',
      okText: '离开',
      cancelText: '继续编辑',
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
    message.error('缺少脚本ID参数')
    handleCancel()
    return
  }

  loadScriptInfo()
})

onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', handleBeforeUnload)
  if (saveStatusTimer) {
    clearTimeout(saveStatusTimer)
    saveStatusTimer = null
  }
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
