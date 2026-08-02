<template>
  <div class="user-edit-container">
    <div class="user-edit-header">
      <div class="header-nav">
        <a-breadcrumb class="breadcrumb">
          <a-breadcrumb-item>
            <router-link to="/scripts" class="breadcrumb-link"> 脚本管理</router-link>
          </a-breadcrumb-item>
          <a-breadcrumb-item>
            <router-link
              :to="{ name: 'HSRScriptEdit', params: { id: scriptId } }"
              class="breadcrumb-link"
            >
              {{ scriptName }}
            </router-link>
          </a-breadcrumb-item>
          <a-breadcrumb-item>
            <span class="breadcrumb-current">
              <img src="@/assets/hsr.png" alt="HSR" class="breadcrumb-logo" />
              {{ isEdit ? '编辑 HSR 用户' : '添加 HSR 用户' }}
            </span>
          </a-breadcrumb-item>
        </a-breadcrumb>
      </div>
      <a-button size="large" class="cancel-button" @click="handleCancel">
        <template #icon><ArrowLeftOutlined /></template>
        返回
      </a-button>
    </div>

    <div class="user-edit-content">
      <a-card class="config-card">
        <a-alert
          v-for="warning in capabilitySnapshot?.warnings || []"
          :key="warning"
          type="warning"
          show-icon
          :message="warning"
          style="margin-bottom: 12px"
        />
        <a-form ref="formRef" :model="formData" layout="vertical" class="config-form">
          <!-- 基本信息 -->
          <div class="form-section">
            <div class="section-header"><h3>基本信息</h3></div>
            <a-row :gutter="24">
              <a-col :span="8">
                <a-form-item>
                  <template #label>
                    <a-tooltip title="该名称也会作为货币战争的开拓者名称写入 M7A/SRA">
                      <span class="form-label"
                        >用户名 <QuestionCircleOutlined class="help-icon"
                      /></span>
                    </a-tooltip>
                  </template>
                  <a-input
                    v-model:value="formData.Info.Name"
                    size="large"
                    class="modern-input"
                    @blur="handleFieldSave('Info.Name', formData.Info.Name)"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="4">
                <a-form-item>
                  <template #label>
                    <span class="form-label">启用</span>
                  </template>
                  <a-switch
                    v-model:checked="formData.Info.Status"
                    checked-children="启用"
                    un-checked-children="禁用"
                    @change="handleFieldSave('Info.Status', formData.Info.Status)"
                  />
                </a-form-item>
              </a-col>
              <a-col v-if="controlMode === 'managed' && effectiveEngines.has('SRA')" :span="6">
                <a-form-item>
                  <template #label>
                    <span class="form-label">账号</span>
                  </template>
                  <a-input
                    v-model:value="formData.SRA.Id"
                    placeholder="请输入账号"
                    size="large"
                    class="modern-input"
                    @blur="handleFieldSave('SRA.Id', formData.SRA.Id)"
                  />
                </a-form-item>
              </a-col>
              <a-col v-if="controlMode === 'managed' && effectiveEngines.has('SRA')" :span="6">
                <a-form-item>
                  <template #label>
                    <span class="form-label">密码</span>
                  </template>
                  <!-- 用 input-class 把 modern-input 挂到内部 <input>，避免 a-input-password 外层嵌套 div -->
                  <a-input-password
                    v-model:value="formData.SRA.Password"
                    placeholder="请输入密码"
                    size="large"
                    :input-class="'modern-input'"
                    @blur="handleFieldSave('SRA.Password', formData.SRA.Password)"
                  />
                </a-form-item>
              </a-col>
            </a-row>
            <a-row :gutter="24" style="margin-top: 8px">
              <a-col :span="6">
                <a-form-item>
                  <template #label>
                    <span class="form-label">服务器</span>
                  </template>
                  <a-select
                    v-model:value="formData.Info.Server"
                    size="large"
                    :options="serverOptions"
                    @change="handleFieldSave('Info.Server', formData.Info.Server)"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="6">
                <a-form-item>
                  <template #label>
                    <a-tooltip
                      title="剩余天数，-1 表示不限制；0 表示今日到期；正数表示距到期还剩 N 天"
                    >
                      <span class="form-label"
                        >剩余天数 <QuestionCircleOutlined class="help-icon"
                      /></span>
                    </a-tooltip>
                  </template>
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
              <a-col :span="12">
                <a-form-item class="control-mode-form-item">
                  <template #label>
                    <span class="form-label">运行模式</span>
                  </template>
                  <a-select
                    :value="controlMode"
                    :options="controlModeOptions"
                    :disabled="isSaving"
                    class="control-mode-select"
                    size="large"
                    @change="handleControlModeChange"
                  />
                </a-form-item>
              </a-col>
            </a-row>
            <a-row :gutter="24" style="margin-top: 8px">
              <a-col :span="24">
                <a-form-item>
                  <template #label>
                    <span class="form-label">备注</span>
                  </template>
                  <a-textarea
                    v-model:value="formData.Info.Notes"
                    :rows="2"
                    allow-clear
                    placeholder="请输入备注"
                    class="notes-textarea"
                    @blur="handleFieldSave('Info.Notes', formData.Info.Notes)"
                  />
                </a-form-item>
              </a-col>
            </a-row>
            <a-alert
              v-if="controlMode === 'managed' && effectiveEngines.has('SRA')"
              type="info"
              show-icon
              style="margin-top: 8px"
              message="保存时 MAS 会自动加密账号密码。未配置 SRA 或未使用 SRA 模块时，账号密码不会用于切号。"
            />
          </div>

          <div v-if="controlMode === 'managed'" class="control-mode-content">
            <a-alert
              type="info"
              show-icon
              message="MAS 按这个用户的任务开关、动态原生选项和执行引擎运行。"
              class="mode-alert"
            />
            <StageConfigSection
              v-if="dailyStageEngine"
              :form-data="formData"
              :loading="isSaving"
              :daily-engine="dailyStageEngine"
              :stage-options="hsrStageOptions"
              :stage-options-loading="hsrStageOptionsLoading"
              :stage-options-error="hsrStageOptionsError"
              @save="handleFieldSave"
            />
            <ManagedTaskSection
              :snapshot="managedConfigSnapshot"
              :task-switch="formData.TaskSwitch"
              :saving="isSaving"
              :loading="managedConfigLoading"
              @import-source="handleManagedSourceImport"
              @task-toggle="handleTaskSwitchToggle"
              @mapping-change="handleManagedMappingChange"
              @field-change="handleManagedFieldChange"
            />
          </div>
          <div v-else class="control-mode-content">
            <a-alert
              type="warning"
              show-icon
              message="脚本直控不会读取该用户的账号、体力副本和 MAS 任务开关。"
              class="mode-alert"
            />
            <DirectControlSection
              :available-engines="[...effectiveEngines]"
              :control="formData.Control"
              :direct="formData.Direct"
              :native-controls="nativeControls"
              :saving="isSaving"
              :importing-engine="importingDirectEngine"
              :opening-engine="openingConfiguratorEngine"
              @toggle="handleDirectEngineToggle"
              @import-config="handleDirectConfigImport"
              @open-configurator="handleOpenNativeConfigurator"
            />
          </div>

          <!-- 进度与重置 (历战余响开始日 已下沉到 体力配置 区) -->
          <div v-if="controlMode === 'managed'" class="form-section">
            <div class="section-header"><h3>进度与重置</h3></div>

            <!-- 历战余响进度 -->
            <a-row :gutter="24" align="middle">
              <a-col :span="10">
                <div class="progress-group">
                  <span class="progress-label">历战余响</span>
                  <a-tag :color="eowCompletedThisWeek ? 'green' : 'orange'">
                    本周 {{ eowCompletedThisWeek ? '已完成' : '未完成' }}
                  </a-tag>
                  <span
                    v-if="hasValidCompletionDate(formData.Data.EchoOfWarLastCompletionDate)"
                    class="date-hint"
                  >
                    最近完成：{{ formData.Data.EchoOfWarLastCompletionDate }}
                  </span>
                </div>
              </a-col>
              <a-col :span="14">
                <a-space>
                  <a-button size="small" :disabled="eowCompletedThisWeek" @click="markEowCompleted">
                    标记完成
                  </a-button>
                  <a-button size="small" danger @click="resetEowProgress"> 重置 </a-button>
                </a-space>
              </a-col>
            </a-row>

            <!-- 周常进度 -->
            <a-row :gutter="24" align="middle" style="margin-top: 16px">
              <a-col :span="10">
                <div class="progress-group">
                  <span class="progress-label">周常</span>
                  <a-tag :color="formData.Data.WeeklyCompletedThisWeek ? 'green' : 'orange'">
                    本周 {{ formData.Data.WeeklyCompletedThisWeek ? '已完成' : '未完成' }}
                  </a-tag>
                  <span
                    v-if="hasValidCompletionDate(formData.Data.WeeklyLastCompletionDate)"
                    class="date-hint"
                  >
                    最近完成：{{ formData.Data.WeeklyLastCompletionDate }}
                  </span>
                </div>
              </a-col>
              <a-col :span="14">
                <a-space>
                  <a-button
                    size="small"
                    :disabled="formData.Data.WeeklyCompletedThisWeek"
                    @click="markWeeklyCompleted"
                  >
                    标记完成
                  </a-button>
                  <a-button size="small" danger @click="resetWeeklyProgress"> 重置 </a-button>
                </a-space>
              </a-col>
            </a-row>
          </div>
        </a-form>
      </a-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { ArrowLeftOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import { useScriptRegistryApi } from '@/composables/useScriptRegistryApi'
import { useWebSocket } from '@/composables/useWebSocket'
import { WS_ID_PLUGIN_SYSTEM, WS_PLUGIN_SNAPSHOT_UPDATED } from '@/services/websocket/types'
import {
  useHSRPluginApi,
  type HSREngine,
  type HSRCapabilitySnapshot,
  type HSRManagedConfigSnapshot,
  type HSRNativeControlSnapshot,
} from '@/composables/useHSRPluginApi'
import { DEFAULT_HSR_TASK_MAPPING, resolveTaskMappingValue } from '@/types/script'
import type { HSRDynamicStageOptionsData, HSRUserConfigData } from '@/views/HSRUserEdit/types'
import {
  buildHSRCapabilityView,
  resolveCapabilityTaskEngine,
} from '@/views/HSRUserEdit/capabilityView'
import DirectControlSection from './HSRUserEdit/DirectControlSection.vue'
import ManagedTaskSection from './HSRUserEdit/ManagedTaskSection.vue'
import StageConfigSection from '@/views/HSRUserEdit/StageConfigSection.vue'

const getCurrentISOWeek = (): string => {
  const d = new Date()
  const dayNum = d.getDay() || 7
  const thursday = new Date(d)
  thursday.setDate(d.getDate() + 4 - dayNum)
  const yearStart = new Date(thursday.getFullYear(), 0, 1)
  const weekNo = Math.ceil(((thursday.getTime() - yearStart.getTime()) / 86400000 + 1) / 7)
  return `${thursday.getFullYear()}-W${String(weekNo).padStart(2, '0')}`
}

const getCurrentDate = (): string => {
  const d = new Date()
  const yyyy = d.getFullYear()
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${yyyy}-${mm}-${dd}`
}

const logger = window.electronAPI.getLogger('HSR 用户编辑')

const route = useRoute()
const router = useRouter()
const registryApi = useScriptRegistryApi()
const hsrPluginApi = useHSRPluginApi()
const { subscribe, unsubscribe } = useWebSocket()
const getScript = async (id: string) => (await registryApi.getScripts(id))[0] ?? null
const addUser = async (id: string) => ({ userId: (await registryApi.addUser(id)).id })
const updateUser = async (id: string, uid: string, config: Record<string, unknown>) => {
  await registryApi.updateUser(id, uid, config)
  return true
}
const getUsers = (id: string, uid: string) => registryApi.getUsers(id, uid)

const isInitializing = ref(true)
const isSaving = ref(false)

const scriptId = route.params.scriptId as string
let userId = route.params.userId as string
const isEdit = ref(!!userId)

const scriptName = ref('')
type HSRTaskMapping = Partial<
  Record<'Daily' | 'ReceiveRewards' | 'DivergentUniverse' | 'CurrencyWars', HSREngine>
>
type HSRScriptConfig = {
  SRA?: { Path?: string }
  M7A?: { Path?: string; LowPerformanceMode?: boolean }
  TaskMapping?: HSRTaskMapping
}
const scriptConfig = ref<HSRScriptConfig | null>(null)
const capabilitySnapshot = ref<HSRCapabilitySnapshot | null>(null)
const capabilityView = computed(() => buildHSRCapabilityView(capabilitySnapshot.value))
const effectiveEngines = computed(() => capabilityView.value.effectiveEngines)
const managedConfigSnapshot = ref<HSRManagedConfigSnapshot | null>(null)
const managedConfigLoading = ref(false)
const nativeControls = reactive<Partial<Record<HSREngine, HSRNativeControlSnapshot>>>({})
const importingDirectEngine = ref<HSREngine | null>(null)
const openingConfiguratorEngine = ref<HSREngine | null>(null)
let pluginSystemSubscriptionId: string | null = null

const handlePluginSystemMessage = () => {
  void hsrPluginApi
    .getCapabilities(scriptId)
    .then(async snapshot => {
      capabilitySnapshot.value = snapshot
      await refreshNativeControls()
      if (userId && controlMode.value === 'managed') await loadManagedConfig()
      await loadHsrStageOptions()
    })
    .catch(error => logger.warn(`刷新 HSR 能力失败: ${String(error)}`))
}
const hsrStageOptions = ref<HSRDynamicStageOptionsData | null>(null)
const hsrStageOptionsLoading = ref(false)
const hsrStageOptionsError = ref('')

const serverOptions = [{ value: 'CN-Official', label: '官服' }]
const controlModeOptions = [
  { value: 'managed', label: 'MAS 管控' },
  { value: 'direct', label: '脚本直控' },
]
type MutableRecord = Record<string, unknown>

const DEFAULT_COMPLETION_DATE = '2000-01-01'

const hasValidCompletionDate = (value?: string | null): boolean => {
  const date = String(value ?? '').trim()
  return date !== '' && date !== DEFAULT_COMPLETION_DATE
}

// 优先使用当前用户映射；旧脚本级 TaskMapping 只作为迁移回退。
const getTaskMapping = (
  moduleKey: 'Daily' | 'ReceiveRewards' | 'DivergentUniverse' | 'CurrencyWars'
): HSREngine | undefined => {
  const mapping: HSRTaskMapping = {
    ...DEFAULT_HSR_TASK_MAPPING,
    ...(scriptConfig.value?.TaskMapping ?? {}),
    ...(managedConfigSnapshot.value?.task_mapping ?? {}),
    ...(formData.Managed.TaskMapping ?? {}),
  }
  return (
    resolveCapabilityTaskEngine(capabilitySnapshot.value, moduleKey, mapping[moduleKey]) ??
    resolveTaskMappingValue(mapping[moduleKey], effectiveEngines.value)
  )
}

const loadHsrStageOptions = async () => {
  if (!scriptId || !scriptConfig.value) return
  const engine = getTaskMapping('Daily')
  if (!engine) {
    hsrStageOptions.value = null
    hsrStageOptionsError.value = ''
    hsrStageOptionsLoading.value = false
    return
  }
  hsrStageOptionsLoading.value = true
  hsrStageOptionsError.value = ''
  try {
    const pluginData = await hsrPluginApi.getStageOptions(scriptId, engine, userId || undefined)
    const data: HSRDynamicStageOptionsData = {
      engine,
      categories: pluginData.categories.map(category => ({
        categoryKey: category.key,
        categoryLabel: category.label,
        options: category.options.map(option => ({
          label: option.label,
          detail: option.detail,
          value: option.id,
          categoryKey: category.key,
          categoryLabel: category.label,
          cost: option.cost,
          maxCount: option.max_count,
          ...(option.native_payload || {}),
        })),
      })),
    }
    const optionCount = (data.categories ?? []).reduce((sum, category) => {
      return sum + (category.options?.length ?? 0)
    }, 0)
    if (!data.categories?.length || optionCount <= 0) {
      throw new Error('外部脚本未暴露可用副本选项')
    }
    hsrStageOptions.value = data
    logger.info(`HSR 体力副本动态选项加载成功: ${engine}`)
  } catch (error) {
    hsrStageOptions.value = null
    const errorMsg = error instanceof Error ? error.message : String(error)
    hsrStageOptionsError.value = `HSR 体力副本选项读取失败：${errorMsg}。请检查脚本路径或脚本版本。`
    logger.error(`HSR 体力副本动态选项加载失败: ${errorMsg}`)
  } finally {
    hsrStageOptionsLoading.value = false
  }
}

watch(
  () => managedConfigSnapshot.value?.task_mapping?.Daily,
  () => {
    void loadHsrStageOptions()
  }
)

const handleTaskSwitchToggle = async (moduleKey: string, enabled: boolean) => {
  ;(formData.TaskSwitch as Record<string, boolean | null | undefined>)[moduleKey] = enabled
  const userData: Record<string, unknown> = { TaskSwitch: { [moduleKey]: enabled } }
  if (isInitializing.value || isSaving.value || !userId) return
  isSaving.value = true
  try {
    const saved = await updateUser(scriptId, userId, userData)
    if (saved) {
      logger.info(`用户配置已保存: TaskSwitch.${moduleKey}=${enabled}`)
    } else {
      logger.error(`保存失败: TaskSwitch.${moduleKey}`)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存失败: ${errorMsg}`)
  } finally {
    isSaving.value = false
  }
}

