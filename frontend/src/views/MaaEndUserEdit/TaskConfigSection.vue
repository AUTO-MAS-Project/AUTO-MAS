<!-- eslint-disable vue/no-mutating-props -->
<template>
  <div class="form-section">
    <div class="section-header">
      <h3>任务配置</h3>
    </div>

    <a-alert
      v-if="modeNotice"
      :message="modeNotice"
      type="info"
      show-icon
      class="mode-notice"
    />

    <a-row :gutter="24">
      <a-col v-for="task in presetTaskSwitches" :key="task.field" :span="6">
        <a-form-item :name="task.field">
          <template #label>
            <a-tooltip :title="task.tooltip">
              <span>
                {{ task.label }}
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-switch
            v-model:checked="formData.Task[task.field]"
            :disabled="controlsDisabled"
            @change="emitSave(`Task.${task.field}`, formData.Task[task.field])"
          />
        </a-form-item>
      </a-col>
    </a-row>

    <a-row :gutter="24">

      <a-col :span="8">
        <a-form-item>
          <template #label>
            <a-tooltip title="选择当前要执行的协议空间任务分类">
              <span class="form-label">
                协议空间
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            v-model:value="formData.Task.ProtocolSpaceTab"
            :options="protocolSpaceOptions"
            :disabled="optionControlsDisabled"
            size="large"
            @change="handleProtocolSpaceChange"
          />
        </a-form-item>
      </a-col>

      <a-col :span="8">
        <a-form-item>
          <template #label>
            <a-tooltip :title="taskOptionTooltip">
              <span class="form-label">
                {{ taskOptionLabel }}
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            v-model:value="currentTaskValue"
            :options="currentTaskOptions"
            :disabled="optionControlsDisabled"
            size="large"
            @change="handleTaskOptionChange"
          />
        </a-form-item>
      </a-col>

      <a-col :span="8">
        <a-form-item>
          <template #label>
            <a-tooltip title="当前任务支持奖励组切换时，可在这里选择对应奖励组">
              <span class="form-label">
                可选奖励组
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            v-model:value="formData.Task.RewardsSetOption"
            :options="rewardOptions"
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
import { QuestionCircleOutlined } from '@ant-design/icons-vue'

const props = withDefaults(
  defineProps<{
    formData: any
    loading?: boolean
    mode?: string
    source?: 'script' | 'user'
  }>(),
  {
    loading: false,
    mode: '详细',
    source: 'user',
  }
)

const emit = defineEmits<{
  save: [key: string, value: any]
}>()

const protocolSpaceOptions = [
  { label: '干员养成', value: 'OperatorProgression' },
  { label: '武器养成', value: 'WeaponProgression' },
  { label: '危境预演', value: 'CrisisDrills' },
]

const presetTaskSwitches = [
  {
    label: '协议空间',
    field: 'IfProtocolSpace',
    tooltip: '是否启用 MAS 托管的协议空间预设任务',
  },
  {
    label: '访问好友',
    field: 'IfVisitFriends',
    tooltip: '是否启用访问好友任务',
  },
  {
    label: '帝江奖励',
    field: 'IfDijiangRewards',
    tooltip: '是否启用帝江奖励任务',
  },
  {
    label: '信用采购',
    field: 'IfCreditShoppingN2',
    tooltip: '是否启用信用采购任务',
  },
  {
    label: '配送委托',
    field: 'IfDeliveryJobs',
    tooltip: '是否启用配送委托任务',
  },
  {
    label: '自动售卖',
    field: 'IfSellProduct',
    tooltip: '是否启用自动售卖任务',
  },
  {
    label: '自动备货',
    field: 'IfAutoStockpile',
    tooltip: '是否启用自动备货任务',
  },
  {
    label: '自动补货',
    field: 'IfAutoStockStaple',
    tooltip: '是否启用自动补货任务',
  },
  {
    label: '自动交易',
    field: 'IfAutoSell',
    tooltip: '是否启用自动交易任务',
  },
  {
    label: '环境监测',
    field: 'IfEnvironmentMonitoring',
    tooltip: '是否启用环境监测任务',
  },
  {
    label: '日常奖励',
    field: 'IfDailyRewards',
    tooltip: '是否启用日常奖励任务',
  },
  {
    label: '收取委托',
    field: 'IfSeizeEntrustTask',
    tooltip: '是否启用收取委托任务',
  },
  {
    label: '自动采集',
    field: 'IfAutoCollect',
    tooltip: '是否启用自动采集任务',
  },
  {
    label: '自动用理智药',
    field: 'IfAutoUseSpMedication',
    tooltip: '是否启用自动用理智药任务',
  },
  {
    label: '资源回收',
    field: 'IfResourceRecycleStation',
    tooltip: '是否启用资源回收任务',
  },
  {
    label: '自动农场',
    field: 'IfAutoEcoFarm',
    tooltip: '是否启用自动农场任务',
  },
  {
    label: '基质刷取',
    field: 'IfAutoEssence',
    tooltip: '是否启用基质刷取任务',
  },
]

