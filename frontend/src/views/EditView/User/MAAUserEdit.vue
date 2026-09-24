<template>
  <div class="user-edit-container">
    <!-- 原生 GUI 会话遮罩（配置会话 / 查看会话，公用组件对齐 ok-ww / ok-nte） -->
    <GuiSessionMask
      :open="showMaaConfigMask"
      :icon="SettingOutlined"
      :title="t('edit.maaConfigurationProgress')"
      :description="`${t('edit.maaConfigurationThisUser')}\n${t('edit.clickSaveSettingsWhen')}`"
    >
      <template #actions>
        <a-button v-if="maaTaskId" type="primary" size="large" @click="handleSaveMAAConfig">
          {{ t('edit.saveConfiguration') }}
        </a-button>
      </template>
    </GuiSessionMask>
    <GuiSessionMask
      :open="showMaaViewMask"
      :icon="EyeOutlined"
      :title="t('edit.maaViewingTitle')"
      :description="`${t('edit.maaViewingDesc')}\n${t('edit.maaViewingDesc2')}`"
    >
      <template #actions>
        <a-button
          v-if="maaTaskId"
          type="primary"
          size="large"
          :loading="stoppingMaaConfig"
          @click="handleCloseMaaView"
        >
          {{ t('edit.maaViewClose') }}
        </a-button>
      </template>
    </GuiSessionMask>
    <!-- 头部组件 -->
    <MAAUserEditHeader
      :script-id="scriptId"
      :script-name="scriptName"
      :is-edit="isEdit"
      :user-mode="formData.Info.Mode"
      :maa-config-loading="maaConfigLoading"
      :show-maa-config-mask="showMaaConfigMask"
      :loading="loading"
      :config-locked="configLocked"
      @handle-m-a-a-config="handleMAAConfig"
      @handle-cancel="handleCancel"
    />

    <ConfigLockPanel :script-id="scriptId" content-class="user-edit-content">
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
            @mode-change="handleConfigModeChange"
          />

          <a-flex
            class="section-header"
            justify="space-between"
            align="center"
            wrap="wrap"
            gap="small"
          >
            <h3>{{ t('edit.taskConfiguration') }}</h3>
            <a-space>
              <span>{{ t('edit.enableQuickConfiguration') }}</span>
              <a-switch
                :checked="formData.Info.IfQuickConfig"
                :disabled="loading || isInitializing || isSaving"
                :aria-label="t('edit.enableQuickConfiguration')"
                @change="handleQuickConfigChange"
              />
              <a-button size="small" @click="openRestoreModal">
                <template #icon><HistoryOutlined /></template>
                {{ t('edit.configRestoreTitle') }}
              </a-button>
            </a-space>
          </a-flex>
          <TaskPipelineSection
            v-if="formData.Info.IfQuickConfig"
            v-model:form-data="formData"
            :loading="loading"
            :stage-options="stageOptions"
            :activity-stage-options="activityStageOptions"
            :activity-stage-loading="activityStageLoading"
            :activity-stage-error="activityStageError"
            :display-activity-stage-intent="displayActivityStageIntent"
            :activity-stage-state="activityStageState"
            :activity-period="activityPeriod"
            :depot-item-options="depotItemOptions"
            :depot-item-options-loading="depotItemOptionsLoading"
            :depot-item-options-error="depotItemOptionsError"
            :depot-stage-candidates="depotStageCandidates"
            :depot-stage-candidates-loading="depotStageCandidatesLoading"
            :depot-inventory="depotInventory"
            :depot-inventory-time="depotInventoryTime"
            :skland-role-options="sklandRoleOptions"
            :load-skland-role-options="loadSklandRoleOptions"
            :skland-role-loading="sklandRoleLoading"
            :skland-role-error="sklandRoleError"
            :load-depot-stage-candidates="loadDepotStageCandidates"
            :cultivate-operator-catalog="cultivateOperatorCatalog"
            :cultivate-operator-options-loading="cultivateOperatorOptionsLoading"
            :cultivate-operator-options-error="cultivateOperatorOptionsError"
            :cultivate-preview="cultivatePreview"
            :cultivate-preview-loading="cultivatePreviewLoading"
            :cultivate-preview-error="cultivatePreviewError"
            :load-cultivate-preview="loadCultivatePreview"
            :fight-summary="fightSummary"
            :is-edit="isEdit"
            :infrastructure-importing="infrastructureImporting"
            :infrastructure-options="infrastructureOptions"
            :infrastructure-options-loading="infrastructureOptionsLoading"
            :infrast-plan-select="infrastPlanSelect"
            :infrast-plan-state="infrastPlanState"
            @select-and-import-infrastructure-config="selectAndImportInfrastructureConfig"
            @select-infrast-plan="handleInfrastPlanSelectChange"
            @save="handleFieldSave"
          >
            <template #fight-detail>
              <StageConfigSection
                v-model:form-data="formData"
                :loading="loading"
                :stage-mode-options="stageModeOptions"
                :stage-options="stageOptions"
                :is-plan-mode="isPlanMode"
                :display-medicine-numb="displayMedicineNumb"
                :display-series-numb="displaySeriesNumb"
                :display-stage="displayStage"
                :display-stage1="displayStage1"
                :display-stage2="displayStage2"
                :display-stage3="displayStage3"
                :medicine-numb-tooltip="medicineNumbTooltip"
                :series-numb-tooltip="seriesNumbTooltip"
                :stage-tooltip="stageTooltip"
                :stage1-tooltip="stage1Tooltip"
                :stage2-tooltip="stage2Tooltip"
                :stage3-tooltip="stage3Tooltip"
                @update-medicine-numb="updateMedicineNumb"
                @update-series-numb="updateSeriesNumb"
                @update-stage="updateStage"
                @update-stage1="updateStage1"
                @update-stage2="updateStage2"
                @update-stage3="updateStage3"
                @handle-add-custom-stage="addCustomStage"
                @handle-add-custom-stage1="addCustomStage1"
                @handle-add-custom-stage2="addCustomStage2"
                @handle-add-custom-stage3="addCustomStage3"
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
          <UserNotifyConfig
            v-model="formData.Notify"
            :loading="loading"
            :script-id="scriptId"
            :user-id="userId"
            show-six-star
            @save="handleFieldSave"
          />
        </a-form>
      </a-card>
    </ConfigLockPanel>

    <!-- ══ 配置恢复（通用组件：MAS 用户配置在前、MAA 原生配置在后）══ -->
    <ConfigRestoreSection
      v-model:open="restoreOpen"
      :disabled="configLocked"
      :script-name="MAA_DISPLAY_NAME"
      :targets="restoreTargets"
      :api="restoreApi"
      :script-desc="t('edit.maaConfigRestoreScriptDesc')"
      :on-restored="handleRestored"
      :on-detail="handleRestoreView"
    >
      <!-- mas 备份为任务配置侧车、native 备份为 gui 文件摘要，共用文件集插槽 -->
      <template #preview="{ raw }">
        <a-empty
          v-if="!previewFiles(raw).length"
          :description="t('edit.configRestorePreviewEmpty')"
        />
        <div v-else>
          <template v-for="f in previewFiles(raw)" :key="f.name">
            <h4 class="maa-preview-title">{{ f.label }}</h4>
            <a-descriptions :column="1" size="small" bordered class="maa-preview-box">
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
import ConfigLockPanel from '@/components/ConfigLockPanel.vue'
import { useScriptConfigLock } from '@/composables/useScriptConfigLock'
import { useI18n } from 'vue-i18n'
import { computed, h, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import { EyeOutlined, HistoryOutlined, SettingOutlined } from '@ant-design/icons-vue'
import type { FormInstance, Rule } from 'ant-design-vue/es/form'
import { useUserApi } from '@/composables/useUserApi.ts'
import { useScriptApi } from '@/composables/useScriptApi.ts'
import { usePlanApi } from '@/composables/usePlanApi.ts'
import { useMaaGuiSession } from '@/composables/useMaaGuiSession'
import { Service } from '@/api'
import type { CultivatePreviewOut } from '@/api'
import { PlanComboxIn } from '@/api/models/PlanComboxIn.ts'
import { getWeekdayInTimezone } from '@/utils/dateUtils.ts'
import type { HomeOverviewResponse } from '@/types/home.ts'

const logger = window.electronAPI.getLogger('MAA用户编辑')

// 导入拆分的组件
import MAAUserEditHeader from '@/views/MAAUserEdit/MAAUserEditHeader.vue'
import BasicInfoSection from '@/views/MAAUserEdit/BasicInfoSection.vue'
import StageConfigSection from '@/views/MAAUserEdit/StageConfigSection.vue'
import TaskPipelineSection from '@/views/MAAUserEdit/TaskPipelineSection.vue'
import { summarizeFight } from '@/views/MAAUserEdit/taskSummaries'
import { resolveActivityStageState } from '@/views/MAAUserEdit/activityStageState'
import { isJadeStage, stageNumber } from '@/utils/activityStage'

import type { CultivateOperatorCatalogEntry } from '@/views/MAAUserEdit/cultivateTargets'
import UserNotifyConfig from '@/components/UserNotifyConfig.vue'
import ExtraScriptSection from '@/components/ExtraScriptSection.vue'
import GuiSessionMask from '@/components/GuiSessionMask.vue'
import ConfigRestoreSection from '@/views/EditView/User/components/ConfigRestoreSection.vue'
import { buildRestoreConfirm } from '@/utils/configRestoreMode'

const { t } = useI18n()

const router = useRouter()
const route = useRoute()
const { addUser, updateUser, getUsers, loading: userLoading, error: userError } = useUserApi()
const { getScript } = useScriptApi()
const { getPlans } = usePlanApi()
const {
  maaConfigLoading,
  maaTaskId,
  showMaaConfigMask,
  showMaaViewMask,
  stoppingMaaConfig,
  startSession,
  saveSession,
  stopSession,
} = useMaaGuiSession()

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
const { configLocked } = useScriptConfigLock(() => scriptId)

// 脚本信息
const scriptName = ref('')

// 基建配置文件相关
const infrastructureImporting = ref(false)
const infrastructureOptions = ref<Array<{ label: string; value: string; period?: string | null }>>(
  []
)
const infrastPlanState = ref('empty')
const infrastPlanSelect = ref(-1)
const infrastructureOptionsLoading = ref(false)

// 库存保持物品选项
const depotItemOptions = ref<Array<{ label: string; value: string }>>([])
const depotItemOptionsLoading = ref(false)
const depotItemOptionsError = ref('')

// 库存保持关卡候选（按物品缓存，含每理智效率）与仓库库存
const depotStageCandidates = ref<Record<string, Array<{ label: string; value: string }>>>({})
const depotStageCandidatesLoading = ref<string[]>([])
const depotInventory = ref<Record<string, number>>({})
const depotInventoryTime = ref('')

// 干员养成选择器目录（一图流全量表，含技能/模组名称目录与可达档位，随快照缓存）
const cultivateOperatorCatalog = ref<CultivateOperatorCatalogEntry[]>([])

// 森空岛绑定下拉：合并所有已配置凭据账号组的角色（下拉展开时按需加载）
const sklandRoleOptions = ref<Array<{ label: string; value: string }>>([])
const sklandRoleLoading = ref(false)
const sklandRoleError = ref('')
const cultivateOperatorOptionsLoading = ref(false)
const cultivateOperatorOptionsError = ref('')

// 干员目录（一图流全量表，含技能/模组名称目录与可达档位，随快照缓存；
// 序列号守卫防绑定变更连发两次加载时的乱序覆盖）
let cultivateOperatorCatalogSeq = 0

// 养成需求预览（纯计算不落库；序列号守卫防快速编辑时的乱序覆盖）
const cultivatePreview = ref<CultivatePreviewOut | null>(null)
const cultivatePreviewLoading = ref(false)
const cultivatePreviewError = ref('')
let cultivatePreviewSeq = 0

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
const stageOptions = ref<any[]>([{ label: t('edit.none'), value: '' }])
const activityStageOptions = ref<Array<{ label: string; value: string }>>([])
/** 当前活动关数据的期间态（进行中/下期预览/间隙期），驱动状态行 */
const activityPeriod = ref<'ongoing' | 'preview' | 'gap'>('gap')
const activityStageLoading = ref(false)
const activityStageError = ref('')
const stageOverviewByServer = ref<HomeOverviewResponse['StageByServer']>({})

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
const stageModeOptions = ref<any[]>([{ label: t('edit.fixed'), value: 'Fixed' }])

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
        tooltip += `${weekdaysZh[index]}: ${value}\n`
      }
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
    Mode: '脚本',
    IfQuickConfig: true,
    InfrastMode: 'Normal',
    InfrastName: '',
    Annihilation: 'Annihilation',
    Stage: '1-7',
    StageMode: 'Fixed',
    Stage_1: '',
    Stage_2: '',
    Stage_3: '',
  },
  Task: {
    IfStartUp: true,
    IfInfrast: true,
    IfFight: true,
    IfMall: true,
    IfAward: true,
    IfSwitchTheme: false,
    IfRecruit: true,
    IfDepotMaintain: false,
    DepotMaintainPlans: '[]',
    IfCultivate: false,
    IfGreenTicketStore: false,
    IfActivityFirst: false,
    ActivityStageIntent: '',
    ActivityMedicineNumb: 0,
    CultivateTargets: '[]',
    CultivateSkipDuringActivity: false,
    CultivateSkipDuringResourceCollection: false,
    CultivateSklandAccount: '',
    CultivateSklandUid: '',
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
  },
  Data: {
    LastProxyDate: '',
    ProxyTimes: 0,
    CultivateNotice: '',
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

const displayActivityStageIntent = computed(() => {
  const configuredIntent = formData.Task.ActivityStageIntent
  // 未配置或本期选项对不上（如旧版遗留意图）时显示占位符，不假装已选
  return activityStageOptions.value.some(option => option.value === configuredIntent)
    ? configuredIntent
    : undefined
})

/** 该用户服务器视角的两期关卡（状态行取数用） */
const serverStageLists = computed(() => {
  const server = formData.Info.Server === 'Bilibili' ? 'Official' : formData.Info.Server
  const overview = stageOverviewByServer.value[server]
  return {
    activity: overview?.Activity ?? [],
    preview: overview?.Preview ?? [],
  }
})

/** 选关下方状态行（统一状态机，方案 §6） */
const activityStageState = computed(() =>
  resolveActivityStageState(
    formData.Task.ActivityStageIntent ?? '',
    serverStageLists.value.activity,
    serverStageLists.value.preview,
  ),
)

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
  })
)

