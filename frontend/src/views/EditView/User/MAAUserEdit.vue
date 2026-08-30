<template>
  <div class="user-edit-container">
    <!-- MAA配置遮罩层 -->
    <teleport to="body">
      <div v-if="showMAAConfigMask" class="maa-config-mask">
        <div class="mask-content">
          <div class="mask-icon">
            <SettingOutlined :style="{ fontSize: '48px', color: '#1890ff' }" />
          </div>
          <h2 class="mask-title">{{ t('edit.maaConfigurationProgress') }}</h2>
          <p class="mask-description">
            {{ t('edit.maaConfigurationThisUser') }}
            <br />
            配置完成后，请点击"保存配置"按钮来结束配置会话。
          </p>
          <div class="mask-actions">
            <a-button v-if="maaTaskId" type="primary" size="large" @click="handleSaveMAAConfig">
              {{ t('edit.saveConfiguration') }}
            </a-button>
          </div>
        </div>
      </div>
    </teleport>
    <!-- 头部组件 -->
    <MAAUserEditHeader
      :script-id="scriptId"
      :script-name="scriptName"
      :is-edit="isEdit"
      :user-mode="formData.Info.Mode"
      :maa-config-loading="maaConfigLoading"
      :show-maa-config-mask="showMAAConfigMask"
      :loading="loading"
      @handle-m-a-a-config="handleMAAConfig"
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
          <!-- 基本信息组件 -->
          <BasicInfoSection
            v-model:form-data="formData"
            :loading="loading"
            :server-options="serverOptions"
            @save="handleFieldSave"
          />

          <!-- 任务配置：明确区分剿灭与日常的两次 MAA 启动 -->
          <TaskPipelineSection
            v-model:form-data="formData"
            :loading="loading"
            :is-plan-mode="isPlanMode"
            :stage-options="stageOptions"
            :activity-stage-options="activityStageOptions"
            :activity-stage-loading="activityStageLoading"
            :activity-stage-error="activityStageError"
            :display-activity-stage-index="displayActivityStageIndex"
            :depot-item-options="depotItemOptions"
            :depot-item-options-loading="depotItemOptionsLoading"
            :depot-item-options-error="depotItemOptionsError"
            :fight-summary="fightSummary"
            :is-edit="isEdit"
            :infrastructure-importing="infrastructureImporting"
            :infrastructure-options="infrastructureOptions"
            :infrastructure-options-loading="infrastructureOptionsLoading"
            @select-and-import-infrastructure-config="selectAndImportInfrastructureConfig"
            @save="handleFieldSave"
          >
            <template #fight-detail>
              <StageConfigSection
                v-model:form-data="formData"
                :loading="loading"
                :stage-mode-options="stageModeOptions"
                :stage-options="stageOptions"
                :stage-remain-options="stageRemainOptions"
                :is-plan-mode="isPlanMode"
                :display-medicine-numb="displayMedicineNumb"
                :display-series-numb="displaySeriesNumb"
                :display-stage="displayStage"
                :display-stage1="displayStage1"
                :display-stage2="displayStage2"
                :display-stage3="displayStage3"
                :display-stage-remain="displayStageRemain"
                :medicine-numb-tooltip="medicineNumbTooltip"
                :series-numb-tooltip="seriesNumbTooltip"
                :stage-tooltip="stageTooltip"
                :stage1-tooltip="stage1Tooltip"
                :stage2-tooltip="stage2Tooltip"
                :stage3-tooltip="stage3Tooltip"
                :stage-remain-tooltip="stageRemainTooltip"
                @update-medicine-numb="updateMedicineNumb"
                @update-series-numb="updateSeriesNumb"
                @update-stage="updateStage"
                @update-stage1="updateStage1"
                @update-stage2="updateStage2"
                @update-stage3="updateStage3"
                @update-stage-remain="updateStageRemain"
                @handle-add-custom-stage="addCustomStage"
                @handle-add-custom-stage1="addCustomStage1"
                @handle-add-custom-stage2="addCustomStage2"
                @handle-add-custom-stage3="addCustomStage3"
                @handle-add-custom-stage-remain="addCustomStageRemain"
                @save="handleFieldSave"
              />
            </template>
          </TaskPipelineSection>

          <!-- 额外脚本组件 -->
          <ExtraScriptSection
            v-model:form-data="formData"
            :loading="loading"
            @save="handleFieldSave"
          />

          <!-- 通知配置组件 -->
          <NotifyConfigSection
            v-model:form-data="formData"
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
import { useUserApi } from '@/composables/useUserApi.ts'
import { useScriptApi } from '@/composables/useScriptApi.ts'
import { usePlanApi } from '@/composables/usePlanApi.ts'
import { useWebSocket } from '@/composables/useWebSocket.ts'
import {
  WS_TASK_COMPLETED,
  WS_TASK_NOTICE,
  type WSTaskCompletedData,
  type WSTaskNoticeData,
} from '@/services/websocket/types'
import { Service } from '@/api'
import { PlanComboxIn } from '@/api/models/PlanComboxIn.ts'
import { TaskCreateIn } from '@/api/models/TaskCreateIn.ts'
import { getWeekdayInTimezone } from '@/utils/dateUtils.ts'
import type { HomeOverviewResponse } from '@/types/home.ts'

