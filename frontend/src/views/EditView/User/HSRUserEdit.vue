<template>
  <div class="user-edit-container">
    <UserEditHeader
      :script-id="scriptId"
      :script-name="scriptName"
      :is-edit="isEdit"
      script-edit-segment="hsr"
      :current-label="isEdit ? t('edit.editHsrUser') : t('edit.addHsrUser')"
      :logo-src="hsrLogo"
      @cancel="handleCancel"
    />

    <ConfigLockPanel :script-id="scriptId" content-class="user-edit-content">
      <a-card class="config-card">
        <a-alert
          v-if="capabilitySnapshot?.unavailable_reason && !visibleCapabilityWarnings.length"
          type="warning"
          show-icon
          :message="capabilitySnapshot.unavailable_reason"
          style="margin-bottom: 12px"
        />
        <a-alert
          v-for="warning in visibleCapabilityWarnings"
          :key="warning"
          type="warning"
          show-icon
          :message="warning"
          style="margin-bottom: 12px"
        />
        <a-form ref="formRef" :model="formData" layout="vertical" class="config-form">
          <!-- 基本信息 -->
          <div class="form-section form-section-flat">
            <div class="section-header">
              <h3>{{ t('edit.basicInfo') }}</h3>
              <!-- 体力配置区块隐藏（直控模式，或未给 Daily 配引擎）时，恢复入口兜底到这里 -->
              <div
                v-if="controlMode !== 'managed' || !dailyStageEngine"
                class="section-header-actions"
              >
                <a-button size="small" @click="restoreOpen = true">
                  <template #icon>
                    <HistoryOutlined />
                  </template>
                  {{ t('edit.configRestoreTitle') }}
                </a-button>
              </div>
            </div>
            <a-row :gutter="24">
              <a-col :span="8">
                <a-form-item>
                  <template #label>
                    <a-tooltip :title="t('edit.thisNameAlsoWritten')">
                      <span class="form-label"
                        >{{ t('edit.username') }} <QuestionCircleOutlined class="help-icon"
                      /></span>
                    </a-tooltip>
                  </template>
                  <a-input
                    v-model:value="formData.Info.Name"
                    size="large"
                    @blur="handleFieldSave('Info.Name', formData.Info.Name)"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="4">
                <a-form-item>
                  <template #label>
                    <span class="form-label">{{ t('edit.enabled2') }}</span>
                  </template>
                  <a-switch
                    v-model:checked="formData.Info.Status"
                    :checked-children="t('edit.enabled3')"
                    :un-checked-children="t('edit.disabled')"
                    @change="handleFieldSave('Info.Status', formData.Info.Status)"
                  />
                </a-form-item>
              </a-col>
              <!-- 账号密码只给 SRA StartGame 切号用；云·星穹铁道按用户分浏览器登录态，不需要 -->
              <a-col v-if="showCredentials" :span="6">
                <a-form-item>
                  <template #label>
                    <span class="form-label">{{ t('edit.account') }}</span>
                  </template>
                  <a-input
                    v-model:value="formData.Info.Id"
                    :placeholder="t('edit.enterAccount')"
                    size="large"
                    @blur="handleFieldSave('Info.Id', formData.Info.Id)"
                  />
                </a-form-item>
              </a-col>
              <a-col v-if="showCredentials" :span="6">
                <a-form-item>
                  <template #label>
                    <!-- 加密说明由原先的区块提示降为密码字段的悬停说明 -->
                    <a-tooltip :title="t('edit.whenSavingMasEncrypts')">
                      <span class="form-label"
                        >{{ t('edit.password') }} <QuestionCircleOutlined class="help-icon"
                      /></span>
                    </a-tooltip>
                  </template>
                  <a-input-password
                    v-model:value="formData.Info.Password"
                    :placeholder="t('edit.enterPassword')"
                    size="large"
                    @blur="handleFieldSave('Info.Password', formData.Info.Password)"
                  />
                </a-form-item>
              </a-col>
            </a-row>
            <!-- 云·星穹铁道：登录态在该用户自己的浏览器 profile 里，这里看状态、发起登录 -->
            <a-row v-if="isCloud && isEdit" :gutter="24" align="middle" class="cloud-login-row">
              <a-col :span="24">
                <div class="cloud-login-line" data-testid="hsr-cloud-login-line">
                  <span class="progress-label">{{ t('edit.hsrCloudLogin') }}</span>
                  <a-tag :color="cloudLastLogin ? 'green' : 'orange'">
                    {{
                      cloudLastLogin
                        ? t('edit.hsrCloudLoggedIn', { time: formatCloudLoginTime(cloudLastLogin) })
                        : t('edit.hsrCloudNotLoggedIn')
                    }}
                  </a-tag>
                  <a-tooltip :title="t('edit.hsrCloudLoginTip')">
                    <a-button
                      size="small"
                      :loading="cloudLoginLoading"
                      :disabled="configLocked"
                      data-testid="hsr-cloud-login-button"
                      @click="handleCloudLogin"
                    >
                      {{ t('edit.hsrCloudLoginButton') }}
                    </a-button>
                  </a-tooltip>
                </div>
              </a-col>
            </a-row>
            <a-row :gutter="24" style="margin-top: 8px">
              <!-- 只有一个服务器可选时不渲染下拉（字段仍保留在后端，留作扩展口） -->
              <a-col v-if="serverOptions.length > 1" :span="6">
                <a-form-item>
                  <template #label>
                    <span class="form-label">{{ t('edit.server') }}</span>
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
                    <a-tooltip :title="t('edit.daysLeft1Means')">
                      <span class="form-label"
                        >{{ t('edit.daysLeft') }} <QuestionCircleOutlined class="help-icon"
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
                <a-form-item>
                  <template #label>
                    <span class="form-label">{{ t('edit.note') }}</span>
                  </template>
                  <a-textarea
                    v-model:value="formData.Info.Notes"
                    :rows="2"
                    allow-clear
                    auto-size
                    class="notes-textarea"
                    @blur="handleFieldSave('Info.Notes', formData.Info.Notes)"
                  />
                </a-form-item>
              </a-col>
            </a-row>
            <!-- 页面上唯一的模式控件；三张卡片自带描述，不再另挂来源提示 -->
            <GeneralConfigModeSelector
              :model-value="formData.Info.Mode ?? '脚本'"
              :options="hsrConfigModeOptions"
              :disabled="isSaving"
              :saving="isSaving"
              alert-message=""
              @change="handleConfigModeChange"
            />
          </div>

          <!-- 关卡配置：「脚本」来源编辑脚本共享计划，「用户」来源编辑该用户自己的计划 -->
          <div v-if="controlMode === 'managed'" class="control-mode-content">
            <a-alert
              v-if="planOwner === 'script'"
              type="info"
              show-icon
              :message="t('edit.hsrSharedPlanHint')"
              class="mode-alert"
            />
            <StageConfigSection
              v-if="dailyStageEngine"
              :form-data="planForm"
              :loading="isSaving"
              :daily-engine="dailyStageEngine"
              :stage-options="hsrStageOptions"
              :stage-options-loading="hsrStageOptionsLoading"
              :stage-options-error="hsrStageOptionsError"
              @save="handleFieldSave"
              @open-restore="restoreOpen = true"
            />
            <ManagedTaskSection
              :snapshot="managedConfigSnapshot"
              :task-switch="planForm.TaskSwitch"
              :saving="isSaving"
              :loading="managedConfigLoading"
              :shared="planOwner === 'script'"
              :cloud="isCloud"
              :shown-warnings="visibleCapabilityWarnings"
              @reset-overrides="handleManagedOverridesReset"
              @task-toggle="handleTaskSwitchToggle"
              @mapping-change="handleManagedMappingChange"
              @field-change="handleManagedFieldChange"
              @clear-invalid-overrides="handleManagedInvalidOverridesClear"
            />
          </div>
          <div v-else class="control-mode-content">
            <DirectControlSection
              :available-engines="directEngineCards"
              :cloud="isCloud"
              :control="formData.Control"
              :saving="isSaving"
              @toggle="handleDirectEngineToggle"
            />
          </div>

          <!-- 进度与重置（完成态恒按用户记，脚本 / 用户来源都显示；历战余响开始日在体力配置区） -->
          <div v-if="formData.Info.Mode !== '直控'" class="form-section">
            <div class="section-header">
              <h3>{{ t('edit.progressReset') }}</h3>
            </div>

            <!-- 历战余响进度 -->
            <a-row :gutter="24" align="middle">
              <a-col :span="10">
                <div class="progress-group">
                  <span class="progress-label">{{ t('edit.echoOfWar') }}</span>
                  <a-tag :color="eowCompletedThisWeek ? 'green' : 'orange'">
                    {{ eowCompletedThisWeek ? t('edit.hsrWeekDone') : t('edit.hsrWeekNotDone') }}
                  </a-tag>
                  <span
                    v-if="hasValidCompletionDate(formData.Data.EchoOfWarLastCompletionDate)"
                    class="date-hint"
                  >
                    {{
                      t('edit.hsrLastCompleted', {
                        date: formData.Data.EchoOfWarLastCompletionDate,
                      })
                    }}
                  </span>
                </div>
              </a-col>
              <a-col :span="14">
                <a-space>
                  <a-button size="small" :disabled="eowCompletedThisWeek" @click="markEowCompleted">
                    {{ t('edit.markAsDone') }}
                  </a-button>
                  <a-button size="small" danger @click="resetEowProgress">{{
                    t('edit.reset')
                  }}</a-button>
                </a-space>
              </a-col>
            </a-row>

            <!-- 周常进度 -->
            <a-row :gutter="24" align="middle" style="margin-top: 16px">
              <a-col :span="10">
                <div class="progress-group">
                  <span class="progress-label">{{ t('edit.weekly') }}</span>
                  <a-tag :color="formData.Data.WeeklyCompletedThisWeek ? 'green' : 'orange'">
                    {{
                      formData.Data.WeeklyCompletedThisWeek
                        ? t('edit.hsrWeekDone')
                        : t('edit.hsrWeekNotDone')
                    }}
                  </a-tag>
                  <span
                    v-if="hasValidCompletionDate(formData.Data.WeeklyLastCompletionDate)"
                    class="date-hint"
                  >
                    {{
                      t('edit.hsrLastCompleted', { date: formData.Data.WeeklyLastCompletionDate })
                    }}
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
                    {{ t('edit.markAsDone') }}
                  </a-button>
                  <a-button size="small" danger @click="resetWeeklyProgress">{{
                    t('edit.reset')
                  }}</a-button>
                </a-space>
              </a-col>
            </a-row>
          </div>

          <!-- 额外脚本组件 -->
          <ExtraScriptSection
            v-model:form-data="formData"
            :loading="isSaving"
            @save="handleFieldSave"
          />

          <UserNotifyConfig
            v-model="formData.Notify"
            :loading="isSaving"
            :script-id="scriptId"
            :user-id="userId"
            @save="handleFieldSave"
          />
        </a-form>
      </a-card>
    </ConfigLockPanel>

    <!-- ══ 配置恢复（通用组件：MAS 用户字段在前、HSR 原生配置在后）══ -->
    <ConfigRestoreSection
      v-model:open="restoreOpen"
      :disabled="configLocked"
      :script-name="HSR_DISPLAY_NAME"
      :targets="restoreTargets"
      :api="restoreApi"
      :user-desc="t('edit.hsrConfigRestoreUserDesc')"
      :script-desc="t('edit.hsrConfigRestoreScriptDesc')"
      :on-restored="handleRestored"
    >
      <!-- mas 备份为字段侧车分区、native 备份为两引擎文件清单 -->
      <template #preview="{ raw }">
        <a-empty
          v-if="!previewSections(raw).length"
          :description="t('edit.configRestorePreviewEmpty')"
        />
        <div v-else>
          <template v-for="s in previewSections(raw)" :key="s.name">
            <h4 class="hsr-preview-title">{{ s.label }}</h4>
            <a-descriptions
              v-if="s.rows && s.rows.length"
              :column="1"
              size="small"
              bordered
              class="hsr-preview-box"
            >
              <a-descriptions-item v-for="row in s.rows" :key="row.key" :label="row.key">
                {{ row.value }}
              </a-descriptions-item>
            </a-descriptions>
          </template>
        </div>
      </template>
    </ConfigRestoreSection>
  </div>