const formData = reactive<HSRUserConfigData>({
  Info: {
    Name: '',
    Status: true,
    Server: 'CN-Official',
    RemainedDay: -1,
    Notes: '',
  },
  SRA: { Id: '', Password: '' },
  Stage: {
    Channel: 'CalyxGolden',
    ScriptStage: {},
    ScriptEchoOfWar: {},
  },
  TaskSwitch: {
    Daily: false,
    ReceiveRewards: false,
    DivergentUniverse: false,
    CurrencyWars: false,
  },
  TaskOpt: {
    EchoOfWarWeekday: 'Monday',
  },
  Control: {
    Mode: 'managed',
    SRA: false,
    M7A: false,
  },
  Managed: {
    TaskMapping: {},
    Options: {},
  },
  Direct: {
    SRAConfig: '',
    M7AConfig: '',
    SRAImportedAt: '',
    M7AImportedAt: '',
    SRASource: '',
    M7ASource: '',
  },
  Data: {
    EchoOfWarCompletedThisWeek: false,
    EchoOfWarLastResetWeek: '',
    EchoOfWarLastCompletionDate: '',
    WeeklyCompletedThisWeek: false,
    WeeklyLastResetWeek: '',
    WeeklyLastCompletionDate: '',
    SRARedeemCodeFingerprint: '',
    M7ARedeemCodeFingerprint: '',
  },
})

