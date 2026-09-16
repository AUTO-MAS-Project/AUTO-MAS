<template>
  <div class="user-edit-container">
    <!-- 原生 GUI 会话遮罩（MXU 配置会话 / 查看会话，公用组件对齐 ok-ww / MAA） -->
    <GuiSessionMask
      :open="showMaaEndConfigMask"
      :icon="SettingOutlined"
      :title="t('edit.maaendConfigurationProgress')"
      :description="`${t('edit.maaendConfigurationWindowOpen')}\n${t('edit.clickSaveConfigurationWhen')}`"
    >
      <template #actions>
        <a-button v-if="maaEndTaskId" type="primary" size="large" @click="handleSaveMaaEndConfig">
          {{ t('edit.saveConfiguration') }}
        </a-button>
      </template>
    </GuiSessionMask>
    <GuiSessionMask
      :open="showMaaEndViewMask"
      :icon="EyeOutlined"
      :title="t('edit.maaendViewingTitle')"
      :description="`${t('edit.maaendViewingDesc')}\n${t('edit.maaendViewingDesc2')}`"
    >
      <template #actions>
        <a-button
          v-if="maaEndTaskId"
          type="primary"
          size="large"
          :loading="stoppingMaaEndConfig"
          @click="handleCloseMaaEndView"
        >
          {{ t('edit.maaendViewClose') }}
        </a-button>
      </template>
    </GuiSessionMask>

    <MaaEndUserEditHeader
      :script-id="scriptId"
      :script-name="scriptName"
      :is-edit="isEdit"
      @handle-cancel="handleCancel"
    />

    <div class="user-edit-content">
      <div class="page-layout">
        <a-form
          ref="formRef"
          :model="formData"
          :rules="rules"
          layout="vertical"
          class="config-form sections-column"
        >
          <a-card id="section-basic" class="section-card">
            <template #title>{{ t('edit.basicInfo') }}</template>
            <BasicInfoSection
              v-model:form-data="formData"
              :loading="loading"
              :resource-options="resourceOptions"
              :show-resource="controllerProtocol === 'Adb' && controllerType !== 'CloudADB'"
              @save="handleFieldSave"
            />
          </a-card>

          <a-card id="section-source" class="section-card">
            <template #title>{{ t('edit.configurationSource') }}</template>
            <ConfigSourceSection
              v-model:form-data="formData"
              :loading="loading"
              :config-loading="maaEndConfigLoading"
              :import-loading="maaEndImportLoading"
              :show-config-mask="showMaaEndConfigMask"
              @configure="handleMaaEndConfig"
              @import-config="handleImportMaaEndConfig"
              @script-config="handleScriptConfig"
              @mode-change="handleConfigModeChange"
            />
          </a-card>

          <a-flex id="section-task" justify="space-between" align="center" wrap="wrap" gap="small">
            <h3>{{ t('edit.taskConfiguration') }}</h3>
            <a-space>
              <a-button
                v-if="formData.Info.IfQuickConfig && isSanityPlanMode"
                type="link"
                class="plans-button"
                @click="handleGoToPlans"
              >
                <template #icon><CalendarOutlined /></template>
                {{ t('edit.goPlan') }}
              </a-button>
              <span>{{ t('edit.enableQuickConfiguration') }}</span>
              <a-switch
                :checked="formData.Info.IfQuickConfig"
                :disabled="
                  loading || isSaving || (!presetSupported && !formData.Info.IfQuickConfig)
                "
                :aria-label="t('edit.enableQuickConfiguration')"
                @change="handleQuickConfigChange"
              />
              <a-button size="small" @click="openRestoreModal">
                <template #icon><HistoryOutlined /></template>
                {{ t('edit.configRestoreTitle') }}
              </a-button>
            </a-space>
          </a-flex>
          <a-card v-if="formData.Info.IfQuickConfig" class="section-card">
            <TaskConfigSection
              :form-data="formData"
              :loading="loading"
              :if-quick-config="formData.Info.IfQuickConfig"
              :essence-location-options="essenceLocationOptions"
              :essence-menu-options="essenceMenuOptions"
              :essence-target-weapon-groups="essenceTargetWeaponGroups"
              :options-loading="maaEndOptionsLoading"
              :options-loaded="maaEndOptionsLoaded"
              :is-plan-mode="isSanityPlanMode"
              :sanity-mode-options="sanityModeOptions"
              :plan-mode-config="planModeConfig"
              @save="handleFieldSave"
              @save-batch="handleFieldsSave"
            />
          </a-card>

          <a-card v-if="formData.Info.IfQuickConfig" id="section-collect" class="section-card">
            <template #title>{{ t('edit.maaEndAutoCollectConfig') }}</template>
            <AutoCollectConfigSection
              :groups="autoCollectGroups"
              :options-loading="maaEndOptionsLoading"
              :form-data="formData"
              :loading="loading"
              @save="handleFieldSave"
            />
          </a-card>

          <a-card v-if="formData.Info.IfQuickConfig" id="section-delivery" class="section-card">
            <template #title>{{ t('edit.maaEndDeliveryConfig') }}</template>
            <DeliveryConfigSection
              :form-data="formData"
              :loading="loading"
              @save="handleFieldSave"
            />
          </a-card>

          <a-collapse id="section-limits" class="optional-section" :bordered="false">
            <a-collapse-panel key="limits" :header="t('edit.maaEndDailyOnceTasks')">
              <DailyOnceSection
                :value="formData.Task.DailyOnceTasks"
                :loading="loading"
                @save="handleFieldSave('Task.DailyOnceTasks', $event)"
              />
            </a-collapse-panel>
          </a-collapse>

          <a-collapse id="section-script" class="optional-section" :bordered="false">
            <a-collapse-panel key="script" :header="t('comp.extraScripts')">
              <ExtraScriptSection
                v-model:form-data="formData"
                :loading="loading"
                hide-section-header
                @save="handleFieldSave"
              />
            </a-collapse-panel>
          </a-collapse>

          <a-collapse id="section-notify" class="optional-section" :bordered="false">
            <a-collapse-panel key="notify" :header="t('edit.notificationSettings')">
              <UserNotifyConfig
                v-model="formData.Notify"
                :loading="loading"
                :script-id="scriptId"
                :user-id="userId"
                hide-section-header
                @save="handleFieldSave"
              />
            </a-collapse-panel>
          </a-collapse>
        </a-form>

        <aside class="anchor-sidebar">
          <!-- 页内目录只滚动内容，避免锚点覆盖应用的 hash 路由。 -->
          <a-anchor
            :items="anchorItems"
            :affix="false"
            :offset-top="96"
            :get-container="getAnchorContainer"
            @click.prevent
          />
        </aside>
      </div>
    </div>

    <!-- ══ 配置恢复（通用组件：MAS 用户配置在前、MaaEnd 原生配置在后）══ -->
    <ConfigRestoreSection
      v-model:open="restoreOpen"
      :script-name="MAAEND_DISPLAY_NAME"
      :targets="restoreTargets"
      :api="restoreApi"
      :script-desc="t('edit.maaendConfigRestoreScriptDesc')"
      :on-restored="handleRestored"
      :on-detail="handleRestoreView"
    >
      <!-- mas 备份为快速配置侧车、native 备份为 mxu 配置摘要，共用文件集插槽 -->
      <template #preview="{ raw }">
        <a-empty
          v-if="!previewFiles(raw).length"
          :description="t('edit.configRestorePreviewEmpty')"
        />
        <div v-else>
          <template v-for="f in previewFiles(raw)" :key="f.name">
            <h4 class="maaend-preview-title">{{ f.label }}</h4>
            <a-descriptions :column="1" size="small" bordered class="maaend-preview-box">
              <a-descriptions-item v-for="row in f.summary" :key="row.key" :label="row.key">
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
import { useI18n } from 'vue-i18n'
import { computed, h, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import {
  CalendarOutlined,
  EyeOutlined,
  HistoryOutlined,
  SettingOutlined,
} from '@ant-design/icons-vue'
import type { FormInstance, Rule } from 'ant-design-vue/es/form'
import type { ComboBoxItem } from '@/api'
import { Service } from '@/api'
import { PlanComboxIn } from '@/api/models/PlanComboxIn'
import { navigateTo } from '@/router'
import { useUserApi } from '@/composables/useUserApi'
import { useScriptApi } from '@/composables/useScriptApi'
import { useMaaEndGuiSession } from '@/composables/useMaaEndGuiSession'
import { usePlanApi } from '@/composables/usePlanApi'
import { PLAN_CONFIG_TYPES } from '@/utils/planTypeRegistry'
import {
  MAAEND_PLAN_WEEKDAY_KEYS,
  maaEndPlanKeyToSanityConfig,
  type MaaEndEssenceTargetGroup,
  type MaaEndSanityConfig,
} from '@/utils/maaEndProtocolSpace'
import { getWeekdayInTimezone } from '@/utils/dateUtils'
import { buildRestoreConfirm } from '@/utils/configRestoreMode'

import MaaEndUserEditHeader from '@/views/MaaEndUserEdit/MaaEndUserEditHeader.vue'
import BasicInfoSection from '@/views/MaaEndUserEdit/BasicInfoSection.vue'
import DailyOnceSection from '@/views/MaaEndUserEdit/DailyOnceSection.vue'
import ConfigSourceSection from '@/views/MaaEndUserEdit/ConfigSourceSection.vue'
import DeliveryConfigSection from '@/views/MaaEndUserEdit/DeliveryConfigSection.vue'
import type { MaaEndAutoCollectGroup } from '@/api'
import AutoCollectConfigSection from '@/views/MaaEndUserEdit/AutoCollectConfigSection.vue'
import TaskConfigSection from '@/views/MaaEndUserEdit/TaskConfigSection.vue'
import UserNotifyConfig from '@/components/UserNotifyConfig.vue'
import ExtraScriptSection from '@/components/ExtraScriptSection.vue'
import GuiSessionMask from '@/components/GuiSessionMask.vue'
import ConfigRestoreSection from '@/views/EditView/User/components/ConfigRestoreSection.vue'

const { t } = useI18n()

const logger = window.electronAPI.getLogger('MaaEnd用户编辑')

const router = useRouter()
const route = useRoute()
const { addUser, updateUser, getUsers, error: userError } = useUserApi()
const { getScript, getMaaEndOptions, importScriptConfigFile } = useScriptApi()
const { getPlans } = usePlanApi()
const {
  maaEndConfigLoading,
  maaEndTaskId,
  showMaaEndConfigMask,
  showMaaEndViewMask,
  stoppingMaaEndConfig,
  startSession,
  saveSession,
  stopSession,
} = useMaaEndGuiSession()

const formRef = ref<FormInstance>()
const isInitializing = ref(true)
const isSaving = ref(false)
// 保存请求不再驱动整页 loading，避免每次自动保存都让表单快速闪动。
const loading = computed(() => isInitializing.value)
const maaEndOptionsLoading = ref(false)
const maaEndOptionsLoaded = ref(false)

const scriptId = route.params.scriptId as string
let userId = route.params.userId as string
const isEdit = ref(!!userId)
const scriptName = ref('')
const controllerType = ref<string | null>(null)
const controllerProtocol = ref<string | null>(null)
const presetSupported = ref(true)

const maaEndImportLoading = ref(false)
const resourceOptions = [{ label: '官服', value: '官服' }]
const essenceLocationOptions = ref<ComboBoxItem[]>([])
const essenceMenuOptions = ref<ComboBoxItem[]>([])
const autoCollectGroups = ref<MaaEndAutoCollectGroup[]>([])
const essenceTargetWeaponGroups = ref<MaaEndEssenceTargetGroup[]>([])
const sanityModeOptions = ref<Array<{ label: string; value: string }>>([
  { label: t('edit.fixed'), value: 'Fixed' },
])
const planModeConfig = ref<MaaEndSanityConfig | null>(null)
// 计划表切换版本号：loadSanityPlan 每次调用自增，用于丢弃过期的异步响应
let sanityPlanLoadVersion = 0
const isSanityPlanMode = computed(() => formData.Info.SanityMode !== 'Fixed')

const getAnchorContainer = () => document.querySelector<HTMLElement>('.content-area') ?? window

// 每日执行限制属于调度，独立于快速配置。
const anchorItems = computed(() => {
  const items = [{ key: 'basic', href: '#section-basic', title: t('edit.basicInfo') }]
  items.push({ key: 'source', href: '#section-source', title: t('edit.configurationSource') })
  items.push({ key: 'task', href: '#section-task', title: t('edit.taskConfiguration') })
  if (formData.Info.IfQuickConfig) {
    items.push(
      { key: 'collect', href: '#section-collect', title: t('edit.maaEndAutoCollectConfig') },
      { key: 'delivery', href: '#section-delivery', title: t('edit.maaEndDeliveryConfig') }
    )
  }
  items.push(
    { key: 'limits', href: '#section-limits', title: t('edit.maaEndDailyOnceTasks') },
    { key: 'script', href: '#section-script', title: t('comp.extraScripts') },
    { key: 'notify', href: '#section-notify', title: t('edit.notificationSettings') }
  )
  return items
})

const getDefaultMaaEndUserData = () => ({
  Info: {
    Name: '',
    Status: true,
    Id: '',
    Password: '',
    Mode: '脚本',
    IfQuickConfig: true,
    SanityMode: 'Fixed',
    Resource: '官服',
    RemainedDay: -1,
    IfScriptBeforeTask: false,
    ScriptBeforeTask: '',
    IfScriptAfterTask: false,
    ScriptAfterTask: '',
    Notes: '',
    Tag: '',
  },
  Task: {
    SanityTaskType: 'OperatorProgression',
    OperatorProgression: 'OperatorEXP',
    WeaponProgression: 'WeaponEXP',
    CrisisDrills: 'AdvancedProgression1',
    RewardsSetOption: 'RewardsSetA',
    AutoEssenceSpecifiedLocation: '',
    AutoEssenceMenu: 'Location',
    AutoEssenceTargetWeapons: [],
    SeizeDeliveryJobsReward: 15.9,
    SeizeDeliveryJobsCommissionSource: 'Unlimited',
    AutoCollectMode: 'Distributed',
    AutoCollectRoutes: null,
    AutoCollectCommonRoutes: null,
    IfSanity: true,
    IfAutoUseSpMedication: true,
    IfDijiangRewards: true,
    IfDeliveryJobs: true,
    IfSellProduct: true,
    IfAutoStockpile: true,
    IfAutoStockStaple: true,
    IfVisitFriends: true,
    IfCreditShoppingN2: true,
    IfSeizeDeliveryJobs: true,
    IfAutoEcoFarm: true,
    IfAutoSell: true,
    IfEnvironmentMonitoring: true,
    IfAutoCollect: true,
    IfTrialOfSwordmancy: true,
    IfDailyRewards: true,
    IfResourceRecycleStation: true,
    IfPullCountCalculator: false,
    DailyOnceTasks: '[ ]',
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
    PeriodTaskRecords: '{ }',
  },
})

interface FieldChange {
  key: string
  value: any
}

// 保存中的后续修改按字段合并，避免输入过程中被前一个请求丢弃或重复发送旧值。
const pendingFieldSaves = new Map<string, any>()
let fieldSavePromise: Promise<boolean> | null = null

const restoreFailedFieldSaves = (changes: Array<[string, any]>) => {
  for (const [key, value] of changes) {
    // 保存请求期间的新值优先，失败批次只补回尚未被覆盖的字段。
    if (!pendingFieldSaves.has(key)) {
      pendingFieldSaves.set(key, value)
    }
  }
}

const reportFieldSaveFailure = () => {
  const errorMsg = userError.value
  if (!errorMsg || errorMsg.includes('HTTP error')) {
    message.error(t('edit.couldNotSaveUser'))
  }
  logger.error(`保存用户字段失败: ${errorMsg || '用户 API 未返回成功'}`)
}

const formData = reactive({
  userName: '',
  ...getDefaultMaaEndUserData(),
})

const rules = computed<Record<string, Rule[]>>(() => ({
  userName: [
    { required: true, message: t('edit.enterUsername'), trigger: 'blur' },
    { min: 1, max: 50, message: t('edit.usernameMustBe12'), trigger: 'blur' },
  ],
}))

const syncUserName = () => {
  if (formData.Info.Name !== formData.userName) {
    formData.Info.Name = formData.userName
  }
}

const setNestedValue = (target: Record<string, any>, path: string, value: any) => {
  const parts = path.split('.')
  let current = target

  for (let index = 0; index < parts.length - 1; index += 1) {
    current[parts[index]] = current[parts[index]] ?? {}
    current = current[parts[index]]
  }

  current[parts[parts.length - 1]] = value
}

const saveUserFields = async (changes: FieldChange[]) => {
  if (isInitializing.value || !userId || !changes.length) return false

  for (const change of changes) {
    pendingFieldSaves.set(change.key, change.value)
  }
  if (fieldSavePromise) return fieldSavePromise

  const savePromise = (async (): Promise<boolean> => {
    isSaving.value = true
    let currentChanges: Array<[string, any]> = []
    try {
      while (pendingFieldSaves.size > 0) {
        const userData: Record<string, any> = {}
        currentChanges = Array.from(pendingFieldSaves.entries())
        pendingFieldSaves.clear()

        currentChanges.forEach(([key, value]) => {
          if (key === 'userName') {
            syncUserName()
            setNestedValue(userData, 'Info.Name', formData.Info.Name)
            return
          }

          setNestedValue(userData, key, value)
        })

        if (!(await updateUser(scriptId, userId, userData))) {
          restoreFailedFieldSaves(currentChanges)
          reportFieldSaveFailure()
          return false
        }
        currentChanges = []
      }
      return true
    } catch (error) {
      restoreFailedFieldSaves(currentChanges)
      reportFieldSaveFailure()
      const errorMessage = error instanceof Error ? error.message : String(error)
      logger.error(`保存用户字段异常: ${errorMessage}`)
      return false
    } finally {
      isSaving.value = false
      fieldSavePromise = null
    }
  })()
  fieldSavePromise = savePromise
  return savePromise
}

const handleFieldSave = async (key: string, value: any) => {
  if (key === 'userName') {
    formData.userName = value
    syncUserName()
  } else {
    setNestedValue(formData, key, value)
  }
  return await saveUserFields([{ key, value }])
}

const handleQuickConfigChange = async (value: boolean) => {
  const previous = formData.Info.IfQuickConfig
  if (!(await handleFieldSave('Info.IfQuickConfig', value))) {
    pendingFieldSaves.delete('Info.IfQuickConfig')
    formData.Info.IfQuickConfig = previous
  }
}

const handleConfigModeChange = async (value: boolean | string) => {
  if (typeof value !== 'string' || !['脚本', '用户', '直控'].includes(value)) return
  formData.Info.Mode = value
  await handleFieldSave('Info.Mode', value)
}

const handleFieldsSave = async (changes: FieldChange[]) => {
  changes.forEach(change => setNestedValue(formData, change.key, change.value))
  await saveUserFields(changes)
}

const handleScriptConfig = () => {
  void stopSession()
  router.push(`/scripts/${scriptId}/edit/maaend`)
}

const handleGoToPlans = () => {
  navigateTo('/plans', { query: { planId: formData.Info.SanityMode } })
}

const loadScriptInfo = async () => {
  const scriptDetail = await getScript(scriptId)
  if (scriptDetail) {
    scriptName.value = scriptDetail.name
    controllerType.value = (scriptDetail.config as any).Game?.ControllerType ?? null
  }
}

const loadMaaEndOptions = async () => {
  maaEndOptionsLoading.value = true
  try {
    const response = await getMaaEndOptions(scriptId)
    if (response?.code === 200) {
      autoCollectGroups.value = response.autoCollectGroups ?? []
      essenceLocationOptions.value = response.essenceLocations
      essenceMenuOptions.value = response.essenceMenus ?? []
      essenceTargetWeaponGroups.value = response.essenceTargetWeaponGroups ?? []
      controllerProtocol.value = response.controllerTypes[controllerType.value ?? ''] ?? null
      presetSupported.value = controllerProtocol.value === 'Win32'
      maaEndOptionsLoaded.value = true
    }
  } finally {
    maaEndOptionsLoading.value = false
  }
}

const loadSanityModeOptions = async () => {
  try {
    const response = await Service.getPlanComboxApiInfoComboxPlanPost({
      consumer: PlanComboxIn.consumer.MAAEND,
    })
    if (response?.code === 200 && response.data) {
      sanityModeOptions.value = response.data
        .filter((item): item is ComboBoxItem & { value: string } => item.value !== null)
        .map(item => ({ label: item.label, value: item.value }))
    }
  } catch (error) {
    logger.error(`加载理智任务计划失败: ${error instanceof Error ? error.message : String(error)}`)
  }
}

const loadSanityPlan = async (planId: string) => {
  const version = ++sanityPlanLoadVersion

  if (!planId || planId === 'Fixed') {
    planModeConfig.value = null
    return
  }

  try {
    const response = await getPlans(planId)
    // 已切换到其他计划表：丢弃过期响应，避免旧数据覆盖当前 UI
    if (version !== sanityPlanLoadVersion || formData.Info.SanityMode !== planId) {
      return
    }
    const planData = response.data?.[planId] as unknown as Record<string, unknown> | undefined
    const planIndex = response.index?.find(item => item.uid === planId)
    if (planIndex?.type !== PLAN_CONFIG_TYPES.MAA_END || !planData) {
      planModeConfig.value = null
      return
    }
    const dayKey = MAAEND_PLAN_WEEKDAY_KEYS[(getWeekdayInTimezone(4) + 6) % 7]
    const info = planData.Info as Record<string, unknown> | undefined
    const dayConfig = info?.Mode === 'Weekly' ? planData[dayKey] : planData.ALL
    planModeConfig.value = maaEndPlanKeyToSanityConfig(dayConfig)
  } catch (error) {
    if (version !== sanityPlanLoadVersion) {
      return
    }
    planModeConfig.value = null
    logger.error(`加载理智任务计划失败: ${error instanceof Error ? error.message : String(error)}`)
  }
}

const normalizeQuickConfig = async () => {
  if (!userId) return

  const infoPayload: Record<string, unknown> = {}
  if (formData.Info.Mode === '自定义') {
    formData.Info.Mode = '用户'
    formData.Info.IfQuickConfig = false
    infoPayload.Mode = formData.Info.Mode
    infoPayload.IfQuickConfig = formData.Info.IfQuickConfig
  }

  if (maaEndOptionsLoaded.value && !presetSupported.value && formData.Info.IfQuickConfig) {
    infoPayload.IfQuickConfig = false
  }

  if (Object.keys(infoPayload).length) {
    if (await updateUser(scriptId, userId, { Info: infoPayload })) {
      Object.assign(formData.Info, infoPayload)
    }
  }
}

const loadUserData = async () => {
  try {
    const userResponse = await getUsers(scriptId, userId)
    if (!userResponse || userResponse.code !== 200) {
      throw new Error('加载用户失败')
    }

    const userIndex = userResponse.index.find((index: any) => index.uid === userId)
    if (!userIndex || !userResponse.data[userId]) {
      throw new Error('用户不存在')
    }

    const userData = userResponse.data[userId] as any
    if (userIndex.type !== 'MaaEndUserConfig') {
      throw new Error('用户类型不匹配')
    }

    Object.assign(formData, {
      Info: { ...getDefaultMaaEndUserData().Info, ...userData.Info },
      Task: { ...getDefaultMaaEndUserData().Task, ...userData.Task },
      Notify: { ...getDefaultMaaEndUserData().Notify, ...userData.Notify },
      Data: { ...getDefaultMaaEndUserData().Data, ...userData.Data },
    })

    await nextTick()
    formData.userName = formData.Info.Name || ''
  } catch (error) {
    message.error(error instanceof Error ? error.message : '加载用户失败')
    router.push('/scripts')
  }
}

const handleMaaEndConfig = async () => {
  if (!userId) return
  await startSession(userId)
}

const handleSaveMaaEndConfig = () => {
  void saveSession()
}

const handleCloseMaaEndView = () => {
  void stopSession()
}

const handleImportMaaEndConfig = async () => {
  try {
    maaEndImportLoading.value = true
    if (formData.Info.Mode === '直控') {
      throw new Error('脚本直控直接使用 MaaEnd 原有配置，无需导入')
    }
    const response = await importScriptConfigFile(
      scriptId,
      formData.Info.Mode === '脚本' ? null : userId
    )
    if (response.code !== 200) {
      throw new Error(response.message || '导入脚本配置文件失败')
    }
    const importTarget = formData.Info.Mode === '脚本' ? '脚本共享' : '用户独立'
    message.success(t('edit.importedP0ConfigurationFile', { p0: importTarget }))
  } catch (error) {
    message.error(error instanceof Error ? error.message : '导入脚本配置文件失败')
  } finally {
    maaEndImportLoading.value = false
  }
}

const handleCancel = async () => {
  await stopSession()
  router.push('/scripts')
}

// ══ 配置恢复（通用组件 props 供给：双目标 MAS 在前脚本在后）══
// 专项统一名（文案参数化用）：MaaEnd 统一叫「maaend」
const MAAEND_DISPLAY_NAME = 'maaend'
const restoreOpen = ref(false)

// 目标池顺序 = segmented 展示顺序：MAS 用户配置（在前）、MaaEnd 原生配置（在后）
const restoreTargets: Array<{ key: string; kind: 'user' | 'script' }> = [
  { key: 'mas', kind: 'user' },
  { key: 'native', kind: 'script' },
]

// 组件调用后端：通用 /backup/* 端点（脚本/用户上下文在此闭包捕获）
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

const openRestoreModal = () => {
  restoreOpen.value = true
}

// 预览响应原文（unknown）收敛为文件集视图：泛用组件的 raw 插槽不带专项类型
interface MaaEndPreviewFileView {
  name: string
  label: string
  summary: Array<{ key: string; value: string }>
}
const previewFiles = (raw: unknown): MaaEndPreviewFileView[] =>
  (raw as { fileCards?: MaaEndPreviewFileView[] } | null)?.fileCards ?? []

// 一键恢复成功：mas 恢复含页面快速配置回填，重拉表单——否则旧表单值在
// 下次保存时会静默覆盖回滚结果；native 恢复不影响本页表单
const handleRestored = async (target: string) => {
  restoreOpen.value = false
  if (target === 'mas') {
    await loadUserData()
  }
}

// 「查看详细配置」语义（对齐一条龙）：恢复该时点 + 拉起查看会话预览。
// 弹窗文案必须显式区分——该按钮极易被误以为只读，实际会真覆盖当前配置。
// mas 备份：恢复到 MAS 目录后启动查看会话（下发为查看的必经复制，GUI 所见
// 即备份）；原生备份：恢复到 MaaEnd 本体后启动脚本级查看会话（跳过下发，
// 原生目录即备份）。查看会话结束不回写配置，原生现场由任务前快照还原。
// 与一键恢复同口径：单弹窗文案，跨配置来源时换标题并追加来源切换说明
// （确认后由基座把配置来源切回备份时点再恢复）。
const handleRestoreView = (
  target: string,
  item: { time: string; mode?: string | null },
  currentMode?: string | null
) =>
  new Promise<boolean>(resolve => {
    const { title, paragraphs } = buildRestoreConfirm(
      t,
      {
        title: t('edit.configRestoreDetailView'),
        desc: t('edit.configRestoreDetailConfirm', { script: MAAEND_DISPLAY_NAME }),
      },
      item.mode,
      currentMode
    )
    Modal.confirm({
      title,
      content: h(
        'div',
        paragraphs.map(text =>
          h('p', { style: { color: 'var(--ant-color-error)', margin: '0 0 8px' } }, text)
        )
      ),
      okType: 'danger',
      okText: t('edit.configRestoreConfirmOk'),
      cancelText: t('edit.cancel'),
      onOk: async () => {
        try {
          const resp = await Service.restoreConfigBackupApiApiScriptsBackupRestorePost({
            scriptId,
            userId,
            time: item.time,
            target,
          })
          // 后端失败走 HTTP 200 + body code=400，须显式检查返回体：备份不存在/
          // 路径未设置等抛错若被吞掉，会照常关弹窗并打开查看会话
          if (resp.code !== 200) {
            throw new Error(resp.message || t('edit.configRestoreFailed'))
          }
          restoreOpen.value = false
          if (target === 'mas') {
            // 恢复后重拉表单：后端 UserData 已回填，不重拉会让旧表单值在
            // 下次保存时整块写回、覆盖恢复结果（对齐一键恢复 handleRestored）
            await loadUserData()
            await startSession(userId, true)
          } else {
            await startSession(scriptId, true)
          }
          resolve(true)
        } catch (e) {
          message.error(e instanceof Error ? e.message : t('edit.configRestoreFailed'))
          resolve(false)
        }
      },
      onCancel: () => resolve(false),
    })
  })

// 编辑会话归档（进入/退出时机，指纹去重）：与运行/会话下发前的双池归档
// 配合——进入归档原生配置当前状态（MAS 触碰前原始态），退出归档 MAS 配置
// 终态（编辑会话包络）
const ensureMaaEndBackup = async (target: 'mas' | 'native') => {
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
  await loadScriptInfo()
  await loadMaaEndOptions()
  await loadSanityModeOptions()

  if (isEdit.value) {
    await loadUserData()
    await normalizeQuickConfig()
  } else {
    const result = await addUser(scriptId)
    if (result?.userId) {
      userId = result.userId
      isEdit.value = true
      await normalizeQuickConfig()
    } else {
      message.error(t('edit.couldNotCreateUser'))
      router.push('/scripts')
      return
    }
  }

  // 先等脚本信息与用户就绪（新建模式内部会创建用户并写入 userId）再归档，
  // 否则新建用户首次进入会因 userId 未就绪静默跳过归档
  await nextTick()
  void ensureMaaEndBackup('native')

  await nextTick()
  await loadSanityPlan(formData.Info.SanityMode)
  isInitializing.value = false
})