const logger = window.electronAPI.getLogger('MAA用户编辑')

// 导入拆分的组件
import MAAUserEditHeader from '@/views/MAAUserEdit/MAAUserEditHeader.vue'
import BasicInfoSection from '@/views/MAAUserEdit/BasicInfoSection.vue'
import StageConfigSection from '@/views/MAAUserEdit/StageConfigSection.vue'
import TaskPipelineSection from '@/views/MAAUserEdit/TaskPipelineSection.vue'
import { summarizeFight } from '@/views/MAAUserEdit/taskSummaries'
import NotifyConfigSection from '@/views/MAAUserEdit/NotifyConfigSection.vue'
import ExtraScriptSection from '@/components/ExtraScriptSection.vue'

const { t } = useI18n()

const router = useRouter()
const route = useRoute()
const { addUser, updateUser, getUsers, loading: userLoading, error: userError } = useUserApi()
const { getScript } = useScriptApi()
const { getPlans } = usePlanApi()
const { subscribe, unsubscribe } = useWebSocket()

const formRef = ref<FormInstance>()
const loading = computed(() => userLoading.value)
const isInitializing = ref(true) // 标记是否正在初始化
const isSaving = ref(false) // 标记是否正在保存
const pendingFieldSaves = new Map<string, any>()
let fieldSavePromise: Promise<boolean> | null = null

const reportFieldSaveFailure = () => {
  const errorMsg = userError.value
  if (!errorMsg || errorMsg.includes('HTTP error')) {
    message.error(t('edit.couldNotSaveUser'))
  }
  logger.error(`保存失败: ${errorMsg || '用户 API 未返回成功'}`)
}

// 路由参数
const scriptId = route.params.scriptId as string
let userId = route.params.userId as string
const isEdit = ref(!!userId) // 使用 ref 以便在创建后更新

// 脚本信息
const scriptName = ref('')

// MAA配置相关
const maaConfigLoading = ref(false)
const maaSubscriptionIds = ref<string[]>([])
const maaTaskId = ref<string | null>(null)
const showMAAConfigMask = ref(false)
let maaConfigTimeout: number | null = null

// 基建配置文件相关
const infrastructureImporting = ref(false)
const infrastructureOptions = ref<Array<{ label: string; value: string }>>([])
const infrastructureOptionsLoading = ref(false)

// 库存保持物品选项
const depotItemOptions = ref<Array<{ label: string; value: string }>>([])
const depotItemOptionsLoading = ref(false)
const depotItemOptionsError = ref('')

// 服务器选项
const serverOptions = [
  { label: '官服', value: 'Official' },
  { label: 'B服', value: 'Bilibili' },
  { label: '国际服（YoStarEN）', value: 'YoStarEN' },
  { label: '日服（YoStarJP）', value: 'YoStarJP' },
  { label: '韩服（YoStarKR）', value: 'YoStarKR' },
  { label: '繁中服（txwy）', value: 'txwy' },
]

// 关卡选项
const stageOptions = ref<any[]>([{ label: '不选择', value: '' }])
const activityStageOptions = ref<Array<{ label: string; value: number }>>([])
const activityStageLoading = ref(false)
const activityStageError = ref('')
const stageOverviewByServer = ref<HomeOverviewResponse['StageByServer']>({})

// 剩余理智关卡专用选项（将"当前/上次"改为"不选择"）
const stageRemainOptions = computed(() => {
  return stageOptions.value.map(option => {
    if (option.value === '-') {
      return { ...option, label: option.label.replace('当前/上次', '不选择') }
    }
    return option
  })
})

// 判断值是否为自定义关卡
const isCustomStage = (value: string) => {
  if (!value || value === '' || value === '-') return false

  // 检查是否在从API加载的关卡列表中
  const predefinedStage = stageOptions.value.find(
    option => option.value === value && !option.isCustom
  )

  return !predefinedStage
}

// 关卡配置模式选项
const stageModeOptions = ref<any[]>([{ label: '固定', value: 'Fixed' }])

// 计划模式状态
const isPlanMode = computed(() => {
  return formData.Info.StageMode !== 'Fixed'
})
const planModeConfig = ref<any>(null)
// 新增：存储完整的计划数据用于悬浮提示
const fullPlanData = ref<any>(null)