const controlMode = computed<'managed' | 'direct'>(() =>
  formData.Control.Mode === 'direct' ? 'direct' : 'managed'
)
const dailyStageEngine = computed(() => getTaskMapping('Daily'))

const refreshNativeControls = async () => {
  await Promise.all(
    [...effectiveEngines.value].map(async engine => {
      try {
        nativeControls[engine] = await hsrPluginApi.getNativeConfigs(scriptId, engine)
      } catch (error) {
        logger.warn(`读取 ${engine} 原生配置状态失败: ${String(error)}`)
      }
    })
  )
}

const loadManagedConfig = async () => {
  if (!userId) return
  managedConfigLoading.value = true
  try {
    managedConfigSnapshot.value = await hsrPluginApi.getManagedConfig(scriptId, userId)
    formData.Managed.TaskMapping = {
      ...(managedConfigSnapshot.value.task_mapping ?? {}),
      ...(formData.Managed.TaskMapping ?? {}),
    }
    await loadHsrStageOptions()
  } catch (error) {
    managedConfigSnapshot.value = null
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`HSR 动态任务配置加载失败: ${errorMsg}`)
    message.error(`动态读取原生配置失败：${errorMsg}`)
  } finally {
    managedConfigLoading.value = false
  }
}

const handleManagedSourceImport = async () => {
  if (!userId || managedConfigLoading.value || isSaving.value) return
  const previousOptions = formData.Managed.Options
  const saved = await handleFieldSave('Managed.Options', {})
  if (!saved) {
    formData.Managed.Options = previousOptions
    message.error('从源配置导入失败')
    return
  }
  await loadManagedConfig()
  message.success('已从当前 SRA / 三月七助手源配置导入')
}

