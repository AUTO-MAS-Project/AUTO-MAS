<template>
  <div ref="pageRef" class="user-edit-container">
    <!-- 原生 GUI 会话遮罩（配置会话 / 查看会话，公用组件对齐 ok-ww / ok-nte） -->
    <GuiSessionMask
      :open="showMaaConfigMask"
      :icon="SettingOutlined"
      :title="t('core.edit.maaConfigurationProgress')"
      :description="`${t('core.edit.maaConfigurationThisUser')}\n${t('core.edit.clickSaveSettingsWhen')}`"
    >
      <template #actions>
        <a-button v-if="maaTaskId" type="primary" size="large" @click="handleSaveMAAConfig">
          {{ t('core.edit.saveConfiguration') }}
        </a-button>
      </template>
    </GuiSessionMask>
    <GuiSessionMask
      :open="showMaaViewMask"
      :icon="EyeOutlined"
      :title="t('core.edit.maaViewingTitle')"
      :description="`${t('core.edit.maaViewingDesc')}\n${t('core.edit.maaViewingDesc2')}`"
    >
      <template #actions>
        <a-button
          v-if="maaTaskId"
          type="primary"
          size="large"
          :loading="stoppingMaaConfig"
          @click="handleCloseMaaView"
        >
          {{ t('core.edit.maaViewClose') }}
        </a-button>
      </template>
    </GuiSessionMask>
    <UserEditHeader
      v-if="!cultivationPage"
      :script-id="scriptId"
      :script-name="scriptName"
      :is-edit="isEdit"
      script-edit-segment="maa"
      :user-id="userId"
      :cancel-loading="leavingPage"
      @cancel="handleCancel"
    />

    <!-- 干员养成独立页面：页面壳自带页头/总览/标签页 -->
    <CultivationPage
      v-if="cultivationPage && !isInitializing"
      :script-id="scriptId"
      :user-id="userId"
      :script-name="scriptName"
      :form-data="formData"
      :loading="loading"
      :leaving-page="leavingPage"
      :editor-busy="editorBusy"
      :operator-catalog="cultivateOperatorCatalog"
      :operator-options-loading="cultivateOperatorOptionsLoading"
      :operator-options-error="cultivateOperatorOptionsError"
      :skland-role-options="sklandRoleOptions"
      :skland-role-loading="sklandRoleLoading"
      :skland-role-error="sklandRoleError"
      :load-skland-role-options="loadSklandRoleOptions"
      :item-options="depotItemOptions"
      :cultivate-preview="cultivatePreview"
      :cultivate-preview-loading="cultivatePreviewLoading"
      :cultivate-preview-error="cultivatePreviewError"
      :load-cultivate-preview="loadCultivatePreview"
      :import-cultivate-targets="importCultivateTargets"
      :prepare-copilot-analysis="prepareCopilotAnalysis"
      @save="handleFieldSave"
      @back="handleCancel"
    />
    <div v-else-if="cultivationPage" class="cultivation-page-loading"><a-spin /></div>
    <ConfigLockPanel v-else :script-id="scriptId" content-class="user-edit-content">
      <a-card class="config-card" :inert="editorBusy">
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

          <!-- 配置文件来源：base 三态 ⊕ overlay 两态，与 MaaEnd / Okww 共用同一套面板 -->
          <a-flex class="section-header" align="center" wrap="wrap" gap="small">
            <h3>{{ t('core.edit.configurationSource') }}</h3>
          </a-flex>
          <GeneralConfigModeSelector
            :model-value="formData.Info.Base"
            :options="maaConfigModeOptions"
            :disabled="loading"
            :quick-config="formData.Info.IfQuickConfig"
            :quick-config-disabled="loading || isInitializing"
            :alert-message="t('core.edit.configSourceHintBase')"
            :show-gui-hint="false"
            @change="handleConfigModeChange"
            @quick-config-change="handleQuickConfigChange"
          />
          <!-- MAA 不提供配置导入 -->
          <ConfigActionsSection
            :base="formData.Info.Base"
            script-label="MAA"
            :disabled="loading || showMaaConfigMask || configLocked"
            :config-loading="preparingSession || maaConfigLoading"
            :configuring="showMaaConfigMask"
            :show-import="false"
            @configure="handleMAAConfig"
            @script-config="handleScriptConfig"
          />

          <a-flex
            class="section-header"
            justify="space-between"
            align="center"
            wrap="wrap"
            gap="small"
          >
            <h3>{{ t('core.edit.taskConfiguration') }}</h3>
            <a-space>
              <a-button size="small" @click="openRestoreModal">
                <template #icon><HistoryOutlined /></template>
                {{ t('core.edit.configRestoreTitle') }}
              </a-button>
            </a-space>
          </a-flex>
          <TaskPipelineSection
            v-if="formData.Info.IfQuickConfig"
            v-model:form-data="formData"
            :loading="loading"
            :stage-options="stageOptions"
            :activity-stages="activityStages"
            :activity-template="activityTemplate"
            :activity-stage-loading="activityStageLoading"
            :activity-stage-error="activityStageError"
            :depot-item-options="depotItemOptions"
            :depot-item-options-loading="depotItemOptionsLoading"
            :depot-item-options-error="depotItemOptionsError"
            :depot-stage-candidates="depotStageCandidates"
            :depot-stage-candidates-loading="depotStageCandidatesLoading"
            :depot-inventory="depotInventory"
            :depot-inventory-time="depotInventoryTime"
            :depot-plan-editor="depotPlanEditor"
            :event-depot-plan-editor="eventDepotPlanEditor"
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
            @retry-activity="loadActivityStageOptions(true)"
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
      :disabled="configLocked || editorBusy"
      :script-name="MAA_DISPLAY_NAME"
      :targets="restoreTargets"
      :api="restoreApi"
      :script-desc="t('core.edit.maaConfigRestoreScriptDesc')"
      :on-detail="handleRestoreView"
    >
      <!-- mas 备份为任务配置侧车、native 备份为 gui 文件摘要，共用文件集插槽 -->
      <template #preview="{ raw }">
        <NoData
          v-if="!previewFiles(raw).length"
          :description="t('core.edit.configRestorePreviewEmpty')"
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
import UserEditHeader from '@/components/UserEditHeader.vue'
import CultivationPage from '@/views/MAAUserEdit/CultivationPage.vue'
import { useScriptConfigLock } from '@/composables/useScriptConfigLock'
import { useI18n } from 'vue-i18n'
import { computed, h, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import { EyeOutlined, HistoryOutlined, SettingOutlined } from '@ant-design/icons-vue'
import type { FormInstance, Rule } from 'ant-design-vue/es/form'
import { useUserApi } from '@/composables/useUserApi.ts'
import { useScriptApi } from '@/composables/useScriptApi.ts'
import { usePlanApi } from '@/composables/usePlanApi.ts'
import { useMaaGuiSession } from '@/composables/useMaaGuiSession'
import { useMaaDepotStageCandidates } from '@/composables/useMaaDepotStageCandidates'
import { AdapterSetupService as Service } from '@/composables/useAdapterSetupApi'
import type { CultivatePreviewOut } from '@/api'
import { PlanComboxIn } from '@/api/models/PlanComboxIn.ts'
import { getWeekdayInTimezone } from '@/utils/dateUtils.ts'
import { useMaaStageOptions } from '@/views/MAAUserEdit/useMaaStageOptions'

const logger = window.electronAPI.getLogger('MAA用户编辑')

// 导入拆分的组件
import BasicInfoSection from '@/views/MAAUserEdit/BasicInfoSection.vue'
import GeneralConfigModeSelector from '@/views/EditView/User/GeneralConfigModeSelector.vue'
import ConfigActionsSection from '@/views/EditView/User/ConfigActionsSection.vue'
import StageConfigSection from '@/views/MAAUserEdit/StageConfigSection.vue'
import TaskPipelineSection from '@/views/MAAUserEdit/TaskPipelineSection.vue'
import { summarizeFight } from '@/views/MAAUserEdit/taskSummaries'
import { getDefaultMAAUserData } from '@/views/MAAUserEdit/userDefaults'
import { useDepotMaintainPlanEditor } from '@/views/MAAUserEdit/useDepotMaintainPlanEditor'
import { useMAAFieldSave } from '@/views/MAAUserEdit/useMAAFieldSave'
import { useMAAEditorLifecycle } from '@/views/MAAUserEdit/useMAAEditorLifecycle'
import { getGameDayOffset } from '@/views/MAAUserEdit/periodMarkers'
import { useMaaCultivation } from '@/views/MAAUserEdit/useMaaCultivation'
import UserNotifyConfig from '@/components/UserNotifyConfig.vue'
import ExtraScriptSection from '@/components/ExtraScriptSection.vue'
import GuiSessionMask from '@/components/GuiSessionMask.vue'
import ConfigRestoreSection from '@/views/EditView/User/components/ConfigRestoreSection.vue'
import { buildRestoreConfirm } from '@/utils/configRestoreMode'
import { useConfigBackupApi } from '@/composables/useConfigBackupApi'

const { t } = useI18n()
const { cultivationPage = false } = defineProps<{ cultivationPage?: boolean }>()

const router = useRouter()
const route = useRoute()
const { addUser, updateUser, getUsers, loading: userLoading, error: userError } = useUserApi()
const { getScript, error: scriptApiError } = useScriptApi()
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
const pageRef = ref<HTMLElement>()
const isInitializing = ref(true)
// 字段请求不禁用整棵编辑树，后续输入由保存队列保留；独占操作才锁定编辑。
const loading = computed(
  () => editorBusy.value || isInitializing.value || (userLoading.value && !isSaving.value)
)

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
const {
  candidates: depotStageCandidates,
  loading: depotStageCandidatesLoading,
  load: loadDepotStageCandidateBatch,
  cancelPending: cancelDepotStageCandidates,
} = useMaaDepotStageCandidates(scriptId)
const depotInventory = ref<Record<string, number>>({})
const depotInventoryTime = ref('')

// 服务器选项
const serverOptions = [
  { label: '官服', value: 'Official' },
  { label: 'B服', value: 'Bilibili' },
  { label: '国际服（YoStarEN）', value: 'YoStarEN' },
  { label: '日服（YoStarJP）', value: 'YoStarJP' },
  { label: '韩服（YoStarKR）', value: 'YoStarKR' },
  { label: '繁中服（txwy）', value: 'txwy' },
]

const {
  stageOptions,
  activityStages,
  activityTemplate,
  activityStageLoading,
  activityStageError,
  appendConfiguredCustomStages,
  applyServerStageOptions,
  loadActivityStageOptions,
} = useMaaStageOptions(() => formData)

// 关卡配置模式选项
const stageModeOptions = ref<any[]>([{ label: t('core.edit.fixed'), value: 'Fixed' }])

// 计划模式状态
const isPlanMode = computed(() => {
  return formData.Stage.StageMode !== 'Fixed'
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
    return formData.Stage.MedicineNumb
  },
  set: value => {
    if (!isPlanMode.value) {
      formData.Stage.MedicineNumb = value
    }
  },
})

