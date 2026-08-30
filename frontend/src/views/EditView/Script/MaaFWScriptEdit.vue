<template>
  <div class="script-edit-header">
    <div class="header-nav">
      <a-breadcrumb class="breadcrumb">
        <a-breadcrumb-item>
          <router-link to="/scripts" class="breadcrumb-link"> 脚本管理</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          <div class="breadcrumb-current">
            <img src="../../../assets/maafw.png" alt="MFW" class="breadcrumb-logo" />
            {{ projectDisplayName }} {{ isWizard ? '项目引导' : '项目配置' }}
          </div>
        </a-breadcrumb-item>
      </a-breadcrumb>
    </div>

    <a-space size="middle">
      <a-button size="large" class="cancel-button" @click="handleCancel">
        <template #icon>
          <ArrowLeftOutlined />
        </template>
        返回
      </a-button>
    </a-space>
  </div>

  <div class="script-edit-content">
    <a-card
      :title="`${projectDisplayName} ${isWizard ? '项目引导' : '项目配置'}`"
      :loading="pageLoading"
      class="config-card"
    >
      <template #extra>
        <a-tag color="geekblue" class="type-tag"> MFW</a-tag>
      </template>

      <a-steps
        v-if="isWizard"
        size="small"
        :current="currentStep"
        :items="stepItems"
        class="wizard-steps"
      />

      <a-form ref="formRef" :model="formData" :rules="rules" layout="vertical" class="config-form">
        <div v-show="!isWizard || currentStep === 0">
          <BasicInfoSection
            :maafw-config="maafwConfig"
            :form-data="formData"
            :rules="rules"
            :preview-data="previewData"
            :interface-loading="previewLoading"
            :preview-project-title="previewProjectTitle"
            :interface-stats="interfaceStats"
            :update-applying="updateApplying"
            @change="handleChange"
            @select-path="selectMaaFWPath"
            @preview-interface="handlePreviewInterface"
          />
        </div>

        <div v-show="!isWizard || currentStep === 1">
          <ControlConfigSection
            :maafw-config="maafwConfig"
            :preview-data="previewData"
            :interface-loading="previewLoading"
            :emulator-loading="emulatorLoading"
            :emulator-options-ready="emulatorOptionsReady"
            :emulator-device-loading="emulatorDeviceLoading"
            :emulator-options="emulatorOptions"
            :emulator-device-options="emulatorDeviceOptions"
            :emulator-type-by-id="emulatorTypeById"
            :controller-options="controllerOptions"
            :effective-controller-name="effectiveControllerName"
            :effective-controller-type="effectiveControllerType"
            :is-adb-controller="isAdbController"
            :is-desktop-controller="isDesktopController"
            :resource-options="resourceOptions"
            :unsupported-controller-options="unsupportedControllerOptions"
            :unsupported-controller-message="unsupportedControllerMessage"
            :adb-control-strategy-message="adbControlStrategyMessage"
            :adb-control-strategy-items="adbControlStrategyItems"
            :selected-emulator-label="selectedEmulatorLabel"
            :interface-dependent-disabled="interfaceDependentDisabled"
            @change="handleChange"
            @controller-change="handleControllerChange"
            @resource-change="handleResourceChange"
            @emulator-select-change="handleEmulatorSelectChange"
            @select-launch-path="selectLaunchPath"
          />
        </div>

        <div v-show="!isWizard || currentStep === 2">
          <UpdateSettingsSection
            :maafw-config="maafwConfig"
            :preview-data="previewData"
            :is-auto-update-disabled="isAutoUpdateDisabled"
            :update-checking="updateChecking"
            :update-applying="updateApplying"
            :update-error="updateError"
            :update-result="updateResult"
            :update-source-options="updateSourceOptions"
            :update-channel-options="updateChannelOptions"
            @change="handleChange"
            @check-update="runUpdateCheck"
            @apply-update="runUpdateApply"
          />
        </div>

        <div v-show="!isWizard || currentStep === 3">
          <RunConfigSection
            :maafw-config="maafwConfig"
            :daily-once-tasks="dailyOnceTasks"
            :weekly-once-tasks="weeklyOnceTasks"
            :monthly-once-tasks="monthlyOnceTasks"
            :period-task-options="periodTaskOptions"
            :interface-dependent-disabled="interfaceDependentDisabled"
            @change="handleChange"
            @period-task-change="handlePeriodTaskChange"
          />
        </div>
      </a-form>

      <div v-if="isWizard" class="wizard-actions">
        <a-button v-if="currentStep > 0" size="large" @click="currentStep -= 1"> 上一步 </a-button>
        <a-button
          v-if="currentStep < stepItems.length - 1"
          type="primary"
          size="large"
          :disabled="!canLeaveCurrentStep"
          @click="currentStep += 1"
        >
          下一步
        </a-button>
        <a-button v-else type="primary" size="large" @click="handleCancel"> 完成 </a-button>
      </div>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { FormInstance } from 'ant-design-vue'
