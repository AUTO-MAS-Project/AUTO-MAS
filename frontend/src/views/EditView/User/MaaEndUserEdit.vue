<template>
  <div class="user-edit-container">
    <teleport to="body">
      <div v-if="showMaaEndConfigMask" class="maaend-config-mask">
        <div class="mask-content">
          <div class="mask-icon">
            <SettingOutlined :style="{ fontSize: '48px', color: 'var(--ant-color-primary)' }" />
          </div>
          <h2 class="mask-title">{{ t('edit.maaendConfigurationProgress') }}</h2>
          <p class="mask-description">
            {{ t('edit.maaendConfigurationWindowOpen') }}
            <br />
            {{ t('edit.clickSaveConfigurationWhen') }}
          </p>
          <div class="mask-actions">
            <a-button
              v-if="maaEndTaskId"
              type="primary"
              size="large"
              @click="handleSaveMaaEndConfig"
            >
              {{ t('edit.saveConfiguration') }}
            </a-button>
          </div>
        </div>
      </div>
    </teleport>

    <MaaEndUserEditHeader
      :script-id="scriptId"
      :script-name="scriptName"
      :is-edit="isEdit"
      @handle-cancel="handleCancel"
    />

    <div class="user-edit-content">
      <a-card class="config-card">
        <a-form
          ref="formRef"
          :model="formData"
          :rules="rules"
          layout="vertical"
          class="config-form"
        >
          <BasicInfoSection
            v-model:form-data="formData"
            :loading="loading"
            :resource-options="resourceOptions"
            :preset-supported="presetSupported"
            :config-loading="maaEndConfigLoading"
            :import-loading="maaEndImportLoading"
            :show-config-mask="showMaaEndConfigMask"
            @save="handleFieldSave"
            @configure="handleMaaEndConfig"
            @import-config="handleImportMaaEndConfig"
            @script-config="handleScriptConfig"
            @mode-change="handleConfigModeChange"
          />
          <DeliveryConfigSection
            v-if="formData.Info.IfQuickConfig"
            :form-data="formData"
            :loading="loading"
            @save="handleFieldSave"
          />
          <AutoCollectConfigSection
            v-if="formData.Info.IfQuickConfig"
            :form-data="formData"
            :loading="loading"
            @save="handleFieldSave"
          />
          <TaskConfigSection
            v-if="formData.Info.IfQuickConfig"
            :form-data="formData"
            :loading="loading"
            :if-quick-config="formData.Info.IfQuickConfig"
            :essence-location-options="essenceLocationOptions"
            :options-loading="maaEndOptionsLoading"
            :options-loaded="maaEndOptionsLoaded"
            :is-plan-mode="isSanityPlanMode"
            :sanity-mode-options="sanityModeOptions"
            :plan-mode-config="planModeConfig"
            @save="handleFieldSave"
            @save-batch="handleFieldsSave"
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
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { SettingOutlined } from '@ant-design/icons-vue'
import type { FormInstance, Rule } from 'ant-design-vue/es/form'
import type { ComboBoxItem } from '@/api'
import { Service } from '@/api'
import { PlanComboxIn } from '@/api/models/PlanComboxIn'
import { useUserApi } from '@/composables/useUserApi'
import { useScriptApi } from '@/composables/useScriptApi'
import { useWebSocket } from '@/composables/useWebSocket'
import {
  WS_TASK_COMPLETED,
  WS_TASK_NOTICE,
  type WSTaskNoticeData,
} from '@/services/websocket/types'
import { usePlanApi } from '@/composables/usePlanApi'
import { PLAN_CONFIG_TYPES } from '@/utils/planTypeRegistry'
import {
  MAAEND_PLAN_WEEKDAY_KEYS,
  maaEndPlanKeyToSanityConfig,
  type MaaEndSanityConfig,
} from '@/utils/maaEndProtocolSpace'
import { getWeekdayInTimezone } from '@/utils/dateUtils'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'

import MaaEndUserEditHeader from '@/views/MaaEndUserEdit/MaaEndUserEditHeader.vue'
import BasicInfoSection from '@/views/MaaEndUserEdit/BasicInfoSection.vue'
import DeliveryConfigSection from '@/views/MaaEndUserEdit/DeliveryConfigSection.vue'
import AutoCollectConfigSection from '@/views/MaaEndUserEdit/AutoCollectConfigSection.vue'
import TaskConfigSection from '@/views/MaaEndUserEdit/TaskConfigSection.vue'
import UserNotifyConfig from '@/components/UserNotifyConfig.vue'
import ExtraScriptSection from '@/components/ExtraScriptSection.vue'