const taskOptionsMap: Record<string, Array<{ label: string; value: string; rewards?: boolean }>> = {
  OperatorProgression: [
    { label: '干员经验', value: 'OperatorEXP', rewards: true },
    { label: '干员进阶', value: 'Promotions', rewards: true },
    { label: '钱币收集', value: 'T-Creds', rewards: false },
    { label: '技能提升', value: 'SkillUp', rewards: true },
  ],
  WeaponProgression: [
    { label: '武器经验', value: 'WeaponEXP', rewards: false },
    { label: '武器进阶', value: 'WeaponTune', rewards: true },
  ],
  CrisisDrills: [
    { label: '高阶培养 I - D96钢样品四', value: 'AdvancedProgression1', rewards: false },
    { label: '高阶培养 II - 超距辉映管', value: 'AdvancedProgression2', rewards: false },
    { label: '高阶培养 III - 快子遴捡晶格', value: 'AdvancedProgression3', rewards: false },
    { label: '高阶培养 IV - 象限拟合液', value: 'AdvancedProgression4', rewards: false },
    { label: '高阶培养 V - 三相纳米片', value: 'AdvancedProgression5', rewards: false },
  ],
}

const rewardOptions = [
  { label: '奖励组 A', value: 'RewardsSetA' },
  { label: '奖励组 B', value: 'RewardsSetB' },
]

const protocolTaskFieldMap: Record<string, string> = {
  OperatorProgression: 'OperatorProgression',
  WeaponProgression: 'WeaponProgression',
  CrisisDrills: 'CrisisDrills',
}

const taskLabelMap: Record<string, string> = {
  OperatorProgression: '干员养成任务',
  WeaponProgression: '武器养成任务',
  CrisisDrills: '危境预演任务',
}

const taskTooltipMap: Record<string, string> = {
  OperatorProgression: '选择要执行的干员养成任务',
  WeaponProgression: '选择要执行的武器养成任务',
  CrisisDrills: '选择要执行的危境预演任务',
}

const currentField = computed(() => protocolTaskFieldMap[props.formData.Task.ProtocolSpaceTab])

const currentTaskOptions = computed(
  () => taskOptionsMap[props.formData.Task.ProtocolSpaceTab] ?? taskOptionsMap.OperatorProgression
)

const currentTaskValue = computed({
  get: () => props.formData.Task[currentField.value],
  set: value => {
    props.formData.Task[currentField.value] = value
  },
})

const currentTaskOption = computed(() => {
  return currentTaskOptions.value.find(option => option.value === currentTaskValue.value)
})

const taskOptionLabel = computed(
  () => taskLabelMap[props.formData.Task.ProtocolSpaceTab] ?? '干员养成任务'
)

const taskOptionTooltip = computed(
  () => taskTooltipMap[props.formData.Task.ProtocolSpaceTab] ?? '选择要执行的干员养成任务'
)

const rewardGroupEnabled = computed(() => Boolean(currentTaskOption.value?.rewards))

const controlsDisabled = computed(() => {
  return (
    props.loading ||
    (props.source === 'user' && props.mode === '简洁') ||
    props.mode === '自定义'
  )
})

const optionControlsDisabled = computed(() => {
  return controlsDisabled.value || !props.formData.Task.IfProtocolSpace
})

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

const emitSave = (key: string, value: any) => {
  if (controlsDisabled.value) return
  emit('save', key, value)
}

const ensureCurrentTaskValue = () => {
  if (controlsDisabled.value) return
  const options = currentTaskOptions.value
  if (!options.some(option => option.value === currentTaskValue.value)) {
    currentTaskValue.value = options[0].value
  }
}

const ensureRewardGroupState = () => {
  if (controlsDisabled.value) return
  if (!rewardGroupEnabled.value && props.formData.Task.RewardsSetOption !== 'RewardsSetA') {
    props.formData.Task.RewardsSetOption = 'RewardsSetA'
    emitSave('Task.RewardsSetOption', props.formData.Task.RewardsSetOption)
  }
}

const handleProtocolSpaceChange = () => {
  if (controlsDisabled.value) return
  ensureCurrentTaskValue()
  emitSave('Task.ProtocolSpaceTab', props.formData.Task.ProtocolSpaceTab)
  emitSave(`Task.${currentField.value}`, currentTaskValue.value)
  ensureRewardGroupState()
}

const handleTaskOptionChange = () => {
  if (controlsDisabled.value) return
  emitSave(`Task.${currentField.value}`, currentTaskValue.value)
  ensureRewardGroupState()
}

watch(
  () => props.formData.Task.ProtocolSpaceTab,
  () => {
    ensureCurrentTaskValue()
    ensureRewardGroupState()
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
</style>