// 新增：生成计划表悬浮提示内容的函数
const getPlanTooltip = (fieldName: string) => {
  if (!fullPlanData.value || !isPlanMode.value) return ''

  const planData = fullPlanData.value
  const mode = planData.Info?.Mode || 'ALL'

  if (mode === 'ALL') {
    return '此项由全局计划表控制'
  } else if (mode === 'Weekly') {
    const weekdays = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    const weekdaysZh = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

    let tooltip = '此项由周计划表控制:\n'

    weekdays.forEach((day, index) => {
      const dayConfig = planData[day]
      let value = ''

      if (dayConfig && dayConfig[fieldName] !== undefined) {
        value = dayConfig[fieldName]
      } else if (planData.ALL && planData.ALL[fieldName] !== undefined) {
        value = planData.ALL[fieldName] + ' (全局)'
      } else {
        value = '未设置'
      }

      // 格式化特殊字段的显示
      if (fieldName === 'SeriesNumb') {
        if (value === '0') value = 'AUTO'
        else if (value === '-1') value = '不切换'
      } else if (
        fieldName === 'Stage' ||
        fieldName === 'Stage_1' ||
        fieldName === 'Stage_2' ||
        fieldName === 'Stage_3'
      ) {
        if (value === '-') value = '当前/上次'
        else if (value === '') value = '不选择'
      } else if (fieldName === 'Stage_Remain') {
        if (value === '-') value = '不选择'
        else if (value === '') value = '不选择'
      }

      tooltip += `${weekdaysZh[index]}: ${value}\n`
    })

    return tooltip.trim()
  }

  return ''
}

// 新增：各字段的悬浮提示计算属性
const medicineNumbTooltip = computed(() => getPlanTooltip('MedicineNumb'))
const seriesNumbTooltip = computed(() => getPlanTooltip('SeriesNumb'))
const stageTooltip = computed(() => getPlanTooltip('Stage'))
const stage1Tooltip = computed(() => getPlanTooltip('Stage_1'))
const stage2Tooltip = computed(() => getPlanTooltip('Stage_2'))
const stage3Tooltip = computed(() => getPlanTooltip('Stage_3'))
const stageRemainTooltip = computed(() => getPlanTooltip('Stage_Remain'))

// 计算属性用于显示正确的值（来自计划表或用户配置）
const displayMedicineNumb = computed({
  get: () => {
    if (isPlanMode.value && planModeConfig.value?.MedicineNumb !== undefined) {
      return planModeConfig.value.MedicineNumb
    }
    return formData.Info.MedicineNumb
  },
  set: value => {
    if (!isPlanMode.value) {
      formData.Info.MedicineNumb = value
    }
  },
})

const displaySeriesNumb = computed({
  get: () => {
    if (isPlanMode.value && planModeConfig.value?.SeriesNumb !== undefined) {
      return planModeConfig.value.SeriesNumb
    }
    return formData.Info.SeriesNumb
  },
  set: value => {
    if (!isPlanMode.value) {
      formData.Info.SeriesNumb = value
    }
  },
})

const displayStage = computed({
  get: () => {
    if (isPlanMode.value && planModeConfig.value?.Stage !== undefined) {
      return planModeConfig.value.Stage
    }
    return formData.Info.Stage
  },
  set: value => {
    if (!isPlanMode.value) {
      formData.Info.Stage = value
    }
  },
})

const displayStage1 = computed({
  get: () => {
    if (isPlanMode.value && planModeConfig.value?.Stage_1 !== undefined) {
      return planModeConfig.value.Stage_1
    }
    return formData.Info.Stage_1
  },
  set: value => {
    if (!isPlanMode.value) {
      formData.Info.Stage_1 = value
    }
  },
})

const displayStage2 = computed({
  get: () => {
    if (isPlanMode.value && planModeConfig.value?.Stage_2 !== undefined) {
      return planModeConfig.value.Stage_2
    }
    return formData.Info.Stage_2
  },
  set: value => {
    if (!isPlanMode.value) {
      formData.Info.Stage_2 = value
    }
  },
})

const displayStage3 = computed({
  get: () => {
    if (isPlanMode.value && planModeConfig.value?.Stage_3 !== undefined) {
      return planModeConfig.value.Stage_3
    }
    return formData.Info.Stage_3
  },
  set: value => {
    if (!isPlanMode.value) {
      formData.Info.Stage_3 = value
    }
  },
})

const displayStageRemain = computed({
  get: () => {
    if (isPlanMode.value && planModeConfig.value?.Stage_Remain !== undefined) {
      return planModeConfig.value.Stage_Remain
    }
    return formData.Info.Stage_Remain
  },
  set: value => {
    if (!isPlanMode.value) {
      formData.Info.Stage_Remain = value
    }
  },
})

// 获取计划当前配置
const getPlanCurrentConfig = (planData: any) => {
  if (!planData) return null

  const mode = planData.Info?.Mode || 'ALL'

  if (mode === 'ALL') {
    return planData.ALL || null
  } else if (mode === 'Weekly') {
    // 使用东4区时区的今天是星期几（已经是数字0-6）
    const todayWeekday = getWeekdayInTimezone(4)

    const weekdays = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    const today = weekdays[todayWeekday]

    logger.debug(`计划表周模式调试: 
      东4区星期几: ${todayWeekday},
      星期: ${today},
      计划数据: ${JSON.stringify(planData)}`)

    // 优先使用今天的配置，如果没有或为空则使用ALL配置
    const todayConfig = planData[today]

    if (todayConfig && typeof todayConfig === 'object' && Object.keys(todayConfig).length > 0) {
      logger.debug(`使用今日配置: ${JSON.stringify(todayConfig)}`)
      return todayConfig
    }

    const allConfig = planData.ALL || null
    logger.debug(`使用ALL配置: ${JSON.stringify(allConfig)}`)
    return allConfig
  }

  logger.debug('计划模式未知，返回null')
  return null
}