</template>

<script setup lang="ts">
import ConfigLockPanel from '@/components/ConfigLockPanel.vue'
import { useScriptConfigLock } from '@/composables/useScriptConfigLock'
import { useI18n } from 'vue-i18n'
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { HistoryOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import hsrLogo from '@/assets/hsr.png'
import UserEditHeader from '@/components/UserEditHeader.vue'
import UserNotifyConfig from '@/components/UserNotifyConfig.vue'
import ExtraScriptSection from '@/components/ExtraScriptSection.vue'
import ConfigRestoreSection from '@/views/EditView/User/components/ConfigRestoreSection.vue'
import { Service } from '@/api'
import { useUserApi } from '@/composables/useUserApi'
import { useScriptApi } from '@/composables/useScriptApi'
import { useSaveQueue } from '@/composables/useSaveQueue'
import {
  filterHSRCapabilityWarnings,
  getHSRCloudLastLogin,
  useHSRPluginApi,
  type HSRCapabilitySnapshot,
  type HSRManagedConfigSnapshot,
  type HSREngine,
  type HSRPlanOwner,
} from '@/composables/useHSRPluginApi'
import type { HSRConfig_TaskMapping } from '@/api'
import { DEFAULT_HSR_TASK_MAPPING, resolveTaskMappingValue } from '@/types/script'
import type { HSRScriptConfig } from '@/types/script'
import StageConfigSection from './HSRUserEdit/StageConfigSection.vue'
import GeneralConfigModeSelector from '@/views/EditView/User/GeneralConfigModeSelector.vue'
import type {
  HSRDynamicStageOptionsData,
  HSRPlanData,
  HSRUserConfigData,
} from './HSRUserEdit/types'
import { buildHSRCapabilityView, resolveDirectEngineCards } from './HSRUserEdit/capabilityView'
import DirectControlSection from './HSRUserEdit/DirectControlSection.vue'
import ManagedTaskSection from './HSRUserEdit/ManagedTaskSection.vue'

const { t } = useI18n()

/**
 * 游戏服务器口径的「现在」：星铁在服务器时间（UTC+8）周一 04:00 重置，等价于 UTC+4 的
 * 零点。后端 HSRAutoProxyTask._period_markers 就是按 UTC+4 算日期和 ISO 周的，这里必须
 * 用同一口径——按本机时区算的话，跨周边界时前端写下的周标记和后端判定的周对不上：
 * 页面显示「本周已完成」，运行时却当成新一周照样去打。
 *
 * 全程用 UTC 取值（在时间戳上加偏移后读 getUTC*），顺带避开本机夏令时对天数差的干扰。
 */
const nowAtServerDayBoundary = (): Date => new Date(Date.now() + 4 * 3600 * 1000)

const getCurrentISOWeek = (): string => {
  const d = nowAtServerDayBoundary()
  const dayNum = d.getUTCDay() || 7
  const thursday = new Date(d)
  thursday.setUTCDate(d.getUTCDate() + 4 - dayNum)
  const yearStart = new Date(Date.UTC(thursday.getUTCFullYear(), 0, 1))
  const weekNo = Math.ceil(((thursday.getTime() - yearStart.getTime()) / 86400000 + 1) / 7)
  return `${thursday.getUTCFullYear()}-W${String(weekNo).padStart(2, '0')}`
}

const getCurrentDate = (): string => {
  const d = nowAtServerDayBoundary()
  const yyyy = d.getUTCFullYear()
  const mm = String(d.getUTCMonth() + 1).padStart(2, '0')
  const dd = String(d.getUTCDate()).padStart(2, '0')
  return `${yyyy}-${mm}-${dd}`
}

const logger = window.electronAPI.getLogger('HSR 用户编辑')

const route = useRoute()
const router = useRouter()
const { addUser, updateUser, getUsers } = useUserApi()
const { getScript, updateScript } = useScriptApi()
const hsrPluginApi = useHSRPluginApi()

const isInitializing = ref(true)
// 保存串行队列：连续改动按序写回，不再被布尔互斥丢掉
const { isSaving, enqueue } = useSaveQueue()

// 一份计划的初始值（加载前的占位）。用户自己的计划与脚本共享计划形状相同。
const createDefaultPlan = (): HSRPlanData => ({
  Stage: {
    Channel: 'CalyxGolden',
    ScriptStage: '{ }',
    ScriptEchoOfWar: '{ }',
  },
  TaskSwitch: {
    Daily: true,
    ReceiveRewards: false,
    DivergentUniverse: false,
    CurrencyWars: false,
  },
  TaskOpt: {
    EchoOfWarWeekday: 'Monday',
  },
  Managed: {
    TaskMapping: {},
    Options: {},
  },
})

// Initialize the reactive form before any computed/watch that can evaluate it
// during setup.  Keeping this declaration first avoids a browser TDZ error.
const formData = reactive<HSRUserConfigData>({
  Info: {
    Name: '',
    Status: true,
    Id: '',
    Password: '',
    // 配置来源三态（脚本/用户/直控）是页面上唯一的模式轴；新建用户默认「脚本」，与后端一致
    Mode: '脚本',
    // HSR 按方案 B 声明不支持快速配置（模型/schema 字段保留但运行时无消费，
    // native_control.py 已声明），前端不渲染快速配置开关，故不设 IfQuickConfig 默认值
    Server: 'CN-Official',
    RemainedDay: -1,
    IfScriptBeforeTask: false,
    ScriptBeforeTask: '',
    IfScriptAfterTask: false,
    ScriptAfterTask: '',
    Notes: '',
  },
  ...createDefaultPlan(),
  Data: {
    EchoOfWarCompletedThisWeek: false,
    EchoOfWarLastResetWeek: '',
    EchoOfWarLastCompletionDate: '',
    WeeklyCompletedThisWeek: false,
    WeeklyLastResetWeek: '',
    WeeklyLastCompletionDate: '',
  },
  Notify: {
    Enabled: false,
    IfSendStatistic: false,
    IfSendMail: false,
    ToAddress: '',
    IfServerChan: false,
    ServerChanKey: '',
  },
  Control: {
    SRA: false,
    M7A: false,
  },
})

// 脚本共享计划：脚本配置上与用户计划同名的几组，本脚本下所有「脚本」来源用户共用
const sharedPlan = reactive<HSRPlanData>(createDefaultPlan())

const scriptId = route.params.scriptId as string
let userId = route.params.userId as string
const isEdit = ref(!!userId)
const { configLocked } = useScriptConfigLock(() => scriptId)

const scriptName = ref('')
const scriptConfig = ref<HSRScriptConfig | null>(null)
const capabilitySnapshot = ref<HSRCapabilitySnapshot | null>(null)
const visibleCapabilityWarnings = computed(() =>
  filterHSRCapabilityWarnings(capabilitySnapshot.value?.warnings)
)
const capabilityView = computed(() => buildHSRCapabilityView(capabilitySnapshot.value))
const effectiveEngines = computed(() => capabilityView.value.effectiveEngines)
// 云·星穹铁道只用三月七：直控只剩三月七可选，引擎分配恒为三月七
const isCloud = computed(() => scriptConfig.value?.Game?.Platform === 'Cloud')
const directEngines = computed<HSREngine[]>(() =>
  isCloud.value
    ? effectiveEngines.value.filter(engine => engine === 'M7A')
    : [...effectiveEngines.value]
)
// 直控区块的开关：可选引擎之外，已勾选的也要给开关，否则后端因它拒绝运行时无从关掉
const directEngineCards = computed<HSREngine[]>(() =>
  resolveDirectEngineCards(directEngines.value, formData.Control)
)
const cloudLastLogin = computed(() =>
  userId ? getHSRCloudLastLogin(scriptConfig.value?.Cloud?.LastLogin, userId) : ''
)
const cloudLoginLoading = ref(false)

const formatCloudLoginTime = (value: string): string => {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

const handleCloudLogin = async () => {
  if (!userId || cloudLoginLoading.value) return
  cloudLoginLoading.value = true
  try {
    await hsrPluginApi.cloudLogin(scriptId, userId)
    message.success(t('edit.hsrCloudLoginSuccess'))
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error)
    logger.error(`云·星穹铁道登录失败: ${reason}`)
    message.error(t('edit.hsrCloudLoginFailed', { reason }))
  } finally {
    cloudLoginLoading.value = false
    // 登录时间由后端写进脚本配置，重拉一次让状态行跟上
    await refreshSharedPlan()
  }
}
const managedConfigSnapshot = ref<HSRManagedConfigSnapshot | null>(null)
const managedConfigLoading = ref(false)
const hsrStageOptions = ref<HSRDynamicStageOptionsData | null>(null)
const hsrStageOptionsLoading = ref(false)
const hsrStageOptionsError = ref('')

const serverOptions = computed(() => [
  { value: 'CN-Official', label: t('edit.hsrServerCnOfficial') },
])

// 配置来源三态卡片（value 为后端 Info.Mode 取值，驱动逻辑需保持原样；文案走词表）
// 脚本 = 本脚本下「脚本」来源用户共用一份任务配置；用户 = 该用户自己一份；直控 = 原样跑原生配置
const hsrConfigModeOptions: Array<{
  label: string
  value: '脚本' | '用户' | '直控'
  title: string
  description: string
  icon: 'database' | 'setting'
}> = [
  {
    label: t('edit.script'),
    value: '脚本',
    title: t('edit.script'),
    description: t('edit.hsrUseScriptShared'),
    icon: 'database',
  },
  {
    label: t('edit.user'),
    value: '用户',
    title: t('edit.user'),
    description: t('edit.useThisUserS'),
    icon: 'database',
  },
  {
    label: t('edit.directControl'),
    value: '直控',
    title: t('edit.directControl'),
    description: t('edit.useScriptSCurrent'),
    icon: 'setting',
  },
]

type MutableRecord = Record<string, unknown>

const parseJsonRecord = (value: unknown): Record<string, any> => {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, any>
  }
  if (typeof value === 'string') {
    try {
      const parsed = JSON.parse(value)
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        return parsed as Record<string, any>
      }
    } catch {
      // Legacy validators may return an empty or malformed JSON string.
    }
  }
  return {}
}

