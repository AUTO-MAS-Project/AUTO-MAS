<!-- eslint-disable vue/no-mutating-props -->
<template>
  <div class="form-section">
    <div class="section-header">
      <h3>任务配置</h3>
      <a-button
        v-if="
          showSanityOptions &&
          isPlanMode &&
          formData.Info.SanityMode &&
          formData.Info.SanityMode !== 'Fixed'
        "
        type="link"
        class="plans-button"
        @click="handleGoToPlans"
      >
        <template #icon>
          <CalendarOutlined />
        </template>
        跳转到计划表
      </a-button>
    </div>

    <a-alert v-if="modeNotice" :message="modeNotice" type="info" show-icon class="mode-notice" />

    <a-row :gutter="24">
      <a-col v-for="task in presetTaskSwitches" :key="task.key" :span="6">
        <a-form-item>
          <template #label>
            <a-tooltip :title="task.tooltip">
              <span>
                {{ task.label }}
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-switch
            :checked="task.enabled"
            :disabled="controlsDisabled"
            @change="handlePresetTaskChange(task, Boolean($event))"
          />
        </a-form-item>
      </a-col>
    </a-row>

    <a-row v-if="showSanityOptions" :gutter="24">
      <a-col v-if="showSanityMode" :span="8">
        <a-form-item>
          <template #label>
            <a-tooltip title="可选择固定配置或引用 MaaEnd 计划表">
              <span class="form-label">
                理智任务配置模式
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            v-model:value="formData.Info.SanityMode"
            :options="sanityModeOptions"
            :disabled="optionControlsDisabled"
            size="large"
            @change="emitSave('Info.SanityMode', formData.Info.SanityMode)"
          />
        </a-form-item>
      </a-col>

      <a-col :span="optionColumnSpan">
        <a-form-item>
          <template #label>
            <a-tooltip
              :title="isPlanMode ? '当前生效理智任务来自计划表' : '选择当前执行的理智任务类型'"
            >
              <span class="form-label">
                理智任务
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <div v-if="isPlanMode" class="plan-mode-display">
            <div class="plan-value">{{ displaySanityTaskType }}</div>
            <a-tooltip>
              <template #title>
                <div class="plan-tooltip">{{ sanityTaskTypeTooltip }}</div>
              </template>
              <div class="plan-source">来自计划表</div>
            </a-tooltip>
          </div>
          <a-select
            v-else
            v-model:value="formData.Task.SanityTaskType"
            :options="SANITY_TASK_TYPE_OPTIONS"
            :disabled="optionControlsDisabled"
            size="large"
            @change="handleSanityTaskTypeChange"
          />
        </a-form-item>
      </a-col>

      <a-col :span="optionColumnSpan">
        <a-form-item>
          <template #label>
            <a-tooltip :title="isPlanMode ? '当前生效任务来自计划表' : taskOptionTooltip">
              <span class="form-label">
                {{ taskOptionLabel }}
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <div v-if="isPlanMode" class="plan-mode-display">
            <div class="plan-value">{{ displayCurrentTask }}</div>
            <a-tooltip>
              <template #title>
                <div class="plan-tooltip">{{ currentTaskTooltip }}</div>
              </template>
              <div class="plan-source">来自计划表</div>
            </a-tooltip>
          </div>
          <a-select
            v-else
            v-model:value="currentTaskValue"
            :options="currentTaskOptions"
            :disabled="optionControlsDisabled"
            size="large"
            @change="handleTaskOptionChange"
          />
        </a-form-item>
      </a-col>
    </a-row>

    <a-row v-if="showSanityOptions" :gutter="24">
      <a-col :span="8">
        <a-form-item>
          <template #label>
            <a-tooltip
              :title="
                isPlanMode
                  ? '当前生效奖励组来自计划表；非协议空间奖励任务会固定为奖励组 A'
                  : '协议空间奖励任务可在这里选择奖励组，基质刷取固定奖励组 A'
              "
            >
              <span class="form-label">
                可选奖励组
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <div v-if="isPlanMode" class="plan-mode-display">
            <div class="plan-value">{{ displayRewardsSet }}</div>
            <a-tooltip>
              <template #title>
                <div class="plan-tooltip">{{ rewardsTooltip }}</div>
              </template>
              <div class="plan-source">来自计划表</div>
            </a-tooltip>
          </div>
          <a-select
            v-else
            v-model:value="formData.Task.RewardsSetOption"
            :options="REWARD_OPTIONS"
            :disabled="optionControlsDisabled || !rewardGroupEnabled"
            size="large"
            @change="emitSave('Task.RewardsSetOption', formData.Task.RewardsSetOption)"
          />
        </a-form-item>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'
import { CalendarOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import { navigateTo } from '@/router'
import type { MaaEndPresetTask } from '@/composables/useMaaEndPresetTasks'
import {
  AUTO_ESSENCE_LOCATION_OPTIONS,
  PROTOCOL_SPACE_TASK_FIELD_MAP,
  PROTOCOL_SPACE_TASK_OPTIONS_MAP,
  PROTOCOL_SPACE_TASK_TITLE_MAP,
  PROTOCOL_SPACE_TASK_TOOLTIP_MAP,
  REWARD_LABEL_MAP,
  REWARD_OPTIONS,
  SANITY_TASK_TYPE_LABEL_MAP,
  SANITY_TASK_TYPE_OPTIONS,
  getSanityTaskDisplayValue,
  normalizeMaaEndSanityConfig,
  type MaaEndSanityConfig,
  type ProtocolSpaceTab,
  type SanityTaskType,
} from '@/utils/maaEndProtocolSpace'

interface FieldChange {
  key: string
  value: any
}

const props = withDefaults(
  defineProps<{
    formData: any
    loading?: boolean
    mode?: string
    source?: 'script' | 'user'
    controllerType?: string | null
    isPlanMode?: boolean
    sanityModeOptions?: Array<{ label: string; value: string }>
    planModeConfig?: MaaEndSanityConfig | null
    presetTasks?: MaaEndPresetTask[]
    sanityTaskTypeTooltip?: string
    currentTaskTooltip?: string
    rewardsTooltip?: string
  }>(),
  {
    loading: false,
    mode: '详细',
    source: 'user',
    controllerType: null,
    isPlanMode: false,
    sanityModeOptions: () => [{ label: '固定配置', value: 'Fixed' }],
    planModeConfig: null,
    presetTasks: () => [],
    sanityTaskTypeTooltip: '',
    currentTaskTooltip: '',
    rewardsTooltip: '',
  }
)

const emit = defineEmits<{
  save: [key: string, value: any]
  saveBatch: [changes: FieldChange[]]
  togglePresetTasks: [taskIds: string[], enabled: boolean]
}>()

const formData = props.formData
const showSanityOptions = computed(() => props.controllerType !== 'Win32-Window')
const showSanityMode = computed(() => showSanityOptions.value && props.source === 'user')
const optionColumnSpan = computed(() => (showSanityMode.value ? 8 : 12))

interface PresetTaskSwitch {
  key: string
  label: string
  tooltip: string
  taskIds: string[]
  enabled: boolean
}

const presetTaskInfo: Record<string, { label: string; tooltip: string }> = {
  VisitFriends: { label: '🤝拜访好友', tooltip: '是否启用🤝拜访好友' },
  DijiangRewards: { label: '🎁基建任务', tooltip: '是否启用🎁基建任务' },
  CreditShoppingN2: { label: '🛍️信用点购物', tooltip: '是否启用🛍️信用点购物' },
  DeliveryJobs: { label: '🚚转交委托', tooltip: '是否启用🚚转交委托' },
  SellProduct: { label: '🛒售卖产品', tooltip: '是否启用🛒售卖产品' },
  AutoStockpile: { label: '📦自动囤货', tooltip: '是否启用📦自动囤货' },
  AutoStockStaple: { label: '🏪购买稳定物资', tooltip: '是否启用🏪购买稳定物资' },
  AutoSell: { label: '💰售卖弹性物资', tooltip: '是否启用💰售卖弹性物资' },
  EnvironmentMonitoring: { label: '🌿环境监测', tooltip: '是否启用🌿环境监测' },
  DailyRewards: { label: '📅日常奖励领取', tooltip: '是否启用📅日常奖励领取' },
  SeizeEntrustTask: { label: '🌆抢委托', tooltip: '是否启用🌆抢委托' },
  AutoCollect: { label: '🧺自动采集', tooltip: '是否启用🧺自动采集' },
  AutoUseSpMedication: { label: '💊应急理智加强剂', tooltip: '是否启用💊应急理智加强剂' },
  ResourceRecycleStation: { label: '🦉资源回收站', tooltip: '是否启用🦉资源回收站' },
  AutoEcoFarm: { label: '🌾生态农场', tooltip: '是否启用🌾生态农场' },
}

const presetTaskSwitches = computed(() => {
  const sanityTasks = props.presetTasks.filter(task =>
    ['ProtocolSpace', 'AutoEssence'].includes(task.taskName)
  )
  const switches: PresetTaskSwitch[] = []
  if (sanityTasks.length) {
    switches.push({
      key: 'Sanity',
      label: '理智任务',
      tooltip: '是否启用协议空间或基质刷取任务',
      taskIds: sanityTasks.map(task => task.id),
      enabled: sanityTasks.some(task => task.enabled),
    })
  }

  props.presetTasks.forEach(task => {
    const taskInfo = presetTaskInfo[task.taskName]
    if (!taskInfo) return
    switches.push({
      key: task.id,
      taskIds: [task.id],
      enabled: task.enabled,
      ...taskInfo,
    })
  })
  return switches
})

const controlsDisabled = computed(() => {
  return (
    props.loading || (props.source === 'user' && props.mode === '简洁') || props.mode === '自定义'
  )
})

const sanityTasksEnabled = computed(() =>
  props.presetTasks
    .filter(task => ['ProtocolSpace', 'AutoEssence'].includes(task.taskName))
    .some(task => task.enabled)
)
const optionControlsDisabled = computed(() => controlsDisabled.value || !sanityTasksEnabled.value)

const modeNotice = computed(() => {
  if (props.source === 'script') {
    return '简洁模式用户将使用这里的脚本级预设任务配置。'
  }
  if (props.mode === '简洁') {
    return '简洁模式使用脚本级预设配置，请在脚本配置页调整任务开关和选项。'
  }
  if (props.mode === '自定义') {
    return '自定义模式运行用户完整 MaaEnd 配置，MAS 不托管业务任务队列。'
  }
  return ''
})

const currentField = computed(
  () => PROTOCOL_SPACE_TASK_FIELD_MAP[formData.Task.SanityTaskType as ProtocolSpaceTab]
)

const currentTaskOptions = computed(() => {
  if (formData.Task.SanityTaskType === 'Essence') {
    return AUTO_ESSENCE_LOCATION_OPTIONS
  }
  return PROTOCOL_SPACE_TASK_OPTIONS_MAP[formData.Task.SanityTaskType as ProtocolSpaceTab]
})

const currentTaskValue = computed({
  get: () => {
    if (formData.Task.SanityTaskType === 'Essence') {
      return formData.Task.AutoEssenceSpecifiedLocation
    }
    return formData.Task[currentField.value]
  },
  set: value => {
    if (formData.Task.SanityTaskType === 'Essence') {
      formData.Task.AutoEssenceSpecifiedLocation = value
      return
    }
    formData.Task[currentField.value] = value
  },
})

const currentTaskOption = computed(() =>
  currentTaskOptions.value.find(option => option.value === currentTaskValue.value)
)

const rewardGroupEnabled = computed(() => {
  if (formData.Task.SanityTaskType === 'Essence') return false
  return Boolean(currentTaskOption.value?.rewards)
})

const displayPlanConfig = computed(() =>
  props.planModeConfig ? normalizeMaaEndSanityConfig(props.planModeConfig) : null
)

const displaySanityTaskType = computed(() => {
  if (!displayPlanConfig.value) return '未读取到计划表配置'
  return SANITY_TASK_TYPE_LABEL_MAP[displayPlanConfig.value.SanityTaskType]
})

const displayCurrentTask = computed(() => {
  if (!displayPlanConfig.value) return '未读取到计划表配置'
  return getSanityTaskDisplayValue(displayPlanConfig.value)
})

const displayRewardsSet = computed(() => {
  if (!displayPlanConfig.value) return '未读取到计划表配置'
  return REWARD_LABEL_MAP[displayPlanConfig.value.RewardsSetOption]
})

const taskOptionLabel = computed(() =>
  formData.Task.SanityTaskType === 'Essence'
    ? '基质地点'
    : (PROTOCOL_SPACE_TASK_TITLE_MAP[formData.Task.SanityTaskType as ProtocolSpaceTab] ??
      '协议空间任务')
)

const taskOptionTooltip = computed(() =>
  formData.Task.SanityTaskType === 'Essence'
    ? '选择当前基质刷取地点'
    : (PROTOCOL_SPACE_TASK_TOOLTIP_MAP[formData.Task.SanityTaskType as ProtocolSpaceTab] ??
      '选择当前协议空间任务')
)

const emitSave = (key: string, value: any) => {
  if (controlsDisabled.value) return
  emit('save', key, value)
}

const emitSaveBatch = (changes: FieldChange[]) => {
  if (controlsDisabled.value || !changes.length) return
  emit('saveBatch', changes)
}

const handlePresetTaskChange = (task: PresetTaskSwitch, enabled: boolean) => {
  if (controlsDisabled.value) return
  emit('togglePresetTasks', task.taskIds, enabled)
}

const handleGoToPlans = () => {
  const planId =
    props.isPlanMode && formData.Info.SanityMode && formData.Info.SanityMode !== 'Fixed'
      ? formData.Info.SanityMode
      : undefined

  navigateTo('/plans', {
    query: {
      from: 'sanity-task-config',
      ...(planId ? { planId } : {}),
    },
  })
}

const ensureCurrentTaskValue = () => {
  if (optionControlsDisabled.value) return
  const options = currentTaskOptions.value
  if (!options.some(option => option.value === currentTaskValue.value)) {
    currentTaskValue.value = options[0].value
  }
}

const normalizeRewardGroupState = (): FieldChange | null => {
  if (!rewardGroupEnabled.value && formData.Task.RewardsSetOption !== 'RewardsSetA') {
    formData.Task.RewardsSetOption = 'RewardsSetA'
    return { key: 'Task.RewardsSetOption', value: formData.Task.RewardsSetOption }
  }
  return null
}

const handleSanityTaskTypeChange = (value: SanityTaskType) => {
  if (optionControlsDisabled.value) return
  formData.Task.SanityTaskType = value
  ensureCurrentTaskValue()

  const changes: FieldChange[] = [
    { key: 'Task.SanityTaskType', value: formData.Task.SanityTaskType },
  ]

  if (value === 'Essence') {
    changes.push({
      key: 'Task.AutoEssenceSpecifiedLocation',
      value: formData.Task.AutoEssenceSpecifiedLocation ?? 'VFTheHub',
    })
  } else {
    changes.push({ key: `Task.${currentField.value}`, value: currentTaskValue.value })
  }

  const rewardGroupChange = normalizeRewardGroupState()
  if (rewardGroupChange) {
    changes.push(rewardGroupChange)
  }

  emitSaveBatch(changes)
}

const handleTaskOptionChange = () => {
  if (optionControlsDisabled.value) return
  const changes: FieldChange[] = []

  if (formData.Task.SanityTaskType === 'Essence') {
    changes.push({
      key: 'Task.AutoEssenceSpecifiedLocation',
      value: formData.Task.AutoEssenceSpecifiedLocation,
    })
  } else {
    changes.push({ key: `Task.${currentField.value}`, value: currentTaskValue.value })
  }

  const rewardGroupChange = normalizeRewardGroupState()
  if (rewardGroupChange) {
    changes.push(rewardGroupChange)
  }

  emitSaveBatch(changes)
}

watch(
  () => formData.Task.SanityTaskType,
  () => {
    if (props.isPlanMode || optionControlsDisabled.value) return
    ensureCurrentTaskValue()
    normalizeRewardGroupState()
  },
  { immediate: true }
)
</script>

<style scoped>
.form-section {
  margin-bottom: 32px;
}

.section-header {
  margin-bottom: 20px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--ant-color-border-secondary);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.mode-notice {
  margin-bottom: 16px;
}

.section-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--ant-color-text);
  display: flex;
  align-items: center;
  gap: 12px;
}

.section-header h3::before {
  content: '';
  width: 4px;
  height: 24px;
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  border-radius: 2px;
}

.plans-button {
  font-size: 14px;
  color: var(--ant-color-primary);
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 4px;
}

.form-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: var(--ant-color-text);
  font-size: 14px;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
  cursor: help;
  transition: color 0.3s ease;
}

.help-icon:hover {
  color: var(--ant-color-primary);
}

.plan-mode-display {
  min-height: 40px;
  padding: 8px 12px;
  border: 1px solid var(--ant-color-border);
  border-radius: 6px;
  background: var(--ant-color-bg-container);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.plan-value {
  color: var(--ant-color-text);
  font-weight: 500;
}

.plan-source {
  font-size: 12px;
  color: var(--ant-color-primary);
  white-space: nowrap;
  cursor: help;
}

.plan-tooltip {
  white-space: pre-line;
}
</style>
