<template>
  <div class="user-edit-container">
    <div class="user-edit-header">
      <a-breadcrumb class="breadcrumb">
        <a-breadcrumb-item>
          <router-link to="/scripts" class="breadcrumb-link">脚本管理</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          <span class="breadcrumb-current">{{
            isEdit ? '编辑 MaaFramework 用户' : '添加 MaaFramework 用户'
          }}</span>
        </a-breadcrumb-item>
      </a-breadcrumb>

      <a-space>
        <a-button size="large" @click="handleCancel">
          <template #icon>
            <ArrowLeftOutlined />
          </template>
          返回
        </a-button>
      </a-space>
    </div>

    <div class="user-edit-content">
      <a-card class="config-card" :loading="loading">
        <template #title>
          <div class="card-title">
            <img src="@/assets/AUTO-MAS.ico" alt="MaaFramework" class="title-logo" />
            <span>{{ scriptName || 'MaaFramework 项目' }}</span>
          </div>
        </template>

        <a-form
          ref="formRef"
          :model="formData"
          :rules="rules"
          layout="vertical"
          class="config-form"
        >
          <div class="form-section">
            <div class="section-header">
              <h3>基本信息</h3>
            </div>

            <a-row :gutter="24">
              <a-col :span="8">
                <a-form-item name="userName">
                  <template #label>
                    <a-tooltip title="为当前配置设置一个易于识别的名称">
                      <span class="form-label">
                        用户名称
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <a-input
                    v-model:value="formData.userName"
                    placeholder="请输入用户名称"
                    size="large"
                    @blur="handleFieldSave('Info.Name', formData.Info.Name)"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="4">
                <a-form-item label="启用">
                  <a-switch
                    v-model:checked="formData.Info.Status"
                    checked-children="启用"
                    un-checked-children="禁用"
                    @change="handleFieldSave('Info.Status', formData.Info.Status)"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="6">
                <a-form-item label="剩余天数">
                  <a-input-number
                    v-model:value="formData.Info.RemainedDay"
                    :min="-1"
                    :max="9999"
                    size="large"
                    style="width: 100%"
                    @blur="handleFieldSave('Info.RemainedDay', formData.Info.RemainedDay)"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="6">
                <a-form-item label="一键切换预设">
                  <a-dropdown
                    trigger="click"
                    :disabled="interfaceDependentDisabled || presetOptions.length === 0"
                  >
                    <a-button
                      size="large"
                      block
                      class="preset-switch-button"
                      :disabled="interfaceDependentDisabled || presetOptions.length === 0"
                    >
                      <span>{{ selectedPresetLabel }}</span>
                      <DownOutlined />
                    </a-button>
                    <template #overlay>
                      <a-menu
                        :selected-keys="
                          formData.Task.SelectedPreset ? [formData.Task.SelectedPreset] : []
                        "
                        @click="handlePresetMenuClick"
                      >
                        <a-menu-item v-for="item in presetOptions" :key="item.name">
                          {{ getDisplayName(item) }}
                        </a-menu-item>
                      </a-menu>
                    </template>
                  </a-dropdown>
                </a-form-item>
              </a-col>
            </a-row>

            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <a-tooltip :title="accountRecordTooltip">
                      <span class="form-label">
                        账号
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <a-input
                    v-model:value="formData.Info.Account"
                    size="large"
                    placeholder="仅用于本地记录"
                    @blur="handleFieldSave('Info.Account', formData.Info.Account)"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <a-tooltip :title="accountRecordTooltip">
                      <span class="form-label">
                        密码
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <a-input-password
                    v-model:value="formData.Info.Password"
                    size="large"
                    placeholder="仅用于本地记录"
                    @blur="handleFieldSave('Info.Password', formData.Info.Password)"
                  />
                </a-form-item>
              </a-col>
            </a-row>
            <a-alert
              class="account-record-alert"
              type="info"
              show-icon
              :message="accountRecordTooltip"
            />

            <a-form-item label="备注">
              <a-textarea
                v-model:value="formData.Info.Notes"
                :rows="3"
                placeholder="请输入备注"
                @blur="handleFieldSave('Info.Notes', formData.Info.Notes)"
              />
            </a-form-item>
          </div>

          <div class="form-section">
            <div class="section-header section-header-with-action">
              <h3>任务队列配置</h3>
              <a-space>
                <a-button
                  :loading="interfaceLoading"
                  :disabled="!scriptPath"
                  @click="reloadInterface"
                >
                  <template #icon>
                    <FileSearchOutlined />
                  </template>
                  读取 interface
                </a-button>
              </a-space>
            </div>

            <div v-if="interfaceLoading" class="task-loading">
              <a-spin tip="正在读取 interface.json...">
                <a-alert
                  type="info"
                  show-icon
                  message="正在加载 MaaFW 项目接口"
                  description="请稍候，正在解析任务、选项和预设定义"
                />
              </a-spin>
            </div>
            <a-empty
              v-else-if="!previewData"
              description="尚未读取 interface.json"
              class="task-empty"
            />
            <a-row v-else :gutter="24" class="task-editor-layout">
              <a-col :span="12" class="task-list-column">
                <div class="column-header">
                  <span>任务队列</span>
                  <div ref="addTaskMenuRootRef" class="add-task-menu" @click.stop>
                    <a-button
                      type="primary"
                      :disabled="interfaceDependentDisabled || availableTasks.length === 0"
                      @click="toggleAddTaskMenu"
                    >
                      <template #icon>
                        <PlusOutlined />
                      </template>
                      添加任务 ({{ availableTasks.length }})
                    </a-button>
                    <div v-if="addTaskMenuVisible" class="add-task-popup">
                      <div class="add-task-menu-column">
                        <button
                          v-for="group in addTaskMenuGroups"
                          :key="group.key"
                          type="button"
                          class="add-task-menu-item"
                          :class="{
                            'add-task-menu-item-active': group.key === selectedAddTaskGroupKey,
                          }"
                          @click="handleAddTaskGroupClick(group.key)"
                        >
                          <span class="add-task-menu-label">{{ group.label }}</span>
                          <span class="add-task-menu-meta">
                            <span>{{ group.taskCount }}</span>
                            <RightOutlined class="add-task-menu-chevron" />
                          </span>
                        </button>
                      </div>
                      <div v-if="activeAddTaskGroup" class="add-task-menu-column">
                        <button
                          v-for="item in activeAddTaskGroup.items"
                          :key="item.key"
                          type="button"
                          class="add-task-menu-item"
                          :class="{
                            'add-task-menu-item-active': item.key === selectedAddTaskSecondKey,
                          }"
                          @click="handleAddTaskSecondClick(item)"
                        >
                          <span class="add-task-menu-label">{{ item.label }}</span>
                          <span class="add-task-menu-meta">
                            <span v-if="item.type === 'group'">{{ item.taskCount }}</span>
                            <RightOutlined
                              v-if="item.type === 'group'"
                              class="add-task-menu-chevron"
                            />
                          </span>
                        </button>
                      </div>
                      <div v-if="activeAddTaskSecondGroup" class="add-task-menu-column">
                        <button
                          v-for="task in activeAddTaskSecondGroup.tasks"
                          :key="task.name"
                          type="button"
                          class="add-task-menu-item"
                          @click="addTaskToQueue(task.name)"
                        >
                          <span class="add-task-menu-label">{{ getDisplayName(task) }}</span>
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
                <div class="task-list">
                  <div
                    v-if="orderedTasks.length === 0 && presetTemplates.length > 0"
                    class="preset-section"
                  >
                    <div
                      v-for="template in presetTemplates"
                      :key="template.preset.name"
                      class="preset-card"
                    >
                      <div class="preset-card-inner">
                        <div class="preset-header">
                          <div class="preset-icon-wrap">
                            <ThunderboltOutlined class="preset-icon" />
                          </div>
                          <div class="preset-info">
                            <h3 class="preset-name">{{ getDisplayName(template.preset) }}</h3>
                            <MaaFWDescriptionView
                              v-if="template.preset.description"
                              :content="template.preset.description"
                              :base-path="previewData.path"
                              class="preset-desc"
                            />
                          </div>
                        </div>

                        <div class="preset-tasks-preview">
                          <div
                            v-for="taskName in template.taskNames"
                            :key="taskName"
                            class="task-chip"
                          >
                            <span class="task-dot"></span>
                            <span class="task-chip-name">
                              {{ getDisplayName(taskByName.get(taskName)!) }}
                            </span>
                          </div>
                        </div>

                        <div class="preset-actions">
                          <a-button
                            type="primary"
                            block
                            :disabled="template.taskNames.length === 0"
                            @click="applyPresetTemplate(template.preset.name)"
                          >
                            <template #icon>
                              <ThunderboltOutlined />
                            </template>
                            一键切换预设（{{ template.taskNames.length }} 个任务）
                          </a-button>
                        </div>
                      </div>
                    </div>
                  </div>
                  <a-empty
                    v-else-if="orderedTasks.length === 0"
                    description="请从上方添加任务"
                    class="task-queue-empty"
                  />
                  <draggable
                    v-else
                    v-model="queuedTaskNames"
                    :item-key="getTaskKey"
                    :animation="200"
                    ghost-class="task-row-ghost"
                    chosen-class="task-row-chosen"
                    drag-class="task-row-drag"
                    class="task-queue-list"
                    @end="handleTaskDragEnd"
                  >
                    <template #item="{ element: taskName, index }">
                      <div
                        v-if="getQueuedTask(taskName)"
                        class="task-row"
                        :class="{ 'task-row-selected': selectedTask?.name === taskName }"
                        @click="selectTask(taskName)"
                      >
                        <img
                          v-if="resolveMaaFWAssetUrl(getQueuedTask(taskName)?.icon)"
                          :src="resolveMaaFWAssetUrl(getQueuedTask(taskName)?.icon)"
                          alt=""
                          class="task-icon"
                        />
                        <div class="task-main">
                          <span class="task-title">{{ getQueuedTaskDisplayName(taskName) }}</span>
                          <div class="task-meta">
                            <a-tag v-if="getQueuedTask(taskName)?.entry" color="blue">
                              {{ getQueuedTask(taskName)?.entry }}
                            </a-tag>
                            <a-tag
                              v-for="group in getQueuedTask(taskName)?.group || []"
                              :key="group"
                              color="default"
                            >
                              {{ group }}
                            </a-tag>
                          </div>
                        </div>
                        <a-space @click.stop>
                          <a-button
                            type="text"
                            size="small"
                            :disabled="interfaceDependentDisabled || index === 0"
                            aria-label="上移任务"
                            @click="moveTask(taskName, -1)"
                          >
                            <template #icon>
                              <ArrowUpOutlined />
                            </template>
                          </a-button>
                          <a-button
                            type="text"
                            size="small"
                            :disabled="
                              interfaceDependentDisabled || index === orderedTasks.length - 1
                            "
                            aria-label="下移任务"
                            @click="moveTask(taskName, 1)"
                          >
                            <template #icon>
                              <ArrowDownOutlined />
                            </template>
                          </a-button>
                        </a-space>
                      </div>
                    </template>
                  </draggable>
                </div>
              </a-col>
              <a-col :span="12" class="task-option-column">
                <div class="column-header">
                  <span>任务配置</span>
                </div>
                <div v-if="selectedTask" class="task-option-panel">
                  <div class="selected-task-header">
                    <img
                      v-if="resolveMaaFWAssetUrl(selectedTask.icon)"
                      :src="resolveMaaFWAssetUrl(selectedTask.icon)"
                      alt=""
                      class="selected-task-icon"
                    />
                    <div>
                      <div class="selected-task-title">{{ getDisplayName(selectedTask) }}</div>
                      <div class="selected-task-meta">
                        {{ selectedTask.entry || selectedTask.name }}
                      </div>
                    </div>
                  </div>
                  <MaaFWTaskOptionEditor
                    :option-names="getTaskOptionNames(selectedTask)"
                    :options="previewData.options"
                    :task-options="taskSnapshot.taskOptions[selectedTask.name] || {}"
                    :controller-name="effectiveControllerName"
                    :resource-name="effectiveResourceName"
                    :base-path="previewData.path"
                    :disabled="interfaceDependentDisabled"
                    @update="payload => handleTaskOptionUpdate(selectedTask.name, payload)"
                  />
                  <MaaFWDescriptionView
                    v-if="selectedTask.description"
                    :content="selectedTask.description"
                    :base-path="previewData.path"
                    class="selected-task-description"
                  />
                  <a-popconfirm
                    title="确定要删除这个任务吗？"
                    ok-text="确定"
                    cancel-text="取消"
                    :disabled="interfaceDependentDisabled"
                    @confirm="deleteSelectedTask"
                  >
                    <a-button
                      danger
                      block
                      class="delete-task-button"
                      :disabled="interfaceDependentDisabled"
                    >
                      <template #icon>
                        <DeleteOutlined />
                      </template>
                      删除此任务
                    </a-button>
                  </a-popconfirm>
                </div>
                <div v-else class="task-option-empty">
                  <a-empty description="请从左侧选择一个任务进行配置" />
                </div>
              </a-col>
            </a-row>
          </div>

          <ExtraScriptSection :form-data="formData" :loading="loading" @save="handleFieldSave" />

          <div class="form-section">
            <div class="section-header">
              <h3>通知</h3>
            </div>
            <a-row :gutter="24">
              <a-col :span="6">
                <a-form-item label="启用通知">
                  <a-switch
                    v-model:checked="formData.Notify.Enabled"
                    checked-children="启用"
                    un-checked-children="关闭"
                    @change="handleFieldSave('Notify.Enabled', formData.Notify.Enabled)"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="6">
                <a-form-item label="发送统计">
                  <a-switch
                    v-model:checked="formData.Notify.IfSendStatistic"
                    @change="
                      handleFieldSave('Notify.IfSendStatistic', formData.Notify.IfSendStatistic)
                    "
                  />
                </a-form-item>
              </a-col>
              <a-col :span="6">
                <a-form-item label="邮件通知">
                  <a-switch
                    v-model:checked="formData.Notify.IfSendMail"
                    @change="handleFieldSave('Notify.IfSendMail', formData.Notify.IfSendMail)"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="6">
                <a-form-item label="Server 酱">
                  <a-switch
                    v-model:checked="formData.Notify.IfServerChan"
                    @change="handleFieldSave('Notify.IfServerChan', formData.Notify.IfServerChan)"
                  />
                </a-form-item>
              </a-col>
            </a-row>
            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item label="收件地址">
                  <a-input
                    v-model:value="formData.Notify.ToAddress"
                    placeholder="邮件收件地址"
                    size="large"
                    :disabled="!formData.Notify.IfSendMail"
                    @blur="handleFieldSave('Notify.ToAddress', formData.Notify.ToAddress)"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item label="Server 酱密钥">
                  <a-input-password
                    v-model:value="formData.Notify.ServerChanKey"
                    placeholder="Server 酱 SendKey"
                    size="large"
                    :disabled="!formData.Notify.IfServerChan"
                    @blur="handleFieldSave('Notify.ServerChanKey', formData.Notify.ServerChanKey)"
                  />
                </a-form-item>
              </a-col>
            </a-row>
          </div>
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
import { message } from 'ant-design-vue'
import draggable from 'vuedraggable'
import {
  ArrowDownOutlined,
  ArrowLeftOutlined,
  ArrowUpOutlined,
  DeleteOutlined,
  DownOutlined,
  FileSearchOutlined,
  PlusOutlined,
  QuestionCircleOutlined,
  RightOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons-vue'
import ExtraScriptSection from '@/components/ExtraScriptSection.vue'
import { buildMaaFWAssetUrl, useMaaFWApi } from '@/composables/useMaaFWApi'
import { useScriptApi } from '@/composables/useScriptApi'
import { useUserApi } from '@/composables/useUserApi'
import MaaFWDescriptionView from './MaaFWDescriptionView.vue'
import MaaFWTaskOptionEditor from './MaaFWTaskOptionEditor.vue'
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

const scriptId = route.params.scriptId as string
let userId = route.params.userId as string
const isEdit = ref(!!userId)

const scriptName = ref('')
const scriptPath = ref('')
const scriptConfig = ref<MaaFWScriptConfig | null>(null)
const preferAdbController = ref(false)
const previewData = shallowRef<MaaFWInterfacePreviewData | null>(null)
const selectedTaskName = ref('')
const addTaskMenuVisible = ref(false)
const addTaskMenuRootRef = ref<HTMLElement | null>(null)
const selectedAddTaskGroupKey = ref('')
const selectedAddTaskSecondKey = ref('')
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
  Device: {
    AdbAddress: '',
    HWnd: 0,
    PlayCoverAddress: '',
    PlayCoverUuid: '',
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

const controllerOptions = computed(() => previewData.value?.controllers || [])
// 预设 schema（MaaFWPresetInfo）不携带 controller/resource 约束，直接展示全部预设
const presetOptions = computed(() => previewData.value?.presets || [])
const taskByName = computed(() => {
  const entries = (previewData.value?.tasks || []).map(task => [task.name, task] as const)
  return new Map<string, MaaFWTaskInfo>(entries)
})
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
const resourceOptions = computed(() =>
  getResourceOptionsByController(effectiveControllerName.value)
)
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
const effectiveController = computed(() => {
  return controllerOptions.value.find(item => item.name === effectiveControllerName.value)
})
const effectiveResource = computed(() => {
  return resourceOptions.value.find(item => item.name === effectiveResourceName.value)
})
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
    taskSnapshot.value.taskOrder = [...value, ...hiddenTaskNames]
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
const activeAddTaskGroup = computed(() => {
  return addTaskMenuGroups.value.find(group => group.key === selectedAddTaskGroupKey.value) || null
})
const activeAddTaskSecondGroup = computed(() => {
  const item = activeAddTaskGroup.value?.items.find(
    item => item.key === selectedAddTaskSecondKey.value
  )
  return item?.type === 'group' ? item : null
})
const presetTemplates = computed(() => {
  const activeTaskNames = new Set(activeTasks.value.map(task => task.name))
  return presetOptions.value.map(preset => {
    const snapshot = normalizeTaskSnapshot(preset.snapshot, previewData.value)
    const taskNames = snapshot.taskOrder.filter(taskName => activeTaskNames.has(taskName))
    return { preset, taskNames }
  })
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
    closeAddTaskMenu()
    return
  }

  if (!groups.some(group => group.key === selectedAddTaskGroupKey.value)) {
    resetAddTaskMenuSelection()
    return
  }

  if (
    activeAddTaskGroup.value &&
    !activeAddTaskGroup.value.items.some(item => item.key === selectedAddTaskSecondKey.value)
  ) {
    selectedAddTaskSecondKey.value = ''
  }
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

const uniqueOptionNames = (optionGroups: string[][]) => {
  const optionNames: string[] = []
  const seen = new Set<string>()
  for (const group of optionGroups) {
    for (const optionName of group) {
      if (seen.has(optionName)) continue
      seen.add(optionName)
      optionNames.push(optionName)
    }
  }
  return optionNames
}

const getTaskOptionNames = (task: MaaFWTaskInfo) =>
  uniqueOptionNames([
    previewData.value?.globalOption || [],
    effectiveResource.value?.option || [],
    effectiveController.value?.option || [],
    task.option || [],
  ])

const resolveMaaFWAssetUrl = (rawPath?: string | null) => {
  return buildMaaFWAssetUrl(previewData.value?.path, rawPath)
}

const selectTask = (taskName: string) => {
  selectedTaskName.value = taskName
}

const getTaskKey = (taskName: string) => taskName

const getQueuedTask = (taskName: string) => taskByName.value.get(taskName)

const getQueuedTaskDisplayName = (taskName: string) => {
  const task = getQueuedTask(taskName)
  return task ? getDisplayName(task) : taskName
}

const persistQueuedSnapshot = async () => {
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

const resetAddTaskMenuSelection = () => {
  selectedAddTaskGroupKey.value = ''
  selectedAddTaskSecondKey.value = ''
}

const closeAddTaskMenu = () => {
  addTaskMenuVisible.value = false
  resetAddTaskMenuSelection()
}

const toggleAddTaskMenu = () => {
  if (availableTasks.value.length === 0) {
    closeAddTaskMenu()
    return
  }
  addTaskMenuVisible.value = !addTaskMenuVisible.value
  if (!addTaskMenuVisible.value) {
    resetAddTaskMenuSelection()
  }
}

const handleAddTaskGroupClick = (groupKey: string) => {
  if (selectedAddTaskGroupKey.value === groupKey) {
    resetAddTaskMenuSelection()
    return
  }

  selectedAddTaskGroupKey.value = groupKey
  selectedAddTaskSecondKey.value = ''
}

const handleAddTaskSecondClick = async (item: AddTaskSecondLevelItem) => {
  if (item.type === 'task') {
    await addTaskToQueue(item.task.name)
    return
  }

  selectedAddTaskSecondKey.value = selectedAddTaskSecondKey.value === item.key ? '' : item.key
}

const addTaskToQueue = async (taskName: string) => {
  if (!taskByName.value.has(taskName) || taskSnapshot.value.taskOrder.includes(taskName)) {
    closeAddTaskMenu()
    return
  }

  taskSnapshot.value.taskOrder = [...taskSnapshot.value.taskOrder, taskName]
  taskSnapshot.value.taskChecked[taskName] = true
  ensureTaskOptionMap(taskName)
  selectedTaskName.value = taskName
  closeAddTaskMenu()
  await persistQueuedSnapshot()
}

const handleDocumentClick = (event: MouseEvent) => {
  const target = event.target
  if (!(target instanceof Node)) return
  if (addTaskMenuRootRef.value?.contains(target)) return
  closeAddTaskMenu()
}

const applyPresetTemplate = async (presetName: string) => {
  const template = presetTemplates.value.find(item => item.preset.name === presetName)
  if (!template) return

  const presetSnapshot = normalizeTaskSnapshot(template.preset.snapshot, previewData.value)
  const nextTaskNames = template.taskNames
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
  Object.assign(formData.Device, { ...defaults.Device, ...userData.Device })
  Object.assign(formData.Notify, { ...defaults.Notify, ...userData.Notify })
  Object.assign(formData.Data, { ...defaults.Data, ...userData.Data })
}

const handleFieldSave = async (key: string, value: unknown) => {
  if (isInitializing.value || isSaving.value || !userId) return

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

    await updateUser(scriptId, userId, userData)
    logger.info(`用户配置已保存: ${key}`)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存失败: ${errorMsg}`)
  } finally {
    isSaving.value = false
  }
}

const savePresetAndSnapshot = async () => {
  if (isInitializing.value || isSaving.value || !userId) return

  isSaving.value = true
  try {
    formData.Task.TaskSnapshot = JSON.stringify(taskSnapshot.value)
    await updateUser(scriptId, userId, {
      Task: {
        SelectedPreset: formData.Task.SelectedPreset || '',
        TaskSnapshot: formData.Task.TaskSnapshot,
      },
    })
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存任务预设失败: ${errorMsg}`)
  } finally {
    isSaving.value = false
  }
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
  router.push('/scripts')
}

onMounted(() => {
  document.addEventListener('click', handleDocumentClick)

  if (!scriptId) {
    message.error('缺少脚本ID参数')
    handleCancel()
    return
  }

  loadScriptInfo()
})

onBeforeUnmount(() => {
  document.removeEventListener('click', handleDocumentClick)
})
</script>

<style scoped>
.user-edit-container {
  padding: 32px;
  min-height: 100vh;
  background: var(--ant-color-bg-layout);
}

.user-edit-header {
  max-width: 1400px;
  margin: 0 auto 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.breadcrumb-link {
  display: inline-flex;
  align-items: center;
  color: var(--ant-color-text-secondary);
  text-decoration: none;
  white-space: nowrap;
}

.breadcrumb-current {
  display: inline-flex;
  align-items: center;
  color: var(--ant-color-text);
  font-weight: 600;
  white-space: nowrap;
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

.form-section {
  margin-bottom: 24px;
}

.section-header {
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.section-header-with-action {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.section-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--ant-color-text);
  display: flex;
  align-items: center;
  gap: 10px;
}

.section-header h3::before {
  content: '';
  width: 4px;
  height: 20px;
  background: var(--ant-color-primary);
  border-radius: 2px;
}

.form-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}

.account-record-alert {
  margin-bottom: 16px;
}

.preset-switch-button {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.preset-switch-button span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
}

.task-loading {
  padding: 24px;
}

.task-loading :deep(.ant-spin-container) {
  opacity: 1;
}

.task-empty {
  padding: 24px;
  border: 1px dashed var(--ant-color-border);
  border-radius: 8px;
}

.task-editor-layout {
  min-height: 420px;
}

.task-list-column,
.task-option-column {
  display: flex;
  flex-direction: column;
}

.column-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
  color: var(--ant-color-text);
  font-size: 16px;
  font-weight: 600;
}

.add-task-menu {
  position: relative;
  flex: 0 0 auto;
}

.add-task-popup {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  z-index: 20;
  display: flex;
  max-width: min(720px, calc(100vw - 64px));
  max-height: 360px;
  overflow: auto;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-bg-elevated);
  box-shadow: var(--ant-box-shadow-secondary);
}

.add-task-menu-column {
  width: 220px;
  flex: 0 0 220px;
  padding: 8px;
  border-right: 1px solid var(--ant-color-border-secondary);
}

.add-task-menu-column:last-child {
  border-right: none;
}

.add-task-menu-item {
  width: 100%;
  min-height: 36px;
  padding: 7px 8px 7px 10px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--ant-color-text);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  font: inherit;
  font-size: 14px;
  line-height: 1.4;
  text-align: left;
}