import { message } from 'ant-design-vue'
import { ArrowLeftOutlined } from '@ant-design/icons-vue'
import { useScriptApi } from '@/composables/useScriptApi'
import { useMaaFWUpdateApi, type MaaFWUpdateResult } from '@/composables/useMaaFWUpdateApi'
import {
  getDefaultMaaFWScriptConfig,
  updateChannelOptions,
  updateSourceOptions,
  useMaaFWControlConfig,
} from '@/composables/useMaaFWScriptConfig'
import type {
  MaaFWInterfacePreviewData,
  MaaFWScriptConfig,
  MaaFWTaskInfo,
  ScriptType,
} from '@/types/script'
import BasicInfoSection from './MaaFWScriptEdit/BasicInfoSection.vue'
import ControlConfigSection from './MaaFWScriptEdit/ControlConfigSection.vue'
import UpdateSettingsSection from './MaaFWScriptEdit/UpdateSettingsSection.vue'
import RunConfigSection from './MaaFWScriptEdit/RunConfigSection.vue'

const logger = window.electronAPI.getLogger('MaaFW 脚本编辑')

// MaaFW pretask 伪任务：预览接口会把它们混进 tasks[]（entry 固定为 MXU_PRETASK、
// name 带 __MXU_PRETASK__ 前缀），周期跳过下拉不能让用户选到。按 entry 过滤、name 前缀兜底。
const PRETASK_TASK_ENTRY = 'MXU_PRETASK'
const PRETASK_TASK_PREFIX = '__MXU_PRETASK__'
const isPretaskTask = (task: MaaFWTaskInfo): boolean =>
  task.entry === PRETASK_TASK_ENTRY || task.name.startsWith(PRETASK_TASK_PREFIX)

const PERIOD_KEYS = ['DailyOnceTasks', 'WeeklyOnceTasks', 'MonthlyOnceTasks'] as const
type PeriodKey = (typeof PERIOD_KEYS)[number]

const route = useRoute()
const router = useRouter()
const { getScript, updateScript, previewMaaFWInterface } = useScriptApi()
const { checkMaaFWUpdate, applyMaaFWUpdate } = useMaaFWUpdateApi()

const scriptId = route.params.id as string

// 引导模式：同一个页面按步骤渲染四个分节。新建 MaaFW 脚本后进这里，
// 之后再编辑走 /scripts/:id/edit/maafw 的完整单页形态。
const isWizard = computed(() => route.name === 'MaaFWSetupWizard')
const currentStep = ref(0)
const stepItems = [
  { title: '基本信息' },
  { title: '控制配置' },
  { title: '项目更新' },
  { title: '运行配置' },
]
// 第一步没读到 interface 就往下走，后面几步全是空的，先拦住
const canLeaveCurrentStep = computed(() => currentStep.value !== 0 || previewData.value !== null)
const pageLoading = ref(false)
const isInitializing = ref(true)
const isSaving = ref(false)

const formRef = ref<FormInstance>()
const previewLoading = ref(false)
const previewData = ref<MaaFWInterfacePreviewData | null>(null)

const dailyOnceTasks = ref<string[]>([])
const weeklyOnceTasks = ref<string[]>([])
const monthlyOnceTasks = ref<string[]>([])

const maafwConfig = reactive<MaaFWScriptConfig>(getDefaultMaaFWScriptConfig())

const formData = reactive<{ type: ScriptType; name: string; path: string }>({
  type: 'MaaFW',
  name: '',
  path: '',
})

const rules = {
  name: [{ required: true, message: '请输入脚本名称', trigger: 'blur' }],
  path: [
    {
      validator: () =>
        maafwConfig.Info.Path
          ? Promise.resolve()
          : Promise.reject(new Error('请选择 MFW 项目实际目录并读取 interface')),
      trigger: 'blur',
    },
  ],
}

const handleChange = async (category: keyof MaaFWScriptConfig, key: string, value: unknown) => {
  if (isInitializing.value || isSaving.value) return
  isSaving.value = true
  try {
    const success = await updateScript(scriptId, { [category]: { [key]: value } })
    if (success) logger.info(`配置已保存: ${String(category)}.${key}`)
  } catch (error) {
    logger.error(`保存失败: ${error instanceof Error ? error.message : String(error)}`)
  } finally {
    isSaving.value = false
  }
}