// MAA脚本默认用户数据
const getDefaultMAAUserData = () => ({
  Info: {
    Name: '',
    Id: '',
    Password: '',
    Server: 'Official',
    MedicineNumb: 0,
    RemainedDay: -1,
    IfScriptBeforeTask: false,
    ScriptBeforeTask: '',
    IfScriptAfterTask: false,
    ScriptAfterTask: '',
    SeriesNumb: '0',
    Notes: '',
    Status: true,
    Mode: '简洁',
    InfrastMode: 'Normal',
    InfrastName: '',
    InfrastIndex: '',
    Annihilation: 'Annihilation',
    Stage: '1-7',
    StageMode: 'Fixed',
    Stage_1: '',
    Stage_2: '',
    Stage_3: '',
    Stage_Remain: '',
  },
  Task: {
    IfStartUp: true,
    IfInfrast: true,
    IfFight: true,
    IfMall: true,
    IfAward: true,
    IfRecruit: true,
    IfReclamation: false,
    IfRoguelike: false,
    IfDepotMaintain: false,
    IfActivityFirst: false,
    ActivityStageIndex: 1,
    ActivityMedicineNumb: 0,
    DepotMaintainPlans: '[]',
  },
  Notify: {
    Enabled: false,
    ToAddress: '',
    IfSendMail: false,
    IfSendSixStar: false,
    IfSendStatistic: false,
    IfServerChan: false,
    ServerChanKey: '',
    ServerChanChannel: '',
    ServerChanTag: '',
    CustomWebhooks: [],
  },
  Data: {
    LastProxyDate: '',
    ProxyTimes: 0,
  },
})

// 创建扁平化的表单数据，用于表单验证
const formData = reactive({
  // 扁平化的验证字段
  userName: '',
  userId: '',
  // 嵌套的实际数据
  ...getDefaultMAAUserData(),
})

const displayActivityStageIndex = computed(() => {
  const configuredIndex = formData.Task.ActivityStageIndex
  return activityStageOptions.value.some(option => option.value === configuredIndex)
    ? configuredIndex
    : activityStageOptions.value[0]?.value
})

// 折叠态摘要：不展开也能确认当前生效的关卡配置
const fightSummary = computed(() =>
  summarizeFight({
    enabled: formData.Task.IfFight,
    planLabel: isPlanMode.value
      ? stageModeOptions.value.find(option => option.value === formData.Info.StageMode)?.label ||
        formData.Info.StageMode
      : '',
    stage: displayStage.value,
    series: displaySeriesNumb.value,
    medicine: displayMedicineNumb.value ?? 0,
    remain: displayStageRemain.value,
  })
)

// 表单验证规则
const rules = computed(() => {
  const baseRules: Record<string, Rule[]> = {
    userName: [
      { required: true, message: '请输入用户名', trigger: 'blur' },
      { min: 1, max: 50, message: '用户名长度应在1-50个字符之间', trigger: 'blur' },
    ],
  }
  return baseRules
})

// 同步扁平化字段与嵌套数据
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
  () => formData.Info.Id,
  newVal => {
    if (formData.userId !== newVal) {
      formData.userId = newVal || ''
    }
  },
  { immediate: true }
)

// 基建配置名称和索引保持独立，不自动同步

watch(
  () => formData.userName,
  newVal => {
    if (formData.Info.Name !== newVal) {
      formData.Info.Name = newVal || ''
    }
  }
)

watch(
  () => formData.userId,
  newVal => {
    if (formData.Info.Id !== newVal) {
      formData.Info.Id = newVal || ''
    }
  }
)

// 即时保存单个字段变更。保存中的后续变更保留最后一次值，避免被 isSaving 直接丢弃。
const handleFieldSave = async (key: string, value: any): Promise<boolean> => {
  if (isInitializing.value || !userId) return false

  pendingFieldSaves.set(key, value)
  if (fieldSavePromise) return fieldSavePromise

  const savePromise = (async (): Promise<boolean> => {
    isSaving.value = true
    try {
      while (pendingFieldSaves.size > 0) {
        const pendingEntry = pendingFieldSaves.entries().next().value as [string, any] | undefined
        if (!pendingEntry) break

        const [pendingKey, pendingValue] = pendingEntry
        pendingFieldSaves.delete(pendingKey)

        // 解析 key 路径，例如 "Info.Status" -> { Info: { Status: value } }
        const parts = pendingKey.split('.')
        let userData: Record<string, any> = {}
        let current = userData
        let localTarget: any = formData

        for (let i = 0; i < parts.length - 1; i++) {
          current[parts[i]] = {}
          current = current[parts[i]]
          localTarget = localTarget[parts[i]]
        }
        current[parts[parts.length - 1]] = pendingValue
        localTarget[parts[parts.length - 1]] = pendingValue

        // 特殊处理：userName 和 userId 需要同步到 Info
        if (pendingKey === 'userName') {
          userData = { Info: { Name: pendingValue } }
        } else if (pendingKey === 'userId') {
          userData = { Info: { Id: pendingValue } }
        }

        const success = await updateUser(scriptId, userId, userData)
        if (!success) {
          pendingFieldSaves.clear()
          reportFieldSaveFailure()
          return false
        }

        logger.info(`用户配置已保存: ${pendingKey}`)
      }
      return true
    } catch (error) {
      pendingFieldSaves.clear()
      reportFieldSaveFailure()
      if (error instanceof Error) {
        logger.error(`保存异常: ${error.message}`)
      }
      return false
    } finally {
      isSaving.value = false
      fieldSavePromise = null
    }
  })()
  fieldSavePromise = savePromise

  return savePromise
}