const handleControlModeChange = async (value: string | number) => {
  if ((value !== 'managed' && value !== 'direct') || isSaving.value) return
  const previousMode = formData.Control.Mode
  formData.Control.Mode = value
  const saved = await handleFieldSave('Control.Mode', value)
  if (!saved) {
    formData.Control.Mode = previousMode
    message.error('运行模式保存失败，请重试')
    return
  }
  if (value === 'managed') await loadManagedConfig()
  else await refreshNativeControls()
}

const handleManagedMappingChange = async (task: string, engine: HSREngine) => {
  const mapping = { ...(formData.Managed.TaskMapping ?? {}), [task]: engine }
  formData.Managed.TaskMapping = mapping
  if (managedConfigSnapshot.value) {
    managedConfigSnapshot.value.task_mapping = {
      ...managedConfigSnapshot.value.task_mapping,
      [task]: engine,
    }
  }
  await handleFieldSave('Managed.TaskMapping', mapping)
  if (task === 'Daily') await loadHsrStageOptions()
}

const handleManagedFieldChange = async (
  engine: HSREngine,
  task: string,
  key: string,
  value: unknown
) => {
  const options = { ...(formData.Managed.Options ?? {}) }
  const engineOptions = { ...(options[engine] ?? {}) }
  const taskOptions = { ...(engineOptions[task] ?? {}), [key]: value }
  engineOptions[task] = taskOptions
  options[engine] = engineOptions
  formData.Managed.Options = options

  const field = managedConfigSnapshot.value?.tasks
    .find(item => item.key === task)
    ?.forms?.[engine]?.fields.find(item => item.key === key)
  if (field) field.value = value
  await handleFieldSave('Managed.Options', options)
}