const {
  emulatorLoading,
  emulatorOptionsReady,
  emulatorDeviceLoading,
  emulatorOptions,
  emulatorDeviceOptions,
  emulatorTypeById,
  controllerOptions,
  unsupportedControllerOptions,
  unsupportedControllerMessage,
  effectiveControllerName,
  effectiveControllerType,
  isAdbController,
  isDesktopController,
  resourceOptions,
  interfaceDependentDisabled,
  selectedEmulatorLabel,
  adbControlStrategyMessage,
  adbControlStrategyItems,
  handleControllerChange,
  handleResourceChange,
  handleEmulatorSelectChange,
  syncControllerResourceSelection,
  loadEmulatorOptions,
  loadEmulatorDeviceOptions,
  selectLaunchPath,
} = useMaaFWControlConfig(maafwConfig, previewData, previewLoading, handleChange)

const isAutoUpdateDisabled = computed(() =>
  Boolean(previewData.value && !previewData.value.project.version)
)

const previewProjectTitle = computed(() => {
  if (!previewData.value) return '-'
  const project = previewData.value.project
  return project.title || project.label || project.name
})

const projectDisplayName = computed(() => {
  const candidates = [
    previewData.value ? previewProjectTitle.value : '',
    maafwConfig.Info.ProjectLabel,
    maafwConfig.Info.Name,
  ]
  return candidates.find(value => typeof value === 'string' && value.trim())?.trim() || 'MFW'
})

const interfaceStats = computed(() => [
  { label: '任务', value: previewData.value?.tasks.length ?? 0 },
  { label: '预设', value: previewData.value?.presets.length ?? 0 },
  { label: '控制器', value: previewData.value?.controllers.length ?? 0 },
  { label: '资源', value: previewData.value?.resources.length ?? 0 },
  { label: '导入', value: previewData.value?.importCount ?? 0 },
  { label: 'Agent', value: previewData.value?.agentCount ?? 0 },
])

const periodTaskOptions = computed(() =>
  (previewData.value?.tasks || [])
    .filter(task => !isPretaskTask(task))
    .map(task => ({
      label: task.label ? `${task.label}（${task.name}）` : task.name,
      value: task.name,
    }))
)

// ConfigBase 把周期任务列表以 JSON 字符串保存、读回也是字符串；
// 兼容后端某天直接返回数组的情况，统一收敛成字符串数组。
const parseTaskNameList = (value: unknown): string[] => {
  if (Array.isArray(value)) return value.filter((item): item is string => typeof item === 'string')
  if (typeof value === 'string' && value.trim()) {
    try {
      const parsed = JSON.parse(value)
      return Array.isArray(parsed)
        ? parsed.filter((item): item is string => typeof item === 'string')
        : []
    } catch {
      return []
    }
  }
  return []
}

const stringifyTaskNameList = (value: string[]): string => JSON.stringify(value)

const periodTaskRef = (key: PeriodKey): typeof dailyOnceTasks =>
  key === 'DailyOnceTasks'
    ? dailyOnceTasks
    : key === 'WeeklyOnceTasks'
      ? weeklyOnceTasks
      : monthlyOnceTasks

const handlePeriodTaskChange = async (key: PeriodKey, values: string[]) => {
  const normalized = Array.from(new Set(values.filter(Boolean)))
  periodTaskRef(key).value = normalized
  maafwConfig.Run[key] = stringifyTaskNameList(normalized)
  await handleChange('Run', key, maafwConfig.Run[key])
}

const prunePeriodTaskSelections = async () => {
  const available = new Set((previewData.value?.tasks || []).map(task => task.name))
  for (const key of PERIOD_KEYS) {
    const current = periodTaskRef(key).value
    const next = current.filter(name => available.has(name))
    if (next.length !== current.length) {
      await handlePeriodTaskChange(key, next)
    }
  }
}

const applyScriptConfig = (config: Partial<MaaFWScriptConfig> | null | undefined) => {
  const defaults = getDefaultMaaFWScriptConfig()
  ;(Object.keys(defaults) as Array<keyof MaaFWScriptConfig>).forEach(section => {
    Object.assign(
      maafwConfig[section] as Record<string, unknown>,
      defaults[section] as Record<string, unknown>,
      (config?.[section] as Record<string, unknown>) ?? {}
    )
  })
  formData.name = maafwConfig.Info.Name || ''
  formData.path = maafwConfig.Info.Path || ''
  dailyOnceTasks.value = parseTaskNameList(maafwConfig.Run.DailyOnceTasks)
  weeklyOnceTasks.value = parseTaskNameList(maafwConfig.Run.WeeklyOnceTasks)
  monthlyOnceTasks.value = parseTaskNameList(maafwConfig.Run.MonthlyOnceTasks)
}

