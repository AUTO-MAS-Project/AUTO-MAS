<template>
  <div class="user-edit-container">
    <teleport to="body">
      <div v-if="showMaaEndConfigMask" class="maaend-config-mask">
        <div class="mask-content">
          <div class="mask-icon">
            <SettingOutlined :style="{ fontSize: '48px', color: 'var(--ant-color-primary)' }" />
          </div>
          <h2 class="mask-title">正在进行 MaaEnd 配置</h2>
          <p class="mask-description">
            当前正在为这个用户打开 MaaEnd 配置界面，请在 MaaEnd 中完成相关设置。
            <br />
            配置完成后，点击“保存配置”结束本次会话。
          </p>
          <div class="mask-actions">
            <a-button
              v-if="maaEndWebsocketId"
              type="primary"
              size="large"
              @click="handleSaveMaaEndConfig"
            >
              保存配置
            </a-button>
          </div>
        </div>
      </div>
    </teleport>

    <MaaEndUserEditHeader
      :script-id="scriptId"
      :script-name="scriptName"
      :is-edit="isEdit"
      :user-mode="formData.Info.Mode"
      :maa-end-config-loading="maaEndConfigLoading"
      :show-maa-end-config-mask="showMaaEndConfigMask"
      @handle-maa-end-config="handleMaaEndConfig"
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
            :form-data="formData"
            :loading="loading"
            :resource-options="resourceOptions"
            @save="handleFieldSave"
          />
          <TaskConfigSection
            :form-data="formData"
            :loading="loading"
            :is-plan-mode="isSanityPlanMode"
            :sanity-mode-options="sanityModeOptions"
            :plan-mode-config="planModeConfig"
            :sanity-task-type-tooltip="sanityTaskTypeTooltip"
            :current-task-tooltip="currentTaskTooltip"
            :rewards-tooltip="rewardsTooltip"
            @save="handleFieldSave"
            @save-batch="handleFieldsSave"
          />
          <SkylandConfigSection :form-data="formData" :loading="loading" @save="handleFieldSave" />
          <NotifyConfigSection
            :form-data="formData"
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
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { SettingOutlined } from '@ant-design/icons-vue'
import type { FormInstance, Rule } from 'ant-design-vue/es/form'
import { PlanComboxIn, Service } from '@/api'
import type { MaaEndPlanConfig } from '@/api'
import { useUserApi } from '@/composables/useUserApi'
import { useScriptApi } from '@/composables/useScriptApi'
import { usePlanApi } from '@/composables/usePlanApi'
import { useWebSocket } from '@/composables/useWebSocket'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import { getWeekdayInTimezone } from '@/utils/dateUtils'
import { PLAN_CONFIG_TYPES } from '@/utils/planTypeRegistry'
import {
  MAAEND_PLAN_TIME_LABELS,
  MAAEND_PLAN_WEEKDAY_KEYS,
  SANITY_TASK_TYPE_LABEL_MAP,
  REWARD_LABEL_MAP,
  getSanityTaskDisplayValue,
  normalizeMaaEndSanityConfig,
  type PlanWeekdayKey,
  type MaaEndSanityConfig,
} from '@/utils/maaEndProtocolSpace'

import MaaEndUserEditHeader from '../../MaaEndUserEdit/MaaEndUserEditHeader.vue'
import BasicInfoSection from '../../MaaEndUserEdit/BasicInfoSection.vue'
import TaskConfigSection from '../../MaaEndUserEdit/TaskConfigSection.vue'
import SkylandConfigSection from '../../MaaEndUserEdit/SkylandConfigSection.vue'
import NotifyConfigSection from '../../MaaEndUserEdit/NotifyConfigSection.vue'

const logger = window.electronAPI.getLogger('MaaEnd用户编辑')

const router = useRouter()
const route = useRoute()
const { addUser, updateUser, getUsers, loading: userLoading } = useUserApi()
const { getScript } = useScriptApi()
const { getPlans } = usePlanApi()
const { subscribe, unsubscribe } = useWebSocket()

const formRef = ref<FormInstance>()
const loading = computed(() => userLoading.value)
const isInitializing = ref(true)
const isSaving = ref(false)

const scriptId = route.params.scriptId as string
let userId = route.params.userId as string
const isEdit = ref(!!userId)
const scriptName = ref('')