const handleDirectEngineToggle = async (engine: HSREngine, enabled: boolean) => {
  formData.Control[engine] = enabled
  await handleFieldSave(`Control.${engine}`, enabled)
}

const handleDirectConfigImport = async (engine: HSREngine) => {
  if (!userId || importingDirectEngine.value) return
  importingDirectEngine.value = engine
  try {
    const result = await hsrPluginApi.importDirectConfig(scriptId, userId, engine)
    formData.Direct[`${engine}ImportedAt`] = result.imported_at
    formData.Direct[`${engine}Source`] = result.source
    message.success(`${engine} 原生配置已导入当前用户`)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    message.error(`${engine} 配置导入失败：${errorMsg}`)
  } finally {
    importingDirectEngine.value = null
  }
}

const handleOpenNativeConfigurator = async (engine: HSREngine) => {
  if (openingConfiguratorEngine.value) return
  openingConfiguratorEngine.value = engine
  try {
    nativeControls[engine] = await hsrPluginApi.openNativeConfigurator(scriptId, engine)
    message.info(`已打开 ${engine} 配置器；保存并关闭后，再点击“从脚本原有配置导入”`)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    message.error(`打开 ${engine} 配置器失败：${errorMsg}`)
  } finally {
    openingConfiguratorEngine.value = null
  }
}