const { t } = useI18n()

const logger = window.electronAPI.getLogger('MaaEnd用户编辑')

const router = useRouter()
const route = useRoute()
const { addUser, updateUser, getUsers, loading: userLoading } = useUserApi()
const { getScript, getMaaEndOptions, importScriptConfigFile } = useScriptApi()
const { getPlans } = usePlanApi()
const { subscribe, unsubscribe } = useWebSocket()

const formRef = ref<FormInstance>()
const isInitializing = ref(true)
const isSaving = ref(false)
const loading = computed(() => isInitializing.value || userLoading.value)
const maaEndOptionsLoading = ref(false)
const maaEndOptionsLoaded = ref(false)

const scriptId = route.params.scriptId as string
let userId = route.params.userId as string
const isEdit = ref(!!userId)
const scriptName = ref('')
const controllerType = ref<string | null>(null)
const presetSupported = ref(true)

const maaEndConfigLoading = ref(false)
const maaEndImportLoading = ref(false)
const showMaaEndConfigMask = ref(false)
const maaEndSubscriptionIds = ref<string[]>([])
const maaEndTaskId = ref<string | null>(null)
let maaEndConfigTimeout: number | null = null
const resourceOptions = [{ label: '官服', value: '官服' }]
const essenceLocationOptions = ref<ComboBoxItem[]>([])
const sanityModeOptions = ref<Array<{ label: string; value: string }>>([
  { label: t('edit.fixed'), value: 'Fixed' },
])
const planModeConfig = ref<MaaEndSanityConfig | null>(null)
// 计划表切换版本号：loadSanityPlan 每次调用自增，用于丢弃过期的异步响应
let sanityPlanLoadVersion = 0
const isSanityPlanMode = computed(() => formData.Info.SanityMode !== 'Fixed')

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
    SeizeDeliveryJobsReward: 15.9,
    SeizeDeliveryJobsCommissionSource: 'Unlimited',
    AutoCollectMode: 'Distributed',
    AutoCollectRoutes: [
      'Route1',
      'Route2',
      'Route3',
      'Route4',
      'Route5',
      'Route6',
      'Route7',
      'Route8',
      'Route9',
      'Route10',
      'Route11',
      'Route12',
      'Route13',
      'Route14',
      'Route15',
    ],
    AutoCollectCommonRoutes: [
      'CommonRoute1',
      'CommonRoute2',
      'CommonRoute3',
      'CommonRoute4',
      'CommonRoute5',
      'CommonRoute6',
      'CommonRoute7',
      'CommonRoute8',
    ],
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
  },
})

interface FieldChange {
  key: string
  value: any
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
  if (isInitializing.value || isSaving.value || !userId || !changes.length) return

  isSaving.value = true
  try {
    const userData: Record<string, any> = {}

    changes.forEach(change => {
      if (change.key === 'userName') {
        syncUserName()
        setNestedValue(userData, 'Info.Name', formData.Info.Name)
        return
      }

      setNestedValue(userData, change.key, change.value)
    })

    await updateUser(scriptId, userId, userData)
  } catch (error) {
    logger.error(`保存用户字段失败: ${error instanceof Error ? error.message : String(error)}`)
  } finally {
    isSaving.value = false
  }
}

const handleFieldSave = async (key: string, value: any) => {
  await saveUserFields([{ key, value }])
}

const handleConfigModeChange = async (value: boolean | string) => {
  if (typeof value !== 'string' || !['脚本', '用户', '直控'].includes(value)) return
  formData.Info.Mode = value
  await handleFieldSave('Info.Mode', value)
}

const handleFieldsSave = async (changes: FieldChange[]) => {
  await saveUserFields(changes)
}