const maaEndConfigLoading = ref(false)
const showMaaEndConfigMask = ref(false)
const maaEndSubscriptionId = ref<string | null>(null)
const maaEndWebsocketId = ref<string | null>(null)
let maaEndConfigTimeout: number | null = null
const resourceOptions = [{ label: '官服', value: '官服' }]
const sanityModeOptions = ref<Array<{ label: string; value: string }>>([
  { label: '固定', value: 'Fixed' },
])
const isSanityPlanMode = computed(() => formData.Info.SanityMode !== 'Fixed')
const planModeConfig = ref<MaaEndSanityConfig | null>(null)
const fullPlanData = ref<MaaEndPlanConfig | null>(null)

const getDefaultMaaEndUserData = () => ({
  Info: {
    Name: '',
    Status: true,
    Id: '',
    Password: '',
    Mode: '简洁',
    SanityMode: 'Fixed',
    Resource: '官服',
    RemainedDay: -1,
    IfSkland: false,
    SklandToken: '',
    Notes: '',
    Tag: '',
  },
  Task: {
    SanityTaskType: 'OperatorProgression',
    OperatorProgression: 'OperatorEXP',
    WeaponProgression: 'WeaponEXP',
    CrisisDrills: 'AdvancedProgression1',
    RewardsSetOption: 'RewardsSetA',
    AutoEssenceSpecifiedLocation: 'VFTheHub',
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
    LastSklandDate: '',
    ProxyTimes: 0,
    IfPassCheck: false,
  },
})

const getPlanDayConfig = (planData: MaaEndPlanConfig, dayKey: PlanWeekdayKey | 'ALL') =>
  planData[dayKey] as Partial<MaaEndSanityConfig> | null | undefined

const getPlanCurrentConfig = (planData?: MaaEndPlanConfig | null): MaaEndSanityConfig | null => {
  if (!planData) return null

  if (planData.Info?.Mode === 'Weekly') {
    const weekday = MAAEND_PLAN_WEEKDAY_KEYS[(getWeekdayInTimezone(4) + 6) % 7]
    return normalizeMaaEndSanityConfig(getPlanDayConfig(planData, weekday) ?? planData.ALL)
  }

  return normalizeMaaEndSanityConfig(planData.ALL)
}

const formatPlanValue = (
  dayConfig: Partial<MaaEndSanityConfig> | null | undefined,
  field: 'SanityTaskType' | 'CurrentTask' | 'RewardsSetOption'
) => {
  const normalized = normalizeMaaEndSanityConfig(dayConfig)

  if (field === 'SanityTaskType') {
    return SANITY_TASK_TYPE_LABEL_MAP[normalized.SanityTaskType]
  }

  if (field === 'CurrentTask') {
    return getSanityTaskDisplayValue(normalized)
  }

  return REWARD_LABEL_MAP[normalized.RewardsSetOption]
}

const getPlanTooltip = (field: 'SanityTaskType' | 'CurrentTask' | 'RewardsSetOption') => {
  if (!isSanityPlanMode.value || !fullPlanData.value) return ''

  if (fullPlanData.value.Info?.Mode !== 'Weekly') {
    return '此项由全局计划表控制'
  }

  const lines = ['此项由周计划表控制:']

  MAAEND_PLAN_WEEKDAY_KEYS.forEach(dayKey => {
    const dayConfig = getPlanDayConfig(fullPlanData.value, dayKey) ?? fullPlanData.value?.ALL
    lines.push(`${MAAEND_PLAN_TIME_LABELS[dayKey]}: ${formatPlanValue(dayConfig, field)}`)
  })

  return lines.join('\n')
}

const sanityTaskTypeTooltip = computed(() => getPlanTooltip('SanityTaskType'))
const currentTaskTooltip = computed(() => getPlanTooltip('CurrentTask'))
const rewardsTooltip = computed(() => getPlanTooltip('RewardsSetOption'))

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
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 1, max: 50, message: '用户名长度应为 1-50 个字符', trigger: 'blur' },
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

const handleFieldsSave = async (changes: FieldChange[]) => {
  await saveUserFields(changes)
}

const loadScriptInfo = async () => {
  const scriptDetail = await getScript(scriptId)
  if (scriptDetail) {
    scriptName.value = scriptDetail.name
  }
}

const loadSanityModeOptions = async () => {
  try {
    const requestBody: PlanComboxIn = { consumer: PlanComboxIn.consumer.MAAEND }
    const response = await Service.getPlanComboxApiInfoComboxPlanPost(requestBody)
    if (response?.code === 200 && response.data) {
      sanityModeOptions.value = response.data
    }
  } catch (error) {
    logger.error(
      `加载理智任务配置模式选项失败: ${error instanceof Error ? error.message : String(error)}`
    )
  }
}

const isCurrentSanityPlan = (planId: string) => formData.Info.SanityMode === planId