const displaySeriesNumb = computed({
  get: () => {
    if (isPlanMode.value && planModeConfig.value?.SeriesNumb !== undefined) {
      return planModeConfig.value.SeriesNumb
    }
    return formData.Stage.SeriesNumb
  },
  set: value => {
    if (!isPlanMode.value) {
      formData.Stage.SeriesNumb = value
    }
  },
})

const displayStage = computed({
  get: () => {
    if (isPlanMode.value && planModeConfig.value?.Stage !== undefined) {
      return planModeConfig.value.Stage
    }
    return formData.Stage.Stage
  },
  set: value => {
    if (!isPlanMode.value) {
      formData.Stage.Stage = value
    }
  },
})

const displayStage1 = computed({
  get: () => {
    if (isPlanMode.value && planModeConfig.value?.Stage_1 !== undefined) {
      return planModeConfig.value.Stage_1
    }
    return formData.Stage.Stage_1
  },
  set: value => {
    if (!isPlanMode.value) {
      formData.Stage.Stage_1 = value
    }
  },
})

const displayStage2 = computed({
  get: () => {
    if (isPlanMode.value && planModeConfig.value?.Stage_2 !== undefined) {
      return planModeConfig.value.Stage_2
    }
    return formData.Stage.Stage_2
  },
  set: value => {
    if (!isPlanMode.value) {
      formData.Stage.Stage_2 = value
    }
  },
})