const stringifyJsonRecord = (value: unknown): string => JSON.stringify(parseJsonRecord(value))

const DEFAULT_COMPLETION_DATE = '2000-01-01'

const hasValidCompletionDate = (value?: string | null): boolean => {
  const date = String(value ?? '').trim()
  return date !== '' && date !== DEFAULT_COMPLETION_DATE
}

// 任务计划挂在谁身上，与后端 resolve_plan_owner 同一口径：直控没有 MAS 计划，
// 「用户」读写该用户自己的计划，其余（含空值）按「脚本」读写脚本共享计划。
const planOwner = computed<HSRPlanOwner | null>(() => {
  if (formData.Info.Mode === '直控') return null
  return formData.Info.Mode === '用户' ? 'user' : 'script'
})

// 体力配置 / 托管任务两个区块的数据源随 owner 切换
const planForm = computed<HSRPlanData>(() => (planOwner.value === 'script' ? sharedPlan : formData))

// 计划字段分组：脚本态下这些组（外加脚本级 TaskMapping）保存到脚本配置
const PLAN_GROUPS = new Set(['TaskSwitch', 'Stage', 'TaskOpt', 'Managed', 'TaskMapping'])

const applySharedPlan = (config: HSRScriptConfig | null) => {
  const defaults = createDefaultPlan()
  sharedPlan.Stage = { ...defaults.Stage, ...(config?.Stage ?? {}) } as HSRPlanData['Stage']
  sharedPlan.TaskSwitch = { ...defaults.TaskSwitch, ...(config?.TaskSwitch ?? {}) }
  sharedPlan.TaskOpt = { ...defaults.TaskOpt, ...(config?.TaskOpt ?? {}) }
  // 脚本级没有 Managed.TaskMapping：脚本态的引擎分配直接读写脚本 TaskMapping 组
  sharedPlan.Managed = { TaskMapping: {}, Options: parseJsonRecord(config?.Managed?.Options) }
}