// EchoOfWarWeekday 变更已下沉到 StageConfigSection.vue（体力配置区）。

const eowCompletedThisWeek = computed(() => {
  return (
    !!formData.Data.EchoOfWarCompletedThisWeek &&
    formData.Data.EchoOfWarLastResetWeek === getCurrentISOWeek()
  )
})

const saveUserPatch = async (
  userData: Record<string, unknown>,
  successLog: string,
  failureLog: string
) => {
  const saved = await updateUser(scriptId, userId, userData)
  if (saved) {
    logger.info(successLog)
  } else {
    logger.error(failureLog)
  }
  return saved
}

// 历战余响 — 标记已完成
// 必须同时写入当前 ISO 周：后端 resolver 用 LastResetWeek == 当前 ISO 周
const markEowCompleted = async () => {
  const today = getCurrentDate()
  const isoWeek = getCurrentISOWeek()
  formData.Data.EchoOfWarCompletedThisWeek = true
  formData.Data.EchoOfWarLastCompletionDate = today
  formData.Data.EchoOfWarLastResetWeek = isoWeek
  await saveUserPatch(
    {
      Data: {
        EchoOfWarCompletedThisWeek: true,
        EchoOfWarLastCompletionDate: today,
        EchoOfWarLastResetWeek: isoWeek,
      },
    },
    `历战余响标记已完成 (${isoWeek})`,
    '历战余响标记已完成失败'
  )
}