.add-task-menu-item:hover,
.add-task-menu-item-active {
  background: var(--ant-color-fill-tertiary);
}

.add-task-menu-label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.add-task-menu-meta {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  flex: 0 0 auto;
}

.add-task-menu-chevron {
  font-size: 11px;
}

.task-list {
  flex: 1;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  overflow: hidden;
  background: var(--ant-color-bg-container);
}

.task-queue-list {
  min-height: 100%;
}

.preset-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px;
}

.preset-card {
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
}

.preset-card-inner {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 16px;
}

.preset-header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.preset-icon-wrap {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
  flex: 0 0 auto;
}

.preset-icon {
  font-size: 18px;
}

.preset-info {
  flex: 1;
  min-width: 0;
}

.preset-name {
  margin: 0 0 4px;
  font-size: 16px;
  font-weight: 700;
  color: var(--ant-color-text);
}

.preset-desc {
  color: var(--ant-color-text-secondary);
  font-size: 13px;
}

.preset-tasks-preview {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 10px 12px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
}

.task-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
  padding: 3px 10px 3px 7px;
  border-radius: 16px;
  background: var(--ant-color-bg-container);
  color: var(--ant-color-text);
  font-size: 13px;
}

.task-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--ant-color-success);
  flex: 0 0 auto;
}