const runPreview = async () => {
  const path = maafwConfig.Info.Path.trim()
  if (!path) {
    previewData.value = null
    return
  }
  previewLoading.value = true
  try {
    const response = await previewMaaFWInterface(path)
    if (!response || response.code !== 200 || !response.data) {
      previewData.value = null
      message.error(response?.message || 'MaaFW interface 预览失败，请检查后端服务与项目目录')
      return
    }
    previewData.value = response.data as MaaFWInterfacePreviewData
    await syncControllerResourceSelection(true)
    await prunePeriodTaskSelections()
  } catch (error) {
    previewData.value = null
    message.error(error instanceof Error ? error.message : String(error))
  } finally {
    previewLoading.value = false
  }
}

const handlePreviewInterface = async () => {
  await runPreview()
  if (previewData.value) message.success(`已读取 ${previewProjectTitle.value}`)
}

const selectMaaFWPath = async () => {
  try {
    if (!window.electronAPI) {
      message.error('文件选择功能不可用，请在 Electron 环境中运行')
      return
    }
    const path = await window.electronAPI.selectFolder()
    if (!path) return
    maafwConfig.Info.Path = path
    formData.path = path
    await handleChange('Info', 'Path', path)
    await runPreview()
  } catch (error) {
    logger.error(`选择项目目录失败: ${error instanceof Error ? error.message : String(error)}`)
    message.error('选择文件夹失败')
  }
}

const updateChecking = ref(false)
const updateApplying = ref(false)
const updateError = ref('')
const updateResult = ref<MaaFWUpdateResult | null>(null)

const runUpdateCheck = async () => {
  updateChecking.value = true
  updateError.value = ''
  try {
    updateResult.value = await checkMaaFWUpdate(scriptId)
  } catch (error) {
    updateResult.value = null
    updateError.value = error instanceof Error ? error.message : String(error)
  } finally {
    updateChecking.value = false
  }
}

const runUpdateApply = async () => {
  updateApplying.value = true
  updateError.value = ''
  try {
    updateResult.value = await applyMaaFWUpdate(scriptId)
    if (updateResult.value.updated && maafwConfig.Info.Path) {
      await runPreview()
    }
  } catch (error) {
    updateError.value = error instanceof Error ? error.message : String(error)
  } finally {
    updateApplying.value = false
  }
}

const handleCancel = () => {
  router.push('/scripts')
}

onMounted(async () => {
  pageLoading.value = true
  try {
    const [scriptDetail] = await Promise.all([getScript(scriptId), loadEmulatorOptions()])
    if (!scriptDetail) {
      message.error('脚本不存在或加载失败')
      router.push('/scripts')
      return
    }
    applyScriptConfig(scriptDetail.config as Partial<MaaFWScriptConfig>)
    if (!maafwConfig.Info.Name) {
      maafwConfig.Info.Name = scriptDetail.name ?? '新 MFW 脚本'
      formData.name = maafwConfig.Info.Name
    }

    if (maafwConfig.Emulator.Id && maafwConfig.Emulator.Id !== '-') {
      await loadEmulatorDeviceOptions(maafwConfig.Emulator.Id)
    }
    if (maafwConfig.Info.Path) {
      await runPreview()
    }
  } catch (error) {
    logger.error(`加载脚本失败: ${error instanceof Error ? error.message : String(error)}`)
    message.error('加载脚本失败')
    router.push('/scripts')
  } finally {
    pageLoading.value = false
    isInitializing.value = false
  }
})
</script>

<style scoped>
.wizard-steps {
  margin-bottom: 28px;
}

.wizard-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 8px;
  padding-top: 20px;
  border-top: 1px solid var(--ant-color-border-secondary);
}

.script-edit-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 32px;
  padding: 0 8px;
}

.header-nav {
  flex: 1;
}

.breadcrumb {
  margin: 0;
}

.breadcrumb-link {
  align-items: center;
  gap: 8px;
  color: var(--ant-color-text-secondary);
  text-decoration: none;
  transition: color 0.3s ease;
}

.breadcrumb-current {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--ant-color-text);
  font-weight: 600;
}

.breadcrumb-logo {
  width: 20px;
  height: 20px;
  object-fit: contain;
}

.script-edit-content {
  flex: 1;
}

.config-card {
  border-radius: 16px;
  box-shadow: none;
  border: 1px solid var(--ant-color-border-secondary);
  overflow: hidden;
}

.type-tag {
  font-size: 14px;
  font-weight: 600;
  padding: 8px 16px;
  border-radius: 8px;
  border: none;
}

.config-form {
  max-width: none;
}

.config-form :deep(.ant-form-item) {
  margin-bottom: 20px;
}

.cancel-button {
  height: 40px;
}
</style>