const handleScriptConfig = () => {
  cleanupConfigSession()
  router.push(`/scripts/${scriptId}/edit/maaend`)
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
      essenceLocationOptions.value = response.essenceLocations
      presetSupported.value = response.controllerTypes[controllerType.value ?? ''] === 'Win32'
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

  if (!presetSupported.value && formData.Info.IfQuickConfig) {
    formData.Info.IfQuickConfig = false
    infoPayload.IfQuickConfig = false
  }

  if (Object.keys(infoPayload).length) {
    await updateUser(scriptId, userId, { Info: infoPayload })
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

const cleanupConfigSession = () => {
  for (const subscriptionId of maaEndSubscriptionIds.value) {
    unsubscribe(subscriptionId)
  }
  maaEndSubscriptionIds.value = []
  maaEndTaskId.value = null
  showMaaEndConfigMask.value = false
  if (maaEndConfigTimeout) {
    window.clearTimeout(maaEndConfigTimeout)
    maaEndConfigTimeout = null
  }
}

const handleMaaEndConfig = async () => {
  try {
    maaEndConfigLoading.value = true
    cleanupConfigSession()

    const response = await Service.addTaskApiDispatchStartPost({
      taskId: userId,
      mode: TaskCreateIn.mode.SCRIPT_CONFIG,
    })

    if (!response?.taskId) {
      throw new Error(response?.message || '启动 MaaEnd 配置失败')
    }

    const subscriptionIds = [
      subscribe({ id: response.taskId, type: WS_TASK_NOTICE }, wsMessage => {
        const data = wsMessage.data as unknown as WSTaskNoticeData
        if (data.level === 'error') {
          message.error(t('edit.maaendConfigurationErrorP0', { p0: data.message }))
        }
      }),
      subscribe({ id: response.taskId, type: WS_TASK_COMPLETED }, () => {
        cleanupConfigSession()
      }),
    ]

    maaEndSubscriptionIds.value = subscriptionIds
    maaEndTaskId.value = response.taskId
    showMaaEndConfigMask.value = true
    const configTarget =
      formData.Info.Mode === '直控'
        ? '脚本直控'
        : formData.Info.Mode === '用户'
          ? '用户独立'
          : '脚本共享'
    message.success(
      t('edit.startedP0MaaendConfiguration', {
        p0: configTarget,
      })
    )

    maaEndConfigTimeout = window.setTimeout(
      () => {
        cleanupConfigSession()
        message.info(t('edit.maaendConfigurationSessionTimed'))
      },
      30 * 60 * 1000
    )
  } catch (error) {
    message.error(error instanceof Error ? error.message : '启动 MaaEnd 配置失败')
  } finally {
    maaEndConfigLoading.value = false
  }
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
    message.success(
      t('edit.importedP0ConfigurationFile', { p0: importTarget })
    )
  } catch (error) {
    message.error(error instanceof Error ? error.message : '导入脚本配置文件失败')
  } finally {
    maaEndImportLoading.value = false
  }
}

const handleSaveMaaEndConfig = async () => {
  try {
    if (!maaEndTaskId.value) {
      throw new Error('未找到活动配置会话')
    }

    const response = await Service.stopTaskApiDispatchStopPost({ taskId: maaEndTaskId.value })
    if (response.code !== 200) {
      throw new Error(response.message || '保存配置失败')
    }

    cleanupConfigSession()
    message.success(t('edit.maaendConfigurationSaved'))
  } catch (error) {
    message.error(error instanceof Error ? error.message : '保存配置失败')
  }
}

const handleCancel = () => {
  cleanupConfigSession()
  router.push('/scripts')
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
</script>

<style scoped>
.user-edit-container {
  padding: 32px;
  min-height: 100vh;
  background: var(--ant-color-bg-layout);
}

.user-edit-content {
  max-width: 1200px;
  margin: 0 auto;
}

.config-card {
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.config-card :deep(.ant-card-body) {
  padding: 32px;
}

.maaend-config-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}

.mask-content {
  background: var(--ant-color-bg-elevated);
  border-radius: 8px;
  padding: 24px;
  max-width: 480px;
  width: 100%;
  text-align: center;
  border: 1px solid var(--ant-color-border);
}

.mask-icon {
  margin-bottom: 16px;
}

.mask-title {
  font-size: 18px;
  font-weight: 600;
  margin: 0 0 8px;
}

.mask-description {
  font-size: 14px;
  color: var(--ant-color-text-secondary);
  margin: 0 0 24px;
  line-height: 1.5;
}

.mask-actions {
  display: flex;
  justify-content: center;
}

@media (max-width: 768px) {
  .user-edit-container {
    padding: 16px;
  }

  .config-card :deep(.ant-card-body) {
    padding: 20px;
  }
}
</style>