.task-chip-name {
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
  background: var(--ant-color-bg-container);
  cursor: pointer;
  transition:
    background-color 0.2s ease,
    border-color 0.2s ease;
}

.task-row-chosen,
.task-row-drag {
  cursor: grabbing;
}

.task-row-ghost {
  opacity: 0.45;
  background: var(--ant-color-primary-bg);
}

.task-row:last-child {
  border-bottom: none;
}

.task-row:hover {
  background: var(--ant-color-fill-quaternary);
}

.task-row-selected {
  background: var(--ant-color-primary-bg);
  border-left: 3px solid var(--ant-color-primary);
  padding-left: 13px;
}

.task-main {
  flex: 1;
  min-width: 0;
}

.task-icon {
  width: 28px;
  height: 28px;
  object-fit: contain;
  flex: 0 0 auto;
}

.task-title {
  font-weight: 600;
}

.task-meta {
  margin-top: 6px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.task-option-panel {
  min-height: 100%;
  padding: 20px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
}

.selected-task-header {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.selected-task-icon {
  width: 32px;
  height: 32px;
  object-fit: contain;
  flex: 0 0 auto;
}

.selected-task-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--ant-color-text);
}

.selected-task-meta {
  margin-top: 4px;
  color: var(--ant-color-text-tertiary);
  font-size: 13px;
}

.selected-task-description {
  margin: 20px 0 0;
  padding: 16px 0 20px;
  border-top: 1px solid var(--ant-color-border-secondary);
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.task-option-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 320px;
  border: 1px dashed var(--ant-color-border);
  border-radius: 8px;
}

.delete-task-button {
  margin-top: 24px;
  height: 40px;
}

@media (max-width: 768px) {
  .user-edit-container {
    padding: 16px;
  }

  .user-edit-header,
  .section-header-with-action,
  .column-header,
  .task-row {
    flex-direction: column;
    align-items: stretch;
  }

  .task-editor-layout {
    row-gap: 16px;
  }

  .add-task-menu {
    width: 100%;
  }

  .add-task-menu :deep(.ant-btn) {
    width: 100%;
  }

  .add-task-popup {
    left: 0;
    right: auto;
    max-width: calc(100vw - 32px);
  }

  .task-editor-layout :deep(.ant-col) {
    max-width: 100%;
    flex: 0 0 100%;
  }
}
</style>
