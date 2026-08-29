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
              :src="getScriptIcon('MaaFW', projectIconUrl)"
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

          <ExtraScriptSection
            v-model:form-data="formData"
            :loading="loading"
            @save="handleFieldSave"
          />

          <NotifyConfigSection :form-data="formData" @save="handleFieldSave" />

          <WebhookManager v-if="userId" mode="user" :script-id="scriptId" :user-id="userId" />
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
import WebhookManager from '@/components/WebhookManager.vue'
import { buildMaaFWAssetUrl, useMaaFWApi } from '@/composables/useMaaFWApi'
import { useScriptApi } from '@/composables/useScriptApi'
import { useUserApi } from '@/composables/useUserApi'
import { isSupportedMaaFWControllerType } from '@/types/script'
import { getScriptIcon, maafwScriptIcon } from '@/utils/scriptIcon'
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
  image.src = maafwScriptIcon
}
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
const isPretaskName = (taskName: string) => taskByName.value.get(taskName)?.entry === 'MXU_PRETASK'
const partitionTaskOrder = (taskNames: string[]) => {
  const uniqueNames = taskNames.filter(
    (taskName, index, values) => values.indexOf(taskName) === index
  )
  return [
    ...uniqueNames.filter(taskName => isPretaskName(taskName)),
    ...uniqueNames.filter(taskName => !isPretaskName(taskName)),
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
  const nextTaskNames = partitionTaskOrder([...pretaskNames, ...template.taskNames])
  const nextTaskNameSet = new Set(nextTaskNames)
  taskSnapshot.value.taskOrder = nextTaskNames
  taskSnapshot.value.taskChecked = Object.fromEntries(
    nextTaskNames.map(taskName => [taskName, true])
  )
  taskSnapshot.value.taskOptions = Object.fromEntries(
    Object.entries(presetSnapshot.taskOptions).filter(([taskName]) => nextTaskNameSet.has(taskName))
  )
  selectedTaskName.value = nextTaskNames[0] || ''
  formData.Task.SelectedPreset = presetName
  showPresetModal.value = false
  await savePresetAndSnapshot()
}

const appendPresetTemplate = async (presetName: string) => {
  const template = presetTemplates.value.find(item => item.preset.name === presetName)
  if (!template) return

  const presetSnapshot = normalizeTaskSnapshot(template.preset.snapshot, previewData.value)
  const existingNames = new Set(taskSnapshot.value.taskOrder)
  const appendedNames = template.taskNames.filter(taskName => !existingNames.has(taskName))
  const nextTaskNames = partitionTaskOrder([...taskSnapshot.value.taskOrder, ...appendedNames])
  const nextTaskNameSet = new Set(nextTaskNames)
  taskSnapshot.value.taskOrder = nextTaskNames
  taskSnapshot.value.taskChecked = Object.fromEntries(
    nextTaskNames.map(taskName => [taskName, true])
  )
  taskSnapshot.value.taskOptions = Object.fromEntries(
    [
      ...Object.entries(taskSnapshot.value.taskOptions),
      ...Object.entries(presetSnapshot.taskOptions),
    ].filter(([taskName]) => nextTaskNameSet.has(taskName))
  )
  selectedTaskName.value = appendedNames[0] || nextTaskNames[0] || ''
  formData.Task.SelectedPreset = ''
  showPresetModal.value = false
  await savePresetAndSnapshot()
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
  const queuedOrder = order.filter(taskName => taskChecked[taskName])
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

const handleFieldSave = async (key: string, value: unknown) => {
  if (isInitializing.value || !userId) return

  await enqueueSave(async () => {
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
    if (!success) throw new Error(`用户配置保存失败: ${key}`)
    logger.info(`用户配置已保存: ${key}`)
  }).catch(error => {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存失败: ${errorMsg}`)
  })
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
      message.error('脚本不存在')
      handleCancel()
      return
    }
    if (script.type !== 'MaaFW') {
      message.error('脚本类型不是 MFW')
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
    message.error('加载脚本信息失败')
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

const loadUserData = async () => {
  try {
    const userResponse = await getUsers(scriptId, userId)

    if (userResponse?.code === 200) {
      const userIndex = userResponse.index.find(index => index.uid === userId)
      const userData = userResponse.data[userId] as Partial<MaaFWUserConfig> | undefined

      if (String(userIndex?.type) === 'MaaFWUserConfig' && userData) {
        applyUserData(userData)
        taskSnapshot.value = normalizeTaskSnapshot(formData.Task.TaskSnapshot, previewData.value)
        await syncControllerResourceSelection()
        formData.Task.TaskSnapshot = JSON.stringify(taskSnapshot.value)
        await nextTick()
        formData.userName = formData.Info.Name || ''
        hasUnsavedChanges.value = false
        isInitializing.value = false
      } else {
        message.error('用户不存在')
        handleCancel()
      }
    } else {
      message.error('获取用户数据失败')
      handleCancel()
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载用户数据失败: ${errorMsg}`)
    message.error('加载用户数据失败')
    isInitializing.value = false
    handleCancel()
  }
}

const reloadInterface = async (showMessage = true) => {
  if (!scriptPath.value) {
    if (showMessage) message.warning('请先在脚本页导入 MFW 项目')
    return
  }

  previewData.value = null
  const data = await previewInterface(scriptPath.value)
  if (data) {
    previewData.value = markRaw(data)
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