const displayStage3 = computed({
  get: () => {
    if (isPlanMode.value && planModeConfig.value?.Stage_3 !== undefined) {
      return planModeConfig.value.Stage_3
    }
    return formData.Stage.Stage_3
  },
  set: value => {
    if (!isPlanMode.value) {
      formData.Stage.Stage_3 = value
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
    // 按用户区服的游戏日时区取今天是星期几（已经是数字0-6），与后端计划表取值一致
    const todayWeekday = getWeekdayInTimezone(getGameDayOffset(formData.Info.Server))

    const weekdays = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    const today = weekdays[todayWeekday]

    logger.debug(`计划表周模式调试: 
      游戏日星期几: ${todayWeekday},
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

// 创建扁平化的表单数据，用于表单验证
const formData = reactive({
  // 扁平化的验证字段
  userName: '',
  userId: '',
  // 嵌套的实际数据
  ...getDefaultMAAUserData(),
})

// 折叠态摘要：不展开也能确认当前生效的关卡配置
const fightSummary = computed(() =>
  summarizeFight({
    enabled: formData.Task.IfFight,
    planLabel: isPlanMode.value
      ? stageModeOptions.value.find(option => option.value === formData.Stage.StageMode)?.label ||
        formData.Stage.StageMode
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
      { required: true, message: t('core.edit.enterUsername'), trigger: 'blur' },
      { min: 1, max: 50, message: t('core.edit.usernameMustBe1'), trigger: 'blur' },
    ],
  }
  return baseRules
})

// 同步扁平化验证字段与嵌套数据，避免同一轮更新中的旧值覆盖新草稿。
watch(
  () => formData.Info.Name,
  newVal => {
    if (formData.userName !== newVal) {
      formData.userName = newVal || ''
    }
  },
  { immediate: true, flush: 'sync' }
)

watch(
  () => formData.Info.Id,
  newVal => {
    if (formData.userId !== newVal) {
      formData.userId = newVal || ''
    }
  },
  { immediate: true, flush: 'sync' }
)

// 基建配置名称和索引保持独立，不自动同步

watch(
  () => formData.userName,
  newVal => {
    if (formData.Info.Name !== newVal) {
      formData.Info.Name = newVal || ''
    }
  },
  { flush: 'sync' }
)

watch(
  () => formData.userId,
  newVal => {
    if (formData.Info.Id !== newVal) {
      formData.Info.Id = newVal || ''
    }
  },
  { flush: 'sync' }
)

const fieldSave = useMAAFieldSave({
  formData,
  defaults: getDefaultMAAUserData,
  canSave: () => !isInitializing.value && !!userId,
  save: patch => updateUser(scriptId, userId, patch),
  readSaved: async () => {
    const response = await getUsers(scriptId, userId)
    return response?.code === 200 ? (response.data[userId] ?? null) : null
  },
  hasDraft: key =>
    (key === 'Task.DepotMaintainPlans' && depotPlanEditor.hasPendingEdits()) ||
    (key === 'Task.EventDepotMaintainPlans' && eventDepotPlanEditor.hasPendingEdits()),
  onFailure: () => {
    const errorMsg = userError.value
    if (!errorMsg) message.error(t('core.edit.couldNotSaveUser'))
    logger.error(`保存失败: ${errorMsg || '用户 API 未返回成功'}`)
  },
  onError: error => {
    logger.error(`保存异常: ${error instanceof Error ? error.message : String(error)}`)
  },
  onSaved: (key, value) => {
    // 后端清空养成提示后，仅依据本次已保存的值同步当前页。
    if (key === 'Task.IfCultivate' && !value) {
      formData.Data.CultivateNotice = ''
    } else if (key === 'Task.CultivateTargets') {
      let hasTargets = false
      try {
        const parsed: unknown = JSON.parse(String(value ?? '[]'))
        hasTargets =
          Array.isArray(parsed) &&
          parsed.some((target: unknown) => {
            if (!target || typeof target !== 'object') return false
            const goals = (target as { goals?: unknown }).goals
            return Array.isArray(goals) && goals.length > 0
          })
      } catch {
        hasTargets = false
      }
      if (!hasTargets) formData.Data.CultivateNotice = ''
    }
    logger.info(`用户配置已保存: ${key}`)
  },
})
const { isSaving, saveField: handleFieldSave } = fieldSave

const prepareCopilotAnalysis = async () => {
  if (!(await fieldSave.flush())) throw new Error(t('core.edit.couldNotSaveUser'))
}

// 快速配置开关：与配置来源独立，真实保存
const handleQuickConfigChange = async (value: boolean) => {
  await handleFieldSave('Info.IfQuickConfig', value)
}

// 配置来源三态卡片（value 为后端 Info.Base 取值，驱动逻辑需保持原样；文案走词表）
const maaConfigModeOptions: Array<{
  value: 'shared' | 'independent' | 'native'
  title: string
  description: string
  icon: 'file' | 'database' | 'setting'
}> = [
  {
    value: 'shared',
    title: t('core.edit.script'),
    description: t('core.edit.useSharedScriptLevel'),
    icon: 'file',
  },
  {
    value: 'independent',
    title: t('core.edit.user'),
    description: t('core.edit.useThisUserS'),
    icon: 'database',
  },
  {
    value: 'native',
    title: t('core.edit.directControl'),
    description: t('core.edit.nativeConfigSourceDescription'),
    icon: 'setting',
  },
]

// 配置来源切换：校验 value ∈ options → 赋值 Info.Base → 保存
const handleConfigModeChange = async (value: boolean | string) => {
  if (typeof value !== 'string' || !['shared', 'independent', 'native'].includes(value)) return
  formData.Info.Base = value as 'shared' | 'independent' | 'native'
  await handleFieldSave('Info.Base', formData.Info.Base)
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
      if (!scriptApiError.value) message.error(t('core.edit.scriptDoesNotExist2'))
      handleCancel()
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载脚本信息失败: ${errorMsg}`)
    if (!scriptApiError.value) message.error(t('core.edit.couldNotLoadScript2'))
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
      if (!userError.value) message.error(t('core.edit.couldNotCreateUser'))
      handleCancel()
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`创建用户失败: ${errorMsg}`)
    if (!userError.value) message.error(t('core.edit.couldNotCreateUser'))
    handleCancel()
  }
}

// 加载用户数据
const loadUserData = async (): Promise<boolean> => {
  isInitializing.value = true
  // 恢复/重载配置后，旧目标或旧绑定的预览不能再回写。
  resetCultivatePreview()
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
            Stage: { ...getDefaultMAAUserData().Stage, ...userData.Stage },
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
        // 慢时库存列被串行阻塞。活动关卡和候选预取不等它们，
        // 放前面避免被目录最坏 30s 拖住。
        if (!activityStageLoading.value) void loadActivityStageOptions()
        preloadDepotStageCandidates()
        await Promise.all([loadCultivateOperatorOptions(), loadDepotInventory()])
        return true
      } else {
        message.error(t('core.edit.userDoesNotExist'))
        handleCancel()
      }
    } else {
      if (!userError.value) message.error(t('core.edit.couldNotFetchUser'))
      handleCancel()
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载用户数据失败: ${errorMsg}`)
    if (!userError.value) message.error(t('core.edit.couldNotLoadUser2'))
  }
  return false
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

const loadDepotStageCandidates = (itemId: string) => loadDepotStageCandidateBatch([itemId])

// 进页一次预取所有已配置材料，展开时复用缓存；慢数据源不会挤满保存请求的连接。
const preloadDepotStageCandidates = () => {
  try {
    const plans: Array<{ DropId?: string }> = JSON.parse(formData.Task.DepotMaintainPlans || '[]')
    void loadDepotStageCandidateBatch(
      plans.map(plan => plan?.DropId).filter((itemId): itemId is string => !!itemId)
    )
  } catch {
    logger.warn('库存保持候选预取失败，展开时按需加载')
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

const {
  cultivateOperatorCatalog,
  cultivateOperatorOptionsLoading,
  cultivateOperatorOptionsError,
  sklandRoleOptions,
  sklandRoleLoading,
  sklandRoleError,
  cultivatePreview,
  cultivatePreviewLoading,
  cultivatePreviewError,
  loadCultivateOperatorOptions,
  loadSklandRoleOptions,
  loadCultivatePreview,
  importCultivateTargets,
  resetCultivatePreview,
} = useMaaCultivation({
  scriptId,
  getUserId: () => userId,
  task: () => formData.Task,
  isInitializing: () => isInitializing.value,
  isLocked: () => configLocked.value,
  saveTargets: targets => handleFieldSave('Task.CultivateTargets', targets),
  trackEdit: edit => trackEdit(edit),
})

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
const handleInfrastPlanSelectChange = (index: number, label: string) =>
  trackEdit(async () => {
    if (configLocked.value) return
    try {
      const result = await Service.setInfrastPlanSelectApiScriptsUserInfrastructurePlanSelectPost({
        scriptId: scriptId,
        userId: userId,
        index: index,
      })
      if (!result || result.code !== 200) {
        message.error(t('core.edit.maaCustomInfrastPlanSelectFailed'))
        return
      }
      // 后端会把「自动」归一成第一班, 以返回值为准, 免得刷新前后显示不一致
      infrastPlanSelect.value = result.index ?? index
      message.success(t('core.edit.maaCustomInfrastPlanSelected', { name: label }))
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`设置基建班次失败: ${errorMsg}`)
      message.error(t('core.edit.maaCustomInfrastPlanSelectFailed'))
    }
  })

// 选择并导入基建配置文件
const selectAndImportInfrastructureConfig = () =>
  trackEdit(async () => {
    if (!isEdit.value) {
      message.warning(t('core.edit.saveUserBeforeImporting'))
      return
    }
    if (configLocked.value) return

    try {
      // 选择文件
      const path = await window.electronAPI?.selectFile([
        { name: t('core.edit.jsonFiles'), extensions: ['json'] },
        { name: t('core.edit.allFiles'), extensions: ['*'] },
      ])

      if (path && path.length > 0) {
        if (configLocked.value) {
          message.error(t('core.edit.configLocked'))
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
          formData.Task.InfrastName = fileName.replace('.json', '')

          message.success(t('core.edit.baseConfigurationImported'))

          // 重新加载基建配置选项与当前班次
          await loadInfrastructureOptions()
        } else {
          message.error(t('core.edit.couldNotImportBase'))
        }
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`基建配置导入失败: ${errorMsg}`)
      message.error(t('core.edit.couldNotImportBase'))
    } finally {
      infrastructureImporting.value = false
    }
  })

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

const depotPlanEditor = useDepotMaintainPlanEditor({
  getSavedPlans: () => formData.Task.DepotMaintainPlans,
  savePlans: value => {
    void handleFieldSave('Task.DepotMaintainPlans', value)
  },
  loadStageCandidates: async itemId => {
    if (!isInitializing.value) await loadDepotStageCandidates(itemId)
  },
  getBestStage: itemId => depotStageCandidates.value[itemId]?.[0]?.value,
  isLoading: () => loading.value,
})

const eventDepotPlanEditor = useDepotMaintainPlanEditor({
  eventMode: true,
  getSavedPlans: () => formData.Task.EventDepotMaintainPlans,
  savePlans: value => {
    void handleFieldSave('Task.EventDepotMaintainPlans', value)
  },
  loadStageCandidates: async () => {},
  getBestStage: () => undefined,
  isLoading: () => loading.value,
})

const {
  preparingSession,
  leavingPage,
  editorBusy,
  startConfiguration,
  restoreConfiguration,
  trackEdit,
} = useMAAEditorLifecycle({
  pageRef,
  canStart: () => !configLocked.value && !isInitializing.value && !!userId,
  flushEdits: async () => {
    // 结清纯读取的候选等待，让换材料或导入预设的编辑按当前结果保存。
    cancelDepotStageCandidates()
    if (isInitializing.value) return fieldSave.waitForPending()
    await depotPlanEditor.flushPendingEdits()
    await eventDepotPlanEditor.flushPendingEdits()
    await nextTick()
    return fieldSave.flush()
  },
  waitForSaves: fieldSave.waitForPending,
  flushImmediateEdits: () => {
    depotPlanEditor.savePlans()
    eventDepotPlanEditor.savePlans()
  },
  hasPendingEdits: () =>
    fieldSave.hasPendingEdits() ||
    depotPlanEditor.hasPendingEdits() ||
    eventDepotPlanEditor.hasPendingEdits() ||
    !!maaTaskId.value,
  disposeEdits: () => {
    depotPlanEditor.dispose()
    eventDepotPlanEditor.dispose()
  },
  startSession,
  stopSession,
  backup: () => ensureMaaBackup('mas'),
  onSaveError: error => {
    logger.error(`提交编辑失败: ${error instanceof Error ? error.message : String(error)}`)
    if (!userError.value) message.error(t('core.edit.couldNotSaveUser'))
  },
  onStopFailure: () => message.error(t('core.edit.maaSessionStopFailed')),
  onUnloadBlocked: () => message.warning(t('core.edit.maaEditorReloadBlocked')),
})

const handleMAAConfig = async () => {
  await startConfiguration(userId, 'user')
}

// 编辑托管设置：MAA 编辑页自己管会话，离开本页的路由守卫会停会话。
const handleScriptConfig = () => {
  void router.push(`/scripts/${scriptId}/edit/maa`)
}

const handleCancel = async () => {
  await router.push(
    cultivationPage ? { name: 'MAAUserEdit', params: { scriptId, userId } } : '/scripts'
  )
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

  formData.Stage[field] = value
  void handleFieldSave(`Stage.${field}`, value)
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
    message.warning(t('core.edit.stageP0AlreadyExists', { p0: trimmedName }))
    return false
  }

  // 添加到选项列表
  stageOptions.value.push({
    label: trimmedName,
    value: trimmedName,
    isCustom: true,
  })

  message.success(t('core.edit.customStageP0Added', { p0: trimmedName }))
  return true
}

// 添加主关卡
const addCustomStage = (stageName: string) => {
  if (!validateStageName(stageName)) {
    message.error(t('core.edit.enterValidStageName'))
    return
  }

  if (addStageToOptions(stageName)) {
    updateStageField('Stage', stageName.trim())
  }
}

// 添加备选关卡-1
const addCustomStage1 = (stageName: string) => {
  if (!validateStageName(stageName)) {
    message.error(t('core.edit.enterValidStageName'))
    return
  }

  if (addStageToOptions(stageName)) {
    updateStageField('Stage_1', stageName.trim())
  }
}

// 添加备选关卡-2
const addCustomStage2 = (stageName: string) => {
  if (!validateStageName(stageName)) {
    message.error(t('core.edit.enterValidStageName'))
    return
  }

  if (addStageToOptions(stageName)) {
    updateStageField('Stage_2', stageName.trim())
  }
}

// 添加备选关卡-3
const addCustomStage3 = (stageName: string) => {
  if (!validateStageName(stageName)) {
    message.error(t('core.edit.enterValidStageName'))
    return
  }

  if (addStageToOptions(stageName)) {
    updateStageField('Stage_3', stageName.trim())
  }
}

const updateMedicineNumb = (value: number) => {
  if (!isPlanMode.value) {
    formData.Stage.MedicineNumb = value
    handleFieldSave('Stage.MedicineNumb', value)
  }
}

const updateSeriesNumb = (value: string) => {
  if (!isPlanMode.value) {
    formData.Stage.SeriesNumb = value
    handleFieldSave('Stage.SeriesNumb', value)
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
const {
  restoreApi: backupApi,
  restore: restoreConfigBackup,
  ensureBackup,
} = useConfigBackupApi({
  scriptId,
  userId: () => userId,
  logger,
})
const restoreApi = {
  ...backupApi,
  restore: (target: string, time: string, force?: boolean) =>
    restoreBackup(target, time, false, force),
}

// 一键恢复与详细查看共用恢复事务：旧编辑先完成，恢复和重载期间保持锁定。
const restoreBackup = async (target: string, time: string, viewOnly = false, force = false) => {
  let response: Awaited<ReturnType<typeof restoreConfigBackup>> | undefined
  const restored = await restoreConfiguration(
    async () => {
      response = await restoreConfigBackup(target, time, force)
      if (response.code !== 200) return false
      restoreOpen.value = false
      if (target === 'mas' && !(await loadUserData())) return false
      return true
    },
    viewOnly ? (target === 'mas' ? userId : scriptId) : undefined,
    target === 'mas' ? 'user' : target === 'native' ? 'script' : 'unknown'
  )
  // 保留 409 给恢复基座执行损坏配置的二次确认；已恢复但重载/启动失败不能报成功。
  if (response && (restored || response.code !== 200)) return response
  return { code: 400, message: t('core.edit.configRestoreFailed') }
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

// 「查看详细配置」语义（对齐一条龙）：恢复该时点 + 拉起查看会话预览。
// 弹窗文案必须显式区分——该按钮极易被误以为只读，实际会真覆盖当前配置。
// mas 备份：恢复到 MAS 目录后启动查看会话（下发为查看的必经复制，GUI 所见
// 即备份）；原生备份：恢复到 MAA 本体后启动脚本级查看会话（跳过下发，
// 原生目录即备份）。查看会话结束不回写配置，原生现场由任务前快照还原。
// 与一键恢复同口径：单弹窗文案，跨配置来源时换标题并追加来源切换说明
// （确认后由基座把配置来源切回备份时点再恢复）。
const handleRestoreView = (
  target: string,
  item: { time: string; base?: string | null },
  currentMode?: string | null
) => {
  if (configLocked.value) return Promise.resolve(false)

  return new Promise<boolean>(resolve => {
    const { title, paragraphs } = buildRestoreConfirm(
      t,
      {
        title: t('core.edit.configRestoreDetailView'),
        desc: t('core.edit.configRestoreDetailConfirm', { script: MAA_DISPLAY_NAME }),
      },
      item.base,
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
      okText: t('core.edit.configRestoreConfirmOk'),
      cancelText: t('core.edit.cancel'),
      onOk: async () => {
        if (configLocked.value) {
          message.error(t('core.edit.configLocked'))
          resolve(false)
          return
        }

        try {
          const resp = await restoreBackup(target, item.time, true)
          if (resp.code !== 200) {
            throw new Error(resp.message || t('core.edit.configRestoreFailed'))
          }
          resolve(true)
        } catch (e) {
          message.error(e instanceof Error ? e.message : t('core.edit.configRestoreFailed'))
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
const ensureMaaBackup = ensureBackup

// 初始化加载
onMounted(async () => {
  if (!scriptId) {
    message.error(t('core.edit.missingScriptIdParameter'))
    handleCancel()
    return
  }

  // 先等脚本信息加载（新建模式内部会创建用户并写入 userId），native 归档
  // 虽不需要用户但后端 ensure 端点要求 userId 参数——必须在 userId 就绪后
  // 才能发出，否则新建用户首次进入会静默跳过归档
  await loadScriptInfo()
  loadStageModeOptions()
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
    () => formData.Stage.StageMode,
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

            message.success(t('core.edit.switchedPlanModeP0', { p0: planName }))
          } else {
            logger.warn(`计划配置响应不完整: ${JSON.stringify({ response, newStageMode })}`)
            message.warning(t('core.edit.couldNotLoadPlan'))
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
          message.error(t('core.edit.somethingWentWrongLoading'))
          planModeConfig.value = null
        }
      }
    },
    { immediate: false }
  )
})
</script>

<style scoped>
.cultivation-page-loading {
  display: grid;
  place-items: center;
  min-height: 240px;
}
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