// 保存完整用户数据（仅用于特殊批量操作）
const _saveFullUserData = async () => {
  if (isInitializing.value || isSaving.value || !userId) return

  isSaving.value = true
  try {
    // 确保扁平化字段同步到嵌套数据
    formData.Info.Name = formData.userName
    formData.Info.Id = formData.userId

    const userData = {
      Info: { ...formData.Info },
      Task: { ...formData.Task },
      Notify: { ...formData.Notify },
      Data: { ...formData.Data },
    }

    await updateUser(scriptId, userId, userData)
    logger.info('用户配置已保存')
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存失败: ${errorMsg}`)
  } finally {
    isSaving.value = false
  }
}

// 注意：移除了 watch 自动保存，现在由子组件的 @save 事件触发保存

// 加载脚本信息
const loadScriptInfo = async () => {
  try {
    const script = await getScript(scriptId)
    if (script) {
      scriptName.value = script.name

      // 如果是编辑模式，加载用户数据
      if (isEdit.value) {
        await loadUserData()
      } else {
        // 新增模式：立即创建用户获取 ID
        await createUserImmediately()
      }
    } else {
      message.error(t('edit.scriptDoesNotExist2'))
      handleCancel()
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载脚本信息失败: ${errorMsg}`)
    message.error(t('edit.couldNotLoadScript2'))
  }
}