// 切到「脚本」或恢复后重拉脚本配置，拿到其他用户可能刚改过的共享计划
const refreshSharedPlan = async () => {
  const script = await getScript(scriptId)
  if (!script) return
  scriptConfig.value = script.config as HSRScriptConfig
  applySharedPlan(scriptConfig.value)
}

// 返回体力模块的执行引擎（SRA 或 M7A）：脚本态只看脚本 TaskMapping（不允许用户级覆盖），
// 用户态再叠上该用户的 Managed.TaskMapping。
const getTaskMapping = (moduleKey: 'Daily'): HSREngine | undefined => {
  if (isCloud.value) return effectiveEngines.value.includes('M7A') ? 'M7A' : undefined
  const mapping: HSRConfig_TaskMapping = {
    ...DEFAULT_HSR_TASK_MAPPING,
    ...(scriptConfig.value?.TaskMapping ?? {}),
    ...(planOwner.value === 'script' ? {} : (formData.Managed?.TaskMapping ?? {})),
  }
  return resolveTaskMappingValue(mapping[moduleKey] ?? undefined, new Set(effectiveEngines.value))
}

// 同一组参数（引擎 + 用户）的在途请求只发一次，重复调用复用同一个 promise
let hsrStageOptionsRequest: { key: string; promise: Promise<void> } | null = null