// 表单验证规则
const rules = computed(() => {
  const baseRules: Record<string, Rule[]> = {
    userName: [
      { required: true, message: t('edit.enterUsername'), trigger: 'blur' },
      { min: 1, max: 50, message: t('edit.usernameMustBe1'), trigger: 'blur' },
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

// 快速配置开关：与配置来源独立，真实保存
const handleQuickConfigChange = async (value: boolean) => {
  const previous = formData.Info.IfQuickConfig
  formData.Info.IfQuickConfig = value
  if (!(await handleFieldSave('Info.IfQuickConfig', value))) {
    formData.Info.IfQuickConfig = previous
  }
}

// 配置来源切换：校验 value ∈ options → 赋值 Info.Mode → 保存
const handleConfigModeChange = async (value: boolean | string) => {
  if (typeof value !== 'string' || !['脚本', '用户', '直控'].includes(value)) return
  formData.Info.Mode = value as '脚本' | '用户' | '直控'
  await handleFieldSave('Info.Mode', formData.Info.Mode)
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
  if (configLocked.value) return false

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

        // 干员目录按用户档案过滤已精 2（PR2 仅精英化），须在 userId 就绪后加载。
        // 必须在放开 isInitializing 之后：目录走 jsdelivr 兜底拉取时最长 30s，
        // 期间用户在页面上的改动会被 handleFieldSave 静默丢弃（组件自带 loading）。
        // 库存列读当前用户识别档案（决策 31）；两者无依赖，并行加载避免目录
        // 慢时库存列被串行阻塞
        await Promise.all([loadCultivateOperatorOptions(), loadDepotInventory()])
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
  const stageFields = ['Stage', 'Stage_1', 'Stage_2', 'Stage_3']
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
  // 进行中优先，间隙期用下期预览（选项不消失，可提前布阵；预览不注入）
  const source =
    stageOverview.Activity.length > 0 ? stageOverview.Activity : stageOverview.Preview
  activityPeriod.value =
    stageOverview.Activity.length > 0
      ? 'ongoing'
      : stageOverview.Preview.length > 0
        ? 'preview'
        : 'gap'
  // 意图值与后端解析同锚：非玉关按关卡号降序编为 last:N，含玉关固定 jade
  const lastRankByStage = new Map<string, number>()
  source
    .filter(stage => !isJadeStage(stage))
    .sort((a, b) => stageNumber(b.Value) - stageNumber(a.Value))
    .forEach((stage, index) => lastRankByStage.set(stage.Value, index + 1))
  activityStageOptions.value = source.map(stage => {
    const label = `${stage.Activity.StageName} · ${stage.Display} · ${stage.DropName}`
    const rank = lastRankByStage.get(stage.Value)
    return rank
      ? { label: `倒${rank}. ${label}`, value: `last:${rank}` }
      : { label: `搓玉 · ${label}`, value: 'jade' }
  })
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

    const overview = response.data as Partial<HomeOverviewResponse> | undefined
    if (!overview?.StageByServer) {
      // 不能直接赋值: 字段缺席会把 stageOverviewByServer 的 {} 默认值抹成 undefined,
      // 之后服务器切换的 watcher 一跑 applyServerStageOptions 就会整页崩
      logger.error('活动关卡数据缺少 StageByServer 字段，后端版本可能与前端不匹配')
      activityStageError.value = '加载活动关卡失败：返回数据缺少关卡信息'
      return
    }

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

const loadDepotStageCandidates = async (itemId: string) => {
  if (!itemId || depotStageCandidates.value[itemId]) return
  if (depotStageCandidatesLoading.value.includes(itemId)) return
  depotStageCandidatesLoading.value.push(itemId)
  try {
    const response = await Service.getMaaDepotStageCandidatesApiScriptsMaaDepotStageCandidatesPost({
      script: { scriptId },
      itemId,
    })
    // 失败/无候选时写入空数组作为"已完成"标记：编辑器据此回退全量关卡表
    // （undefined 才表示加载中），同时避免失败后无限重试
    depotStageCandidates.value[itemId] =
      response.code === 200
        ? response.data
            .filter(option => option.value)
            .map(option => ({ label: option.label, value: option.value as string }))
        : []
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载库存保持关卡候选失败: ${errorMsg}`)
    depotStageCandidates.value[itemId] = []
  } finally {
    depotStageCandidatesLoading.value = depotStageCandidatesLoading.value.filter(
      id => id !== itemId
    )
  }
}

const loadDepotInventory = async () => {
  try {
    const response = await Service.getMaaDepotInventoryApiScriptsMaaDepotInventoryPost({
      script: { scriptId },
      userId,
    })
    if (response.code !== 200) return
    const inventory: Record<string, number> = {}
    for (const option of response.data) {
      if (option.value) inventory[option.value] = Number(option.label) || 0
    }
    depotInventory.value = inventory
    depotInventoryTime.value = (response.recognizedAt || '').replace('T', ' ')
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载 MAA 仓库库存失败: ${errorMsg}`)
  }
}

const loadCultivateOperatorOptions = async () => {
  // 绑定变更的两字段保存分属两个 await 周期，watch 会以半绑定/完整状态各
  // 触发一次加载；seq 守卫丢弃乱序返回的过期响应（与预览加载同款）
  const seq = ++cultivateOperatorCatalogSeq
  cultivateOperatorOptionsLoading.value = true
  cultivateOperatorOptionsError.value = ''
  try {
    const response = await Service.getMaaCultivateOperatorsApiScriptsMaaCultivateOperatorsPost({
      script: { scriptId },
      userId,
    })
    if (seq !== cultivateOperatorCatalogSeq) return
    if (response.code !== 200) {
      cultivateOperatorOptionsError.value = response.message || '加载干员目录失败'
      return
    }
    cultivateOperatorCatalog.value = (response.data ?? [])
      .filter(option => option.value)
      .map(option => ({
        value: option.value,
        label: option.label,
        rarity: option.rarity ?? 0,
        profession: option.profession ?? '',
        maxElite: option.maxElite ?? 2,
        dataMissing: option.dataMissing ?? false,
        skills: (option.skills ?? []).map(item => ({
          label: item.label,
          value: item.value as string,
          maxLevel: item.maxLevel ?? 0,
        })),
        modules: (option.modules ?? []).map(item => ({
          label: item.label,
          value: item.value as string,
          maxLevel: item.maxLevel ?? 0,
        })),
      }))
  } catch (error) {
    if (seq !== cultivateOperatorCatalogSeq) return
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载干员目录失败: ${errorMsg}`)
    cultivateOperatorOptionsError.value = '加载干员目录失败'
  } finally {
    if (seq === cultivateOperatorCatalogSeq) cultivateOperatorOptionsLoading.value = false
  }
}

const loadSklandRoleOptions = async () => {
  // 该端点要遍历所有已配置森空岛凭据的账号组做凭据刷新+角色拉取，代价高；
  // 每次展开任务行都会重新挂载编辑器并触发回显请求，故已加载过就直接复用
  // （要刷新列表：离开编辑页重进，或下拉为空时由展开下拉触发）
  if (sklandRoleOptions.value.length) return
  sklandRoleLoading.value = true
  sklandRoleError.value = ''
  try {
    const response =
      await Service.getMaaCultivateSklandBindingsApiScriptsMaaCultivateSklandBindingsPost()
    if (response.code !== 200) {
      sklandRoleError.value = response.message || '加载绑定角色失败'
      sklandRoleOptions.value = []
      return
    }
    sklandRoleOptions.value = response.data.map(option => ({
      label: option.label,
      value: option.value as string,
    }))
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载森空岛绑定角色失败: ${errorMsg}`)
    sklandRoleError.value = '加载绑定角色失败'
    sklandRoleOptions.value = []
  } finally {
    sklandRoleLoading.value = false
  }
}

// 绑定变化（绑定↔解绑、或换绑到另一角色）后：选择器目录需按森空岛快照
// 重新过滤（精 2 干员绑定后恢复可见，解除绑定回到剔精 2 口径），预览也要
// 按新练度重算——故比较账号|角色的复合值而不只是绑定与否
watch(
  () => `${formData.Task?.CultivateSklandAccount ?? ''}|${formData.Task?.CultivateSklandUid ?? ''}`,
  (next, prev) => {
    if (isInitializing.value || !userId || next === prev) return
    loadCultivateOperatorOptions()
    if (formData.Task?.CultivateTargets) {
      loadCultivatePreview(formData.Task.CultivateTargets)
    }
  }
)

const loadCultivatePreview = async (targetsJson: string) => {
  const seq = ++cultivatePreviewSeq
  cultivatePreviewLoading.value = true
  cultivatePreviewError.value = ''
  try {
    const response = await Service.getMaaCultivatePreviewApiScriptsMaaCultivatePreviewPost({
      scriptId,
      userId,
      targets: targetsJson,
    })
    if (seq !== cultivatePreviewSeq) return
    if (response.code !== 200) {
      cultivatePreviewError.value = response.message || '需求计算失败'
      return
    }
    cultivatePreview.value = response
  } catch (error) {
    if (seq !== cultivatePreviewSeq) return
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`养成需求计算失败: ${errorMsg}`)
    cultivatePreviewError.value = '需求计算失败'
  } finally {
    if (seq === cultivatePreviewSeq) cultivatePreviewLoading.value = false
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

// 手动选班 = 把轮换起点拨到该班（无时段表存 MAS 用户字段、由 MAS 推进；时段表只有自动）
const handleInfrastPlanSelectChange = async (index: number, label: string) => {
  if (configLocked.value) return
  try {
    const result = await Service.setInfrastPlanSelectApiScriptsUserInfrastructurePlanSelectPost({
      scriptId: scriptId,
      userId: userId,
      index: index,
    })
    if (!result || result.code !== 200) {
      message.error(t('edit.maaCustomInfrastPlanSelectFailed'))
      return
    }
    // 后端会把「自动」归一成第一班, 以返回值为准, 免得刷新前后显示不一致
    infrastPlanSelect.value = result.index ?? index
    message.success(t('edit.maaCustomInfrastPlanSelected', { name: label }))
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`设置基建班次失败: ${errorMsg}`)
    message.error(t('edit.maaCustomInfrastPlanSelectFailed'))
  }
}

// 选择并导入基建配置文件
const selectAndImportInfrastructureConfig = async () => {
  if (!isEdit.value) {
    message.warning(t('edit.saveUserBeforeImporting'))
    return
  }
  if (configLocked.value) return

  try {
    // 选择文件
    const path = await window.electronAPI?.selectFile([
      { name: t('edit.jsonFiles'), extensions: ['json'] },
      { name: t('edit.allFiles'), extensions: ['*'] },
    ])

    if (path && path.length > 0) {
      if (configLocked.value) {
        message.error(t('edit.configLocked'))
        return
      }
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

        message.success(t('edit.baseConfigurationImported'))

        // 重新加载基建配置选项与当前班次
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
        period: item.period ?? null,
      }))
      infrastPlanState.value = result.state ?? 'empty'
    }

    const current = await Service.getInfrastPlanSelectApiScriptsUserInfrastructurePlanSelectGetPost(
      {
        scriptId: scriptId,
        userId: userId,
      }
    )
    if (current && current.code === 200) {
      infrastPlanSelect.value = current.index
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载基建配置选项失败: ${errorMsg}`)
  } finally {
    infrastructureOptionsLoading.value = false
  }
}

const handleMAAConfig = async () => {
  if (configLocked.value) return
  if (!userId) return
  await startSession(userId)
}

const handleSaveMAAConfig = () => {
  void saveSession()
}

const handleCloseMaaView = () => {
  void stopSession()
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

type StageField = 'Stage' | 'Stage_1' | 'Stage_2' | 'Stage_3'

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
    message.warning(t('edit.stageP0AlreadyExists', { p0: trimmedName }))
    return false
  }

  // 添加到选项列表
  stageOptions.value.push({
    label: trimmedName,
    value: trimmedName,
    isCustom: true,
  })

  message.success(t('edit.customStageP0Added', { p0: trimmedName }))
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

const handleCancel = async () => {
  const pendingSave = fieldSavePromise
  if (pendingSave && !(await pendingSave)) return

  await stopSession()
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

watch(
  () => formData.Info.Server,
  () => applyServerStageOptions()
)

// ══ 配置恢复（通用组件 props 供给：双目标 MAS 在前脚本在后）══
// 专项统一名（文案参数化用）：MAA 统一叫「maa」
const MAA_DISPLAY_NAME = 'maa'
const restoreOpen = ref(false)

// 目标池顺序 = segmented 展示顺序：MAS 用户配置（在前）、MAA 原生配置（在后）
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
interface MaaPreviewFileView {
  name: string
  label: string
  summary: Array<{ key: string; value: string }>
}
const previewFiles = (raw: unknown): MaaPreviewFileView[] =>
  (raw as { fileCards?: MaaPreviewFileView[] } | null)?.fileCards ?? []

// 一键恢复成功：mas 恢复含页面核心配置（Info/Task）回填，重拉表单——否则
// 旧表单值在下次保存时会静默覆盖回滚结果；native 恢复不影响本页表单
const handleRestored = async (target: string) => {
  restoreOpen.value = false
  if (target === 'mas') {
    await loadUserData()
  }
}

// 「查看详细配置」语义（对齐一条龙）：恢复该时点 + 拉起查看会话预览。
// 弹窗文案必须显式区分——该按钮极易被误以为只读，实际会真覆盖当前配置。
// mas 备份：恢复到 MAS 目录后启动查看会话（下发为查看的必经复制，GUI 所见
// 即备份）；原生备份：恢复到 MAA 本体后启动脚本级查看会话（跳过下发，
// 原生目录即备份）。查看会话结束不回写配置，原生现场由任务前快照还原。
// 与一键恢复同口径：单弹窗文案，跨配置来源时换标题并追加来源切换说明
// （确认后由基座把配置来源切回备份时点再恢复）。
const handleRestoreView = (
  target: string,
  item: { time: string; mode?: string | null },
  currentMode?: string | null
) => {
  if (configLocked.value) return Promise.resolve(false)

  return new Promise<boolean>(resolve => {
    const { title, paragraphs } = buildRestoreConfirm(
      t,
      {
        title: t('edit.configRestoreDetailView'),
        desc: t('edit.configRestoreDetailConfirm', { script: MAA_DISPLAY_NAME }),
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
        if (configLocked.value) {
          message.error(t('edit.configLocked'))
          resolve(false)
          return
        }

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
}

// 编辑会话归档（进入/退出时机，指纹去重）：与运行/会话下发前的双池归档
// （AutoProxy/ScriptConfig 的 set_maa）配合——进入归档原生配置当前状态
// （MAS 触碰前原始态），退出归档 MAS 配置终态（编辑会话包络）
const ensureMaaBackup = async (target: 'mas' | 'native') => {
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

// 初始化加载
onMounted(async () => {
  if (!scriptId) {
    message.error(t('edit.missingScriptIdParameter'))
    handleCancel()
    return
  }

  // 先等脚本信息加载（新建模式内部会创建用户并写入 userId），native 归档
  // 虽不需要用户但后端 ensure 端点要求 userId 参数——必须在 userId 就绪后
  // 才能发出，否则新建用户首次进入会静默跳过归档
  await loadScriptInfo()
  loadStageModeOptions()
  loadActivityStageOptions()
  loadDepotItemOptions()
  // 进入编辑页：归档 MAA 原生配置当前状态（MAS 触碰前的原始态）
  void ensureMaaBackup('native')

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

            const currentConfig = getPlanCurrentConfig(planData)

            planModeConfig.value = currentConfig
            logger.debug('planModeConfig.value已更新')

            // 新增：保存完整的计划数据用于悬浮提示
            fullPlanData.value = planData
            logger.debug('fullPlanData.value已更新')

            // 只记 planId 与字段数，整份计划序列化进日志既慢又没人看
            logger.info(
              `计划配置加载成功: ${newStageMode}, 字段数=${Object.keys(currentConfig ?? {}).length}`
            )

            // 从stageModeOptions中查找对应的计划名称
            const planOption = stageModeOptions.value.find(option => option.value === newStageMode)
            const planName = planOption ? planOption.label : newStageMode

            message.success(t('edit.switchedPlanModeP0', { p0: planName }))
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

onUnmounted(() => {
  // 退出编辑页：先停会话再归档 MAS 侧终态——并行会与 final_task 的
  // rmtree/copytree 回写撞车，归档到半程状态；会话未开时 stopSession
  // 立即返回，不影响归档时机
  void (async () => {
    await stopSession()
    await ensureMaaBackup('mas')
  })()
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

/* 配置预览：逐文件的摘要标题与摘要表 */
.maa-preview-title {
  margin: 14px 0 6px;
  font-size: 14px;
  font-weight: 600;
}

.maa-preview-title:first-child {
  margin-top: 0;
}

.maa-preview-box {
  margin-bottom: 4px;
}
</style>