watch(
  () => formData.Info.SanityMode,
  value => {
    void loadSanityPlan(value)
  }
)

onUnmounted(() => {
  // 退出编辑页：先停会话再归档 MAS 侧终态——并行会与 final_task 的
  // rmtree/copytree 回写撞车，归档到半程状态；会话未开时 stopSession
  // 立即返回，不影响归档时机
  void (async () => {
    await stopSession()
    await ensureMaaEndBackup('mas')
  })()
})
</script>

<style scoped>
.user-edit-container {
  padding: 24px;
  background: var(--ant-color-bg-layout);
}

.user-edit-content {
  width: 100%;
  min-width: 0;
}

.page-layout {
  display: grid;
  grid-template-columns: 144px minmax(0, 1fr);
  gap: 24px;
  align-items: start;
}

.sections-column {
  width: 100%;
  max-width: none;
  grid-column: 2;
  grid-row: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.section-card {
  border-radius: 8px;
  scroll-margin-top: 32px;
}

.section-card :deep(.ant-card-body) {
  padding: 24px;
}

.optional-section {
  background: var(--ant-color-bg-container);
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  scroll-margin-top: 32px;
}

.daily-once-title {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 600;
}

.plans-button {
  padding-inline: 0;
}

.anchor-sidebar {
  grid-column: 1;
  grid-row: 1;
  position: sticky;
  top: 32px;
}

.maaend-preview-title {
  margin: 0 0 8px;
}

.maaend-preview-box {
  margin-bottom: 16px;
}

@media (max-width: 1100px) {
  .page-layout {
    grid-template-columns: 1fr;
  }

  .sections-column {
    grid-column: 1;
  }

  .anchor-sidebar {
    display: none;
  }
}

@media (max-width: 768px) {
  .user-edit-container {
    padding: 16px;
  }

  .section-card :deep(.ant-card-body) {
    padding: 20px;
  }
}
</style>