const loadHsrStageOptions = async () => {
  if (!scriptId || !scriptConfig.value) return
  const engine = getTaskMapping('Daily')
  if (!engine) {
    hsrStageOptions.value = null
    hsrStageOptionsError.value = ''
    hsrStageOptionsLoading.value = false
    return
  }
  const requestKey = `${engine}|${userId || ''}`
  if (hsrStageOptionsRequest?.key === requestKey) return hsrStageOptionsRequest.promise
  const request = { key: requestKey, promise: fetchHsrStageOptions(engine) }
  hsrStageOptionsRequest = request
  try {
    await request.promise
  } finally {
    if (hsrStageOptionsRequest === request) hsrStageOptionsRequest = null
  }
}

const fetchHsrStageOptions = async (engine: HSREngine) => {
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

// getter 返回字符串而不是新数组，否则 formData.Managed 每次整体赋值都会触发一次重拉
watch(
  () =>
    `${planOwner.value ?? ''}|${isCloud.value}|${scriptConfig.value?.TaskMapping?.Daily ?? ''}|${formData.Managed?.TaskMapping?.Daily ?? ''}`,
  () => {
    void loadHsrStageOptions()
  }
)

const handleTaskSwitchToggle = async (moduleKey: string, enabled: boolean) => {
  await handleFieldSave(`TaskSwitch.${moduleKey}`, enabled)
}

// 运行形态只由配置来源派生：直控跑原生配置，其余由 MAS 按计划托管
const controlMode = computed<'managed' | 'direct'>(() =>
  formData.Info.Mode === '直控' ? 'direct' : 'managed'
)
const dailyStageEngine = computed(() => getTaskMapping('Daily'))
const showCredentials = computed(
  () => controlMode.value === 'managed' && effectiveEngines.value.includes('SRA') && !isCloud.value
)

const loadManagedConfig = async () => {
  if (!userId) return
  managedConfigLoading.value = true
  try {
    const snapshot = await hsrPluginApi.getManagedConfig(scriptId, userId)
    managedConfigSnapshot.value = snapshot
    if (snapshot.plan_owner && planOwner.value && snapshot.plan_owner !== planOwner.value) {
      logger.warn(`托管配置的计划归属与配置来源不一致: ${snapshot.plan_owner} / ${planOwner.value}`)
    }
    // 用户态沿用旧口径：把解析后的引擎分配并进该用户的 Managed.TaskMapping 本地副本；
    // 脚本态的引擎分配只在脚本 TaskMapping 组，不碰用户字段
    if (planOwner.value === 'user') {
      formData.Managed = {
        TaskMapping: {
          ...(managedConfigSnapshot.value.task_mapping ?? {}),
          ...(formData.Managed?.TaskMapping ?? {}),
        },
        Options: formData.Managed?.Options ?? {},
      }
    }
  } catch (error) {
    managedConfigSnapshot.value = null
    logger.warn(`HSR 动态任务配置加载失败: ${String(error)}`)
  } finally {
    managedConfigLoading.value = false
  }
}

// 「重置为源配置」：清空当前计划（脚本共享或该用户自己）在 MAS 里的全部 Managed.Options
// 覆盖值，之后表单和运行都按 SRA / 三月七当前配置走。确认弹窗在子组件里。
const handleManagedOverridesReset = async () => {
  if (!userId || managedConfigLoading.value) return
  const saved = await handleFieldSave('Managed.Options', {})
  if (!saved) {
    message.error(t('edit.couldNotResetManagedOverrides'))
    return
  }
  await loadManagedConfig()
  message.success(t('edit.managedOverridesReset'))
}

// 只剔掉后端报告为失效（原生配置里已没有、或类型对不上）的覆盖键，其余保留。
const handleManagedInvalidOverridesClear = async (
  engine: HSREngine,
  task: string,
  keys: string[]
) => {
  if (!userId || managedConfigLoading.value || keys.length === 0) return
  const plan = planForm.value
  const options = { ...(plan.Managed?.Options ?? {}) }
  const engineOptions = { ...(options[engine] ?? {}) }
  const taskOptions = { ...(engineOptions[task] ?? {}) }
  for (const key of keys) delete taskOptions[key]
  if (Object.keys(taskOptions).length > 0) engineOptions[task] = taskOptions
  else delete engineOptions[task]
  if (Object.keys(engineOptions).length > 0) options[engine] = engineOptions
  else delete options[engine]
  plan.Managed = { ...(plan.Managed ?? {}), Options: options }
  const saved = await handleFieldSave('Managed.Options', options)
  if (!saved) {
    message.error(t('edit.couldNotClearInvalidManagedOverrides'))
    return
  }
  await loadManagedConfig()
  message.success(t('edit.invalidManagedOverridesCleared', { n: keys.length }))
}

// 直控下没勾任何引擎时，按已配路径的引擎全开（后端的同名回落保留兜底）
const ensureDirectEnginesEnabled = async () => {
  const engines = directEngines.value
  if (!engines.length || engines.some(engine => Boolean(formData.Control?.[engine]))) return
  for (const engine of engines) await handleDirectEngineToggle(engine, true)
}

// 配置来源三态切换：校验 value ∈ 三态 → 赋值 Info.Mode → 真实保存 → 按新来源重拉数据。
// 脚本 ↔ 用户意味着计划 owner 变了，托管表单与副本下拉都要换到新 owner 的值。
const handleConfigModeChange = async (value: boolean | string) => {
  if (typeof value !== 'string' || !['脚本', '用户', '直控'].includes(value)) return
  const previousMode = formData.Info.Mode
  if (previousMode === value) return
  formData.Info.Mode = value as '脚本' | '用户' | '直控'
  const saved = await handleFieldSave('Info.Mode', formData.Info.Mode)
  if (!saved) {
    formData.Info.Mode = previousMode
    return
  }
  if (value === '直控') {
    await ensureDirectEnginesEnabled()
    return
  }
  if (value === '脚本') await refreshSharedPlan()
  await loadManagedConfig()
}

// 引擎分配：脚本态写脚本级 TaskMapping.<模块>（共享计划的一部分，不允许用户级覆盖），
// 用户态照旧写该用户的 Managed.TaskMapping。
const handleManagedMappingChange = async (task: string, engine: HSREngine) => {
  if (managedConfigSnapshot.value) {
    managedConfigSnapshot.value.task_mapping = {
      ...managedConfigSnapshot.value.task_mapping,
      [task]: engine,
    }
  }
  if (planOwner.value === 'script') {
    await handleFieldSave(`TaskMapping.${task}`, engine)
  } else {
    const mapping = { ...(formData.Managed?.TaskMapping ?? {}), [task]: engine }
    formData.Managed = { ...(formData.Managed ?? {}), TaskMapping: mapping }
    await handleFieldSave('Managed.TaskMapping', mapping)
  }
  if (task === 'Daily') await loadHsrStageOptions()
}

const handleManagedFieldChange = async (
  engine: HSREngine,
  task: string,
  key: string,
  value: unknown
) => {
  const plan = planForm.value
  const options = { ...(plan.Managed?.Options ?? {}) }
  const engineOptions = { ...(options[engine] ?? {}) }
  const taskOptions = { ...(engineOptions[task] ?? {}), [key]: value }
  engineOptions[task] = taskOptions
  options[engine] = engineOptions
  plan.Managed = { ...(plan.Managed ?? {}), Options: options }
  const field = managedConfigSnapshot.value?.tasks
    .find(item => item.key === task)
    ?.forms?.[engine]?.fields.find(item => item.key === key)
  if (field) field.value = value
  await handleFieldSave('Managed.Options', options)
}

const handleDirectEngineToggle = async (engine: HSREngine, enabled: boolean) => {
  if (!formData.Control) formData.Control = {}
  formData.Control[engine] = enabled
  await handleFieldSave(`Control.${engine}`, enabled)
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

// 按计划 owner 分流保存：脚本态的计划字段（TaskSwitch / Stage / TaskOpt / Managed.Options /
// 脚本级 TaskMapping）写脚本配置，其余（Info / Data / Notify / Control）以及用户态的一切写用户配置。
const handleFieldSave = async (key: string, value: unknown): Promise<boolean> => {
  const parts = key.split('.')
  const toScript = planOwner.value === 'script' && PLAN_GROUPS.has(parts[0])
  if (toScript && key === 'Managed.TaskMapping') {
    // 脚本态不允许用户级引擎覆盖，脚本级这一项也不开放写入
    logger.warn('脚本来源下忽略 Managed.TaskMapping 的保存')
    return false
  }
  if (!toScript && parts[0] === 'TaskMapping') {
    logger.warn(`用户来源下 ${key} 不属于用户配置，已忽略`)
    return false
  }
  let localTarget = (!toScript
    ? formData
    : parts[0] === 'TaskMapping'
      ? (scriptConfig.value ??= {} as HSRScriptConfig)
      : sharedPlan) as unknown as MutableRecord
  for (let i = 0; i < parts.length - 1; i++) {
    const part = parts[i]
    const next = localTarget[part]
    if (!next || typeof next !== 'object' || Array.isArray(next)) {
      localTarget[part] = {}
    }
    localTarget = localTarget[part] as MutableRecord
  }
  localTarget[parts[parts.length - 1]] = value

  if (isInitializing.value || !userId) return false
  return enqueue(async () => {
    try {
      const patch: MutableRecord = {}
      let current = patch
      for (let i = 0; i < parts.length - 1; i++) {
        current[parts[i]] = {}
        current = current[parts[i]] as MutableRecord
      }
      // 脚本级与用户级的这几项同样是 JSONValidator，两条保存路径都要先转成 JSON 字符串
      const isManagedJsonField =
        parts[0] === 'Managed' && (parts[1] === 'TaskMapping' || parts[1] === 'Options')
      const isStageJsonField =
        parts[0] === 'Stage' && (parts[1] === 'ScriptStage' || parts[1] === 'ScriptEchoOfWar')
      const persistedValue = isManagedJsonField
        ? stringifyJsonRecord(value)
        : isStageJsonField && typeof value !== 'string'
          ? JSON.stringify(value ?? {})
          : value
      current[parts[parts.length - 1]] = persistedValue
      const saved = toScript
        ? await updateScript(scriptId, patch)
        : await updateUser(scriptId, userId, patch)
      const target = toScript ? '脚本共享计划' : '用户配置'
      if (saved) {
        logger.info(`${target}已保存: ${key}`)
        return true
      } else {
        logger.error(`${target}保存失败: ${key}`)
        return false
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`保存失败: ${errorMsg}`)
      return false
    }
  }, key)
}

const handleCancel = () => router.push('/scripts')

const loadCapabilities = async () => {
  try {
    capabilitySnapshot.value = await hsrPluginApi.getCapabilities(scriptId)
  } catch (error) {
    // Raw old-dev has no plugin registry. Derive a useful capability view from
    // the two built-in script paths and leave the optional adapter endpoints
    // available for hosts that provide them.
    const configuredEngines: HSREngine[] = []
    if (scriptConfig.value?.Info?.M7APath) configuredEngines.push('M7A')
    if (scriptConfig.value?.Info?.SRAPath) configuredEngines.push('SRA')
    capabilitySnapshot.value = {
      revision: 0,
      available: configuredEngines.length > 0,
      unavailable_reason: configuredEngines.length ? null : '未配置 M7A 或 SRA 路径',
      candidate_engines: configuredEngines,
      configured_engines: configuredEngines,
      effective_engines: configuredEngines,
      adapters: [],
      tasks: [],
      warnings: [
        `HSR 能力端点不可用，已回退到内置脚本配置：${
          error instanceof Error ? error.message : String(error)
        }`,
      ],
    }
  }
}

// ══ 配置恢复（通用组件 props 供给：双目标 MAS 在前脚本在后）══
// 专项统一名（文案参数化用）：HSR 统一叫「hsr」
const HSR_DISPLAY_NAME = 'hsr'
const restoreOpen = ref(false)

const restoreTargets: Array<{ key: string; kind: 'user' | 'script' }> = [
  { key: 'mas', kind: 'user' },
  { key: 'native', kind: 'script' },
]

const restoreApi = {
  list: async (target: string) =>
    Service.listConfigBackupsApiApiScriptsBackupListGet(scriptId, userId, target),
  preview: async (target: string, time: string) =>
    Service.getConfigBackupPreviewApiApiScriptsBackupPreviewGet(scriptId, userId, time, target),
  restore: async (target: string, time: string) =>
    Service.restoreConfigBackupApiApiScriptsBackupRestorePost({
      scriptId,
      userId,
      time,
      target,
    }),
  readFile: async (target: string, time: string, path: string) =>
    Service.getConfigBackupFileApiApiScriptsBackupFileGet(scriptId, userId, time, target, path),
}

interface HSRPreviewRow {
  key: string
  value: string
}
interface HSRPreviewSection {
  name: string
  label: string
  rows?: HSRPreviewRow[]
}
const previewSections = (raw: unknown): HSRPreviewSection[] =>
  (raw as { sections?: HSRPreviewSection[] } | null)?.sections ?? []

// 一键恢复成功：mas 恢复回填字段（托管配置等，计划部分写回当前 owner），需重拉表单；
// native 恢复写两引擎原生配置，MAS 表单不受影响
const handleRestored = async (target: string) => {
  restoreOpen.value = false
  if (target === 'mas') {
    await loadUserData()
    if (planOwner.value === 'script') await refreshSharedPlan()
    if (controlMode.value === 'managed') await loadManagedConfig()
  }
}

// 编辑会话归档（进入/退出时机，指纹去重）：进入归档两引擎原生配置当前状态
// （MAS 触碰前原始态），退出归档 MAS 用户字段侧车终态（编辑会话包络）
const ensureHSRBackup = async (target: 'mas' | 'native') => {
  if (!userId) return
  try {
    const resp = await Service.ensureConfigBackupApiApiScriptsBackupEnsurePost({
      scriptId,
      userId,
      target,
    })
    if (resp.code !== 200) throw new Error(resp.message || t('edit.configRestoreEnsureFailed'))
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
    message.warning(t('edit.configRestoreEnsureFailed'))
  }
}

onMounted(async () => {
  if (!scriptId) {
    message.error(t('edit.missingScriptIdParameter'))
    handleCancel()
    return
  }
  try {
    const script = await getScript(scriptId)
    if (!script) {
      message.error(t('edit.scriptDoesNotExist2'))
      handleCancel()
      return
    }
    scriptName.value = script.name
    scriptConfig.value = script.config as HSRScriptConfig
    applySharedPlan(scriptConfig.value)
    await loadCapabilities()
    await loadHsrStageOptions()

    if (isEdit.value) {
      await loadUserData()
      if (controlMode.value === 'managed') await loadManagedConfig()
    } else {
      await createUserImmediately()
    }
    // 编辑界面进入：归档两引擎原生配置当前状态（须在 userId 就绪后）
    void ensureHSRBackup('native')
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载脚本信息失败: ${errorMsg}`)
    message.error(t('edit.couldNotLoadScript2'))
  } finally {
    isInitializing.value = false
  }
})

onUnmounted(() => {
  // 退出编辑页：归档 MAS 用户字段侧车终态（编辑会话包络；HSR 无遮罩会话）
  void ensureHSRBackup('mas')
})

const createUserImmediately = async () => {
  if (configLocked.value) return false

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
    if (userResponse && userResponse.code === 200) {
      const users = userResponse.data as Record<string, Partial<HSRUserConfigData> | undefined>
      const userData = users?.[userId]
      if (userData) {
        if (userData.Info) formData.Info = { ...formData.Info, ...userData.Info }
        if (userData.Stage) formData.Stage = { ...formData.Stage, ...userData.Stage }
        if (userData.TaskSwitch)
          formData.TaskSwitch = { ...formData.TaskSwitch, ...userData.TaskSwitch }
        if (userData.TaskOpt) formData.TaskOpt = { ...formData.TaskOpt, ...userData.TaskOpt }
        if (userData.Data) formData.Data = { ...formData.Data, ...userData.Data }
        if (userData.Notify) formData.Notify = { ...formData.Notify, ...userData.Notify }
        if (userData.Control)
          formData.Control = { ...(formData.Control ?? {}), ...userData.Control }
        if (userData.Managed) {
          formData.Managed = {
            TaskMapping: {
              ...(formData.Managed?.TaskMapping ?? {}),
              ...parseJsonRecord(userData.Managed.TaskMapping),
            },
            Options: {
              ...(formData.Managed?.Options ?? {}),
              ...parseJsonRecord(userData.Managed.Options),
            },
          }
        }
        logger.info('用户数据加载成功')
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
  }
}
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
  box-shadow: none;
}

.config-card :deep(.ant-card-body) {
  padding: 32px;
}

.config-form {
  max-width: none;
}

.form-section {
  margin-bottom: 12px;
  padding: 20px 24px;
  background: var(--ant-color-bg-container);
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 12px;
}

/* 基本信息与体力配置沿用插件版的无卡片布局；标题分隔线仍保留。 */
.form-section-flat {
  margin-bottom: 24px;
  padding: 0;
  background: transparent;
  border: 0;
  border-radius: 0;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 配置恢复预览（分区行；弹窗内滚动由通用组件负责） */
.hsr-preview-title {
  font-size: 15px;
  font-weight: 600;
  margin: 12px 0 8px;
  color: var(--ant-color-text);
}

.hsr-preview-box {
  margin-bottom: 8px;
}

.section-header h3 {
  font-size: 18px;
}

.section-header h3::before {
  height: 22px;
  background: var(--ant-color-primary);
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

.cloud-login-row {
  margin-top: 8px;
}

.cloud-login-line {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}
</style>