// 新增模式下立即创建用户
const createUserImmediately = async () => {
  try {
    const result = await addUser(scriptId)
    if (result && result.userId) {
      userId = result.userId
      isEdit.value = true
      // 更新路由，但不刷新页面
      router.replace({
        name: route.name || undefined,
        params: { ...route.params, userId: result.userId },
      })
      logger.info(`用户已创建，ID: ${result.userId}`)
      // 加载新创建用户的数据
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

// 加载用户数据
const loadUserData = async () => {
  try {
    const userResponse = await getUsers(scriptId, userId)

    if (userResponse && userResponse.code === 200) {
      // 查找指定的用户数据
      const userIndex = userResponse.index.find(index => index.uid === userId)
      if (userIndex && userResponse.data[userId]) {
        const userData = userResponse.data[userId] as any

        // 填充MAA用户数据
        if (userIndex.type === 'MaaUserConfig') {
          Object.assign(formData, {
            Info: { ...getDefaultMAAUserData().Info, ...userData.Info },
            Task: { ...getDefaultMAAUserData().Task, ...userData.Task },
            Notify: { ...getDefaultMAAUserData().Notify, ...userData.Notify },
            Data: { ...getDefaultMAAUserData().Data, ...userData.Data },
          })
        }

        // 同步扁平字段 - 使用nextTick确保数据更新完成后再同步
        await nextTick()
        formData.userName = formData.Info.Name || ''
        formData.userId = formData.Info.Id || ''

        appendConfiguredCustomStages()

        logger.info('用户数据加载成功')

        // 加载基建配置选项
        await loadInfrastructureOptions()

        // 数据加载完成，允许自动保存
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
  }
}

const appendConfiguredCustomStages = () => {
  const stageFields = ['Stage', 'Stage_1', 'Stage_2', 'Stage_3', 'Stage_Remain']
  stageFields.forEach(field => {
    const stageValue = (formData.Info as any)[field]
    if (stageValue && isCustomStage(stageValue)) {
      const exists = stageOptions.value.find((option: any) => option.value === stageValue)
      if (!exists) {
        stageOptions.value.push({
          label: stageValue,
          value: stageValue,
          isCustom: true,
        })
      }
    }
  })
}

const applyServerStageOptions = () => {
  const server = formData.Info.Server === 'Bilibili' ? 'Official' : formData.Info.Server
  const stageOverview = stageOverviewByServer.value[server]
  if (!stageOverview) {
    return
  }

  stageOptions.value = stageOverview.Options.map(option => ({
    ...option,
    isCustom: false,
  }))
  appendConfiguredCustomStages()
  activityStageOptions.value = stageOverview.Activity.map((stage, index) => ({
    label: `${index + 1}. ${stage.Activity.StageName} · ${stage.Display} · ${stage.DropName}`,
    value: index + 1,
  }))
}

const loadActivityStageOptions = async () => {
  activityStageLoading.value = true
  activityStageError.value = ''
  try {
    const response = await Service.getOverviewApiInfoGetOverviewPost()
    if (response.code !== 200) {
      activityStageError.value = response.message || '加载活动关卡失败'
      return
    }

    const overview = response.data as HomeOverviewResponse
    stageOverviewByServer.value = overview.StageByServer
    applyServerStageOptions()
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载活动关卡失败: ${errorMsg}`)
    activityStageError.value = '加载活动关卡失败'
  } finally {
    activityStageLoading.value = false
  }
}

const loadDepotItemOptions = async () => {
  depotItemOptionsLoading.value = true
  depotItemOptionsError.value = ''
  try {
    const response = await Service.getMaaDepotItemsApiScriptsMaaDepotItemsPost({ scriptId })
    if (response.code !== 200) {
      depotItemOptionsError.value = response.message || '加载 MAA 库存物品失败'
      return
    }
    depotItemOptions.value = response.data
      .filter(option => option.value)
      .map(option => ({ label: option.label, value: option.value as string }))
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载 MAA 库存物品失败: ${errorMsg}`)
    depotItemOptionsError.value = '加载 MAA 库存物品失败'
  } finally {
    depotItemOptionsLoading.value = false
  }
}

const loadStageModeOptions = async () => {
  try {
    const response = await Service.getPlanComboxApiInfoComboxPlanPost({
      consumer: PlanComboxIn.consumer.MAA,
    })
    if (response && response.code === 200 && response.data) {
      stageModeOptions.value = response.data
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载关卡配置模式选项失败: ${errorMsg}`)
    // 保持默认的固定选项
  }
}

// 选择并导入基建配置文件
const selectAndImportInfrastructureConfig = async () => {
  if (!isEdit.value) {
    message.warning(t('edit.saveUserBeforeImporting'))
    return
  }

  try {
    // 选择文件
    const path = await window.electronAPI?.selectFile([
      { name: t('edit.jsonFiles'), extensions: ['json'] },
      { name: t('edit.allFiles'), extensions: ['*'] },
    ])

    if (path && path.length > 0) {
      infrastructureImporting.value = true

      // 直接导入配置
      const result = await Service.importInfrastructureApiScriptsUserInfrastructurePost({
        scriptId: scriptId,
        userId: userId,
        jsonFile: path[0],
      })

      if (result && result.code === 200) {
        // 从文件路径中提取文件名作为 InfrastName
        const fileName = path[0].split('\\').pop()?.split('/').pop() || ''
        formData.Info.InfrastName = fileName.replace('.json', '')
        // 清空 InfrastIndex，等待用户从下拉框中选择
        formData.Info.InfrastIndex = ''

        message.success(t('edit.baseConfigurationImported'))

        // 重新加载基建配置选项
        await loadInfrastructureOptions()
      } else {
        message.error(t('edit.couldNotImportBase'))
      }
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`基建配置导入失败: ${errorMsg}`)
    message.error(t('edit.couldNotImportBase'))
  } finally {
    infrastructureImporting.value = false
  }
}

// 加载基建配置选项
const loadInfrastructureOptions = async () => {
  if (!isEdit.value) return

  try {
    infrastructureOptionsLoading.value = true
    const result = await Service.getUserComboxInfrastructureApiScriptsUserComboxInfrastructurePost({
      scriptId: scriptId,
      userId: userId,
    })

    if (result && result.code === 200 && result.data) {
      infrastructureOptions.value = result.data.map((item: any) => ({
        label: item.label,
        value: item.value,
      }))
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载基建配置选项失败: ${errorMsg}`)
  } finally {
    infrastructureOptionsLoading.value = false
  }
}

const handleMAAConfig = async () => {
  try {
    maaConfigLoading.value = true

    // 如果已有连接，先断开
    if (maaSubscriptionIds.value.length > 0) {
      for (const subscriptionId of maaSubscriptionIds.value) {
        unsubscribe(subscriptionId)
      }
      maaSubscriptionIds.value = []
      maaTaskId.value = null
      showMAAConfigMask.value = false
      if (maaConfigTimeout) {
        window.clearTimeout(maaConfigTimeout)
        maaConfigTimeout = null
      }
    }

    // 调用后端启动任务接口，传入 userId 作为 taskId 与设置模式
    const response = await Service.addTaskApiDispatchStartPost({
      taskId: userId,
      mode: TaskCreateIn.mode.SCRIPT_CONFIG,
    })

    if (response && response.taskId) {
      const wsId = response.taskId

      // 订阅 websocket
      const subscriptionIds = [
        // 处理任务提示中的错误消息（不取消订阅，等待任务结束消息）
        subscribe({ id: wsId, type: WS_TASK_NOTICE }, wsMessage => {
          const data = wsMessage.data as unknown as WSTaskNoticeData
          if (data.level === 'error') {
            logger.error(
              `用户 ${formData.Info?.Name || formData.userName} MAA配置异常:${data.message}`
            )
            message.error(`MAA配置失败: ${data.message}`)
          }
        }),
        // 处理任务结束消息
        subscribe({ id: wsId, type: WS_TASK_COMPLETED }, wsMessage => {
          const data = wsMessage.data as unknown as WSTaskCompletedData
          logger.info(`用户 ${formData.Info?.Name || formData.userName} MAA配置任务已结束`)
          // 根据结果显示不同消息
          if (data.outcome === 'success') {
            message.success(`用户 ${formData.Info?.Name || formData.userName} 的配置已完成`)
          }
          // 清理连接
          for (const subscriptionId of maaSubscriptionIds.value) {
            unsubscribe(subscriptionId)
          }
          maaSubscriptionIds.value = []
          maaTaskId.value = null
          showMAAConfigMask.value = false
          if (maaConfigTimeout) {
            window.clearTimeout(maaConfigTimeout)
            maaConfigTimeout = null
          }
        }),
      ]

      maaSubscriptionIds.value = subscriptionIds
      maaTaskId.value = wsId
      showMAAConfigMask.value = true
      message.success(`已开始配置用户 ${formData.Info?.Name || formData.userName} 的MAA设置`)

      // 设置 30 分钟超时自动断开
      maaConfigTimeout = window.setTimeout(
        () => {
          if (maaSubscriptionIds.value.length > 0) {
            for (const subscriptionId of maaSubscriptionIds.value) {
              unsubscribe(subscriptionId)
            }
            maaSubscriptionIds.value = []
            maaTaskId.value = null
            showMAAConfigMask.value = false
            message.info(`用户 ${formData.Info?.Name || formData.userName} 的配置会话已超时断开`)
          }
          maaConfigTimeout = null
        },
        30 * 60 * 1000
      )
    } else {
      message.error(response?.message || '启动MAA配置失败')
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`启动MAA配置失败: ${errorMsg}`)
    message.error(t('edit.couldNotStartMaa'))
  } finally {
    maaConfigLoading.value = false
  }
}

const handleSaveMAAConfig = async () => {
  try {
    const taskId = maaTaskId.value
    if (!taskId) {
      message.error(t('edit.noActiveConfigurationSession'))
      return
    }

    const response = await Service.stopTaskApiDispatchStopPost({ taskId })
    if (response && response.code === 200) {
      for (const subscriptionId of maaSubscriptionIds.value) {
        unsubscribe(subscriptionId)
      }
      maaSubscriptionIds.value = []
      maaTaskId.value = null
      showMAAConfigMask.value = false
      if (maaConfigTimeout) {
        window.clearTimeout(maaConfigTimeout)
        maaConfigTimeout = null
      }
      message.success(t('edit.configurationThisUserWas'))
    } else {
      message.error(response.message || '保存配置失败')
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存MAA配置失败: ${errorMsg}`)
    message.error(t('edit.couldNotSaveMaa'))
  }
}

// 验证关卡名称格式
const validateStageName = (stageName: string): boolean => {
  if (!stageName || !stageName.trim()) {
    return false
  }

  // 简单的关卡名称验证，可以根据实际需要调整
  const stagePattern = /^[a-zA-Z0-9\-_\u4e00-\u9fa5]+$/
  return stagePattern.test(stageName.trim())
}

type StageField = 'Stage' | 'Stage_1' | 'Stage_2' | 'Stage_3' | 'Stage_Remain'

const updateStageField = (field: StageField, value: string) => {
  if (isPlanMode.value) return

  formData.Info[field] = value
  void handleFieldSave(`Info.${field}`, value)
}

// 添加自定义关卡到选项列表
const addStageToOptions = (stageName: string) => {
  if (!stageName || !stageName.trim()) {
    return false
  }

  const trimmedName = stageName.trim()

  // 检查是否已存在
  const exists = stageOptions.value.find((option: any) => option.value === trimmedName)
  if (exists) {
    message.warning(`关卡 "${trimmedName}" 已存在`)
    return false
  }

  // 添加到选项列表
  stageOptions.value.push({
    label: trimmedName,
    value: trimmedName,
    isCustom: true,
  })

  message.success(`自定义关卡 "${trimmedName}" 添加成功`)
  return true
}

// 添加主关卡
const addCustomStage = (stageName: string) => {
  if (!validateStageName(stageName)) {
    message.error(t('edit.enterValidStageName'))
    return
  }

  if (addStageToOptions(stageName)) {
    updateStageField('Stage', stageName.trim())
  }
}

// 添加备选关卡-1
const addCustomStage1 = (stageName: string) => {
  if (!validateStageName(stageName)) {
    message.error(t('edit.enterValidStageName'))
    return
  }

  if (addStageToOptions(stageName)) {
    updateStageField('Stage_1', stageName.trim())
  }
}

// 添加备选关卡-2
const addCustomStage2 = (stageName: string) => {
  if (!validateStageName(stageName)) {
    message.error(t('edit.enterValidStageName'))
    return
  }

  if (addStageToOptions(stageName)) {
    updateStageField('Stage_2', stageName.trim())
  }
}

// 添加备选关卡-3
const addCustomStage3 = (stageName: string) => {
  if (!validateStageName(stageName)) {
    message.error(t('edit.enterValidStageName'))
    return
  }

  if (addStageToOptions(stageName)) {
    updateStageField('Stage_3', stageName.trim())
  }
}

// 添加剩余理智关卡
const addCustomStageRemain = (stageName: string) => {
  if (!validateStageName(stageName)) {
    message.error(t('edit.enterValidStageName'))
    return
  }

  if (addStageToOptions(stageName)) {
    updateStageField('Stage_Remain', stageName.trim())
  }
}

const handleCancel = async () => {
  const pendingSave = fieldSavePromise
  if (pendingSave && !(await pendingSave)) return

  if (maaSubscriptionIds.value.length > 0) {
    for (const subscriptionId of maaSubscriptionIds.value) {
      unsubscribe(subscriptionId)
    }
    maaSubscriptionIds.value = []
    maaTaskId.value = null
  }
  router.push('/scripts')
}
const updateMedicineNumb = (value: number) => {
  if (!isPlanMode.value) {
    formData.Info.MedicineNumb = value
    handleFieldSave('Info.MedicineNumb', value)
  }
}

const updateSeriesNumb = (value: string) => {
  if (!isPlanMode.value) {
    formData.Info.SeriesNumb = value
    handleFieldSave('Info.SeriesNumb', value)
  }
}

const updateStage = (value: string) => {
  updateStageField('Stage', value)
}

const updateStage1 = (value: string) => {
  updateStageField('Stage_1', value)
}

const updateStage2 = (value: string) => {
  updateStageField('Stage_2', value)
}

const updateStage3 = (value: string) => {
  updateStageField('Stage_3', value)
}

const updateStageRemain = (value: string) => {
  updateStageField('Stage_Remain', value)
}

watch(
  () => formData.Info.Server,
  () => applyServerStageOptions()
)

// 初始化加载
onMounted(() => {
  if (!scriptId) {
    message.error(t('edit.missingScriptIdParameter'))
    handleCancel()
    return
  }

  loadScriptInfo()
  loadStageModeOptions()
  loadActivityStageOptions()
  loadDepotItemOptions()

  // 如果是编辑模式，在用户数据加载后会自动加载基建配置选项
  // 如果是新建模式，也尝试加载基建配置选项（如果已经有用户ID）
  if (isEdit.value) {
    // 编辑模式会在 loadUserData 中加载
  } else {
    // 新建模式暂时不加载，等保存后再加载
  }

  // 设置StageMode变化监听器
  watch(
    () => formData.Info.StageMode,
    async newStageMode => {
      if (newStageMode === 'Fixed') {
        // 切换到固定模式，清除计划配置
        logger.debug('切换到固定模式')
        planModeConfig.value = null
      } else if (newStageMode && newStageMode !== '') {
        // 切换到计划模式，加载计划配置
        logger.debug(`开始加载计划配置: ${newStageMode}`)
        try {
          const response = await getPlans(newStageMode)

          if (response && response.code === 200 && response.data[newStageMode]) {
            const planData = response.data[newStageMode]
            logger.debug(`获取到计划数据: ${JSON.stringify(planData)}`)

            const currentConfig = getPlanCurrentConfig(planData)
            logger.debug(`getPlanCurrentConfig返回: ${JSON.stringify(currentConfig)}`)

            planModeConfig.value = currentConfig
            logger.debug('planModeConfig.value已更新')

            // 新增：保存完整的计划数据用于悬浮提示
            fullPlanData.value = planData
            logger.debug('fullPlanData.value已更新')

            logger.info(
              `计划配置加载成功:${JSON.stringify({
                planId: newStageMode,
                currentConfig: JSON.parse(JSON.stringify(currentConfig)),
                planModeConfigValue: JSON.parse(JSON.stringify(planModeConfig.value)),
              })}`
            )

            // 从stageModeOptions中查找对应的计划名称
            const planOption = stageModeOptions.value.find(option => option.value === newStageMode)
            const planName = planOption ? planOption.label : newStageMode

            message.success(`已切换到计划模式：${planName}`)
          } else {
            logger.warn(`计划配置响应不完整: ${JSON.stringify({ response, newStageMode })}`)
            message.warning(t('edit.couldNotLoadPlan'))
            planModeConfig.value = null
          }
        } catch (error) {
          // 只记录可序列化的错误信息，避免 "An object could not be cloned" 错误
          const errorInfo = {
            message: error instanceof Error ? error.message : String(error),
            stack: error instanceof Error ? error.stack : undefined,
            type: typeof error,
            name: error instanceof Error ? error.name : error?.constructor?.name,
          }
          logger.error(`加载计划配置失败: ${JSON.stringify(errorInfo)}`)
          message.error(t('edit.somethingWentWrongLoading'))
          planModeConfig.value = null
        }
      }
    },
    { immediate: false }
  )
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

.config-form {
  max-width: none;
}

.float-button {
  width: 60px;
  height: 60px;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .user-edit-container {
    padding: 16px;
  }

  .user-edit-content {
    max-width: 100%;
  }
}

/* MAA 配置遮罩样式（与 Scripts.vue 一致，用于全局覆盖） */
.maa-config-mask {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
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
  box-shadow:
    0 6px 16px 0 rgba(0, 0, 0, 0.08),
    0 3px 6px -4px rgba(0, 0, 0, 0.12),
    0 9px 28px 8px rgba(0, 0, 0, 0.05);
  border: 1px solid var(--ant-color-border);
}

.mask-icon {
  margin-bottom: 16px;
}

.mask-title {
  font-size: 18px;
  font-weight: 600;
  margin: 0 0 8px;
  color: var(--ant-color-text);
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
</style>