// 历战余响 — 标记未完成
const resetEowProgress = async () => {
  const isoWeek = getCurrentISOWeek()
  formData.Data.EchoOfWarCompletedThisWeek = false
  formData.Data.EchoOfWarLastResetWeek = isoWeek
  formData.Data.EchoOfWarLastCompletionDate = ''
  await saveUserPatch(
    {
      Data: {
        EchoOfWarCompletedThisWeek: false,
        EchoOfWarLastResetWeek: isoWeek,
        EchoOfWarLastCompletionDate: '',
      },
    },
    `历战余响已标记未完成（${isoWeek}）`,
    '历战余响标记未完成失败'
  )
}

// 周常 — 标记完成
// 必须同时写入当前 ISO 周：后端 resolver 用 WeeklyLastResetWeek == 当前 ISO 周
// 判断 Data 是否属于本周，否则会按"新周已重置"把 done 重置为 False。
const markWeeklyCompleted = async () => {
  const today = getCurrentDate()
  const isoWeek = getCurrentISOWeek()
  formData.Data.WeeklyCompletedThisWeek = true
  formData.Data.WeeklyLastCompletionDate = today
  formData.Data.WeeklyLastResetWeek = isoWeek
  await saveUserPatch(
    {
      Data: {
        WeeklyCompletedThisWeek: true,
        WeeklyLastCompletionDate: today,
        WeeklyLastResetWeek: isoWeek,
      },
    },
    `周常标记完成 (${isoWeek})`,
    '周常标记完成失败'
  )
}

// 周常 — 重置
const resetWeeklyProgress = async () => {
  const isoWeek = getCurrentISOWeek()
  formData.Data.WeeklyCompletedThisWeek = false
  formData.Data.WeeklyLastResetWeek = isoWeek
  formData.Data.WeeklyLastCompletionDate = ''
  await saveUserPatch(
    {
      Data: {
        WeeklyCompletedThisWeek: false,
        WeeklyLastResetWeek: isoWeek,
        WeeklyLastCompletionDate: '',
      },
    },
    `周常已重置（新周：${isoWeek}）`,
    '周常重置失败'
  )
}

const handleFieldSave = async (key: string, value: unknown) => {
  const parts = key.split('.')
  let localTarget = formData as unknown as MutableRecord
  for (let i = 0; i < parts.length - 1; i++) {
    const part = parts[i]
    const next = localTarget[part]
    if (!next || typeof next !== 'object' || Array.isArray(next)) {
      localTarget[part] = {}
    }
    localTarget = localTarget[part] as MutableRecord
  }
  localTarget[parts[parts.length - 1]] = value

  if (isInitializing.value || isSaving.value || !userId) return false
  isSaving.value = true
  try {
    const userData: MutableRecord = {}
    let current = userData
    for (let i = 0; i < parts.length - 1; i++) {
      current[parts[i]] = {}
      current = current[parts[i]] as MutableRecord
    }
    current[parts[parts.length - 1]] = value
    const saved = await updateUser(scriptId, userId, userData)
    if (saved) {
      logger.info(`用户配置已保存: ${key}`)
    } else {
      logger.error(`保存失败: ${key}`)
    }
    return Boolean(saved)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存失败: ${errorMsg}`)
    return false
  } finally {
    isSaving.value = false
  }
}

const handleCancel = () => router.push('/scripts')

onMounted(async () => {
  pluginSystemSubscriptionId = subscribe(
    { id: WS_ID_PLUGIN_SYSTEM, type: WS_PLUGIN_SNAPSHOT_UPDATED },
    handlePluginSystemMessage
  )
  if (!scriptId) {
    message.error('缺少脚本ID参数')
    handleCancel()
    return
  }
  try {
    const script = await getScript(scriptId)
    if (!script) {
      message.error('脚本不存在')
      handleCancel()
      return
    }
    if (script.type !== 'HSR' || script.editor_kind !== 'plugin:automas_script_hsr') {
      message.error('当前脚本未启用 HSR 插件编辑器')
      handleCancel()
      return
    }
    scriptName.value = script.name
    scriptConfig.value = script.config as HSRScriptConfig
    capabilitySnapshot.value = await hsrPluginApi.getCapabilities(scriptId)
    await refreshNativeControls()
    if (!isEdit.value && capabilitySnapshot.value.available === false) {
      message.warning(capabilitySnapshot.value.unavailable_reason || '请先配置可用的 HSR 引擎路径')
      handleCancel()
      return
    }
    if (isEdit.value) {
      await loadUserData()
      if (controlMode.value === 'managed') await loadManagedConfig()
    } else {
      await createUserImmediately()
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载脚本信息失败: ${errorMsg}`)
    message.error('加载脚本信息失败')
  } finally {
    isInitializing.value = false
  }
})