const loadSanityPlan = async (planId?: string | null) => {
  if (!planId || planId === 'Fixed') {
    logger.debug('切换到固定理智任务模式')
    planModeConfig.value = null
    fullPlanData.value = null
    return
  }

  try {
    logger.debug(`开始加载理智任务计划配置: ${planId}`)
    const response = await getPlans(planId)
    const planData = response?.data?.[planId] as MaaEndPlanConfig | undefined
    const planIndex = response?.index?.find(item => item.uid === planId)

    if (!isCurrentSanityPlan(planId)) {
      logger.debug(`理智任务计划配置已切换，跳过过期响应: ${planId}`)
      return
    }

    if (!planData || planIndex?.type !== PLAN_CONFIG_TYPES.MAA_END) {
      logger.warn(`理智任务计划配置响应不完整: ${JSON.stringify({ response, planId })}`)
      planModeConfig.value = null
      fullPlanData.value = null
      message.warning('计划表不存在或已失效')
      return
    }

    const currentConfig = getPlanCurrentConfig(planData)

    logger.debug(`获取到理智任务计划数据: ${JSON.stringify(planData)}`)
    logger.debug(`getPlanCurrentConfig返回: ${JSON.stringify(currentConfig)}`)

    planModeConfig.value = currentConfig
    fullPlanData.value = planData

    logger.info(
      `理智任务计划配置加载成功:${JSON.stringify({
        planId,
        currentConfig: JSON.parse(JSON.stringify(currentConfig)),
        planModeConfigValue: JSON.parse(JSON.stringify(planModeConfig.value)),
      })}`
    )

    const planOption = sanityModeOptions.value.find(option => option.value === planId)
    const planName = planOption ? planOption.label : planId

    message.success(`已切换到理智任务计划模式：${planName}`)
  } catch (error) {
    const errorInfo = {
      message: error instanceof Error ? error.message : String(error),
      stack: error instanceof Error ? error.stack : undefined,
      type: typeof error,
      name: error instanceof Error ? error.name : error?.constructor?.name,
    }
    logger.error(`加载理智任务计划配置失败: ${JSON.stringify(errorInfo)}`)
    if (planId && isCurrentSanityPlan(planId)) {
      planModeConfig.value = null
      fullPlanData.value = null
      message.error('加载计划配置时发生错误')
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

const cleanupConfigSession = () => {
  if (maaEndSubscriptionId.value) {
    unsubscribe(maaEndSubscriptionId.value)
    maaEndSubscriptionId.value = null
  }
  maaEndWebsocketId.value = null
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

    const subscriptionId = subscribe({ id: response.taskId }, (wsMessage: any) => {
      if (wsMessage.type === 'error') {
        message.error(`MaaEnd 配置连接失败: ${wsMessage.data}`)
        cleanupConfigSession()
        return
      }

      if (wsMessage.type === 'Info' && wsMessage.data?.Error) {
        message.error(`MaaEnd 配置异常: ${wsMessage.data.Error}`)
        return
      }

      if (wsMessage.type === 'Signal' && wsMessage.data?.Accomplish !== undefined) {
        cleanupConfigSession()
      }
    })

    maaEndSubscriptionId.value = subscriptionId
    maaEndWebsocketId.value = response.taskId
    showMaaEndConfigMask.value = true
    message.success(`已启动用户 ${formData.Info.Name || formData.userName} 的 MaaEnd 配置`)

    maaEndConfigTimeout = window.setTimeout(
      () => {
        cleanupConfigSession()
        message.info('MaaEnd 配置会话已超时断开')
      },
      30 * 60 * 1000
    )
  } catch (error) {
    message.error(error instanceof Error ? error.message : '启动 MaaEnd 配置失败')
  } finally {
    maaEndConfigLoading.value = false
  }
}

const handleSaveMaaEndConfig = async () => {
  try {
    if (!maaEndWebsocketId.value) {
      throw new Error('未找到活动配置会话')
    }

    const response = await Service.stopTaskApiDispatchStopPost({ taskId: maaEndWebsocketId.value })
    if (response.code !== 200) {
      throw new Error(response.message || '保存配置失败')
    }

    cleanupConfigSession()
    message.success('MaaEnd 配置已保存')
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
  await loadSanityModeOptions()

  watch(
    () => formData.Info.SanityMode,
    async newMode => {
      await loadSanityPlan(newMode)
    },
    { immediate: false }
  )

  if (isEdit.value) {
    await loadUserData()
  } else {
    const result = await addUser(scriptId)
    if (result?.userId) {
      userId = result.userId
      isEdit.value = true
    } else {
      message.error('创建用户失败')
      router.push('/scripts')
      return
    }
  }

  await nextTick()
  isInitializing.value = false
})
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