onUnmounted(() => {
  if (pluginSystemSubscriptionId) unsubscribe(pluginSystemSubscriptionId)
})

const createUserImmediately = async () => {
  try {
    const result = await addUser(scriptId)
    if (result && result.userId) {
      userId = result.userId
      isEdit.value = true
      router.replace({
        name: 'HSRUserEdit',
        params: { scriptId, userId: result.userId },
      })
      await loadUserData()
      if (controlMode.value === 'managed') await loadManagedConfig()
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
    if (userResponse) {
      const userData = userResponse.find(item => item.id === userId)?.config as
        | Partial<HSRUserConfigData>
        | undefined
      if (userData) {
        if (userData.Info) formData.Info = { ...formData.Info, ...userData.Info }
        if (userData.SRA) formData.SRA = { ...formData.SRA, ...userData.SRA }
        if (userData.Stage) formData.Stage = { ...formData.Stage, ...userData.Stage }
        if (userData.TaskSwitch)
          formData.TaskSwitch = { ...formData.TaskSwitch, ...userData.TaskSwitch }
        if (userData.TaskOpt) formData.TaskOpt = { ...formData.TaskOpt, ...userData.TaskOpt }
        if (userData.Control) formData.Control = { ...formData.Control, ...userData.Control }
        if (userData.Managed) {
          formData.Managed = {
            TaskMapping: {
              ...(formData.Managed.TaskMapping ?? {}),
              ...(userData.Managed.TaskMapping ?? {}),
            },
            Options: {
              ...(formData.Managed.Options ?? {}),
              ...(userData.Managed.Options ?? {}),
            },
          }
        }
        if (userData.Direct) formData.Direct = { ...formData.Direct, ...userData.Direct }
        if (userData.Data) formData.Data = { ...formData.Data, ...userData.Data }
        logger.info('用户数据加载成功')
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
</script>

<style scoped>
.user-edit-container {
  padding: 32px;
  min-height: 100vh;
  background: var(--ant-color-bg-layout);
}

.user-edit-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  padding: 0 8px;
}

.breadcrumb {
  margin: 0;
}

.breadcrumb-link {
  color: var(--ant-color-text-secondary);
  text-decoration: none;
}

.breadcrumb-current {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
}

.breadcrumb-logo {
  width: 18px;
  height: 18px;
  object-fit: contain;
}

.user-edit-content {
  max-width: 1400px;
  margin: 0 auto;
}

.config-card {
  border-radius: 12px;
  box-shadow: none;
}

.config-card :deep(.ant-card-body) {
  padding: 32px;
}

.config-form {
  max-width: none;
}

.form-section {
  margin-bottom: 24px;
}

.control-mode-content {
  margin-bottom: 24px;
}

.control-mode-form-item {
  margin-bottom: 0;
}

.control-mode-select {
  width: 100%;
}

.notes-textarea {
  min-height: 72px;
  resize: vertical;
}

.mode-alert {
  margin-bottom: 16px;
}

.section-header {
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--ant-color-border-secondary);
}

.section-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 12px;
}

.section-header h3::before {
  content: '';
  width: 4px;
  height: 22px;
  background: var(--ant-color-primary);
  border-radius: 2px;
}

.form-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  font-size: 14px;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  font-size: 13px;
}

.modern-input,
.modern-input :deep(.ant-input),
.modern-input :deep(.ant-input-number) {
  border-radius: 8px;
  border: 2px solid var(--ant-color-border);
  background: var(--ant-color-bg-container);
}

.modern-input:focus,
.modern-input :deep(.ant-input:focus) {
  border-color: var(--ant-color-primary);
  box-shadow: 0 0 0 4px var(--ant-color-primary-bg);
}

.module-checkbox-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
}

.cancel-button {
  height: 40px;
}

.progress-group {
  display: flex;
  align-items: center;
  gap: 12px;
}

.progress-label {
  font-weight: 600;
  color: var(--ant-color-text);
  min-width: 48px;
}

.date-hint {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
  margin-left: 4px;
}
</style>
