<template>
  <div>
    <a-row :gutter="24">
      <a-col :xs="24" :sm="12">
        <a-form-item :label="t('core.edit.sanityTaskConfigurationMode')">
          <a-select
            :value="formData.Info.SanityMode"
            :options="sanityModeOptions"
            :disabled="loading"
            @change="(value: string) => emit('save', 'Info.SanityMode', value)"
          />
        </a-form-item>
      </a-col>
      <a-col :xs="24" :sm="12">
        <a-form-item :label="t('core.edit.sanityTask')">
          <div v-if="isPlanMode" class="plan-mode-display">
            {{ displayType }}
          </div>
          <a-select
            v-else
            :value="formData.Task.SanityTaskType"
            :options="taskTypes"
            :disabled="disabled"
            @change="handleTypeChange"
          />
        </a-form-item>
      </a-col>
      <a-col :xs="24" :sm="12">
        <a-form-item :label="taskTitle">
          <div v-if="isPlanMode" class="plan-mode-display">{{ displayTask }}</div>
          <a-select
            v-else
            :value="currentValue"
            :options="currentOptions"
            :disabled="disabled"
            @change="handleTaskChange"
          />
        </a-form-item>
      </a-col>
      <a-col v-if="rewardEnabled" :xs="24" :sm="12">
        <a-form-item :label="t('core.edit.rewardGroup')">
          <div v-if="isPlanMode" class="plan-mode-display">
            {{ REWARD_LABEL_MAP[planModeConfig!.RewardsSetOption] }}
          </div>
          <a-select
            v-else
            :value="formData.Task.RewardsSetOption"
            :options="REWARD_OPTIONS"
            :disabled="disabled"
            @change="(value: string) => emit('save', 'Task.RewardsSetOption', value)"
          />
        </a-form-item>
      </a-col>
    </a-row>
    <a-alert
      v-if="isPlanMode && planModeConfig?.SanityTaskType === 'Essence'"
      type="info"
      show-icon
      :message="t('core.edit.maaEndProtocolPlanSkipped')"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ComboBoxItem } from '@/api'
import type { MaaEndUserForm } from './userDefaults'
import {
  PROTOCOL_SPACE_TASK_FIELD_MAP,
  PROTOCOL_SPACE_TASK_OPTIONS_MAP,
  PROTOCOL_SPACE_TASK_TITLE_MAP,
  SANITY_TASK_TYPE_OPTIONS,
  SANITY_TASK_TYPE_LABEL_MAP,
  REWARD_OPTIONS,
  REWARD_LABEL_MAP,
  getSanityTaskDisplayValue,
  isProtocolSpaceRewardEnabled,
  type MaaEndSanityConfig,
  type ProtocolSpaceTab,
} from '@/utils/maaEndProtocolSpace'

const props = defineProps<{
  formData: MaaEndUserForm
  loading: boolean
  crisisDrillsOptions: ComboBoxItem[]
  optionsLoading: boolean
  sanityModeOptions: Array<{ label: string; value: string }>
  isPlanMode: boolean
  planModeConfig: MaaEndSanityConfig | null
}>()
const emit = defineEmits<{
  save: [key: string, value: unknown]
  saveBatch: [changes: Array<{ key: string; value: unknown }>]
}>()
const { t } = useI18n()
const formData = props.formData
const disabled = computed(() => props.loading || props.optionsLoading)
const taskTypes = SANITY_TASK_TYPE_OPTIONS.filter(option => option.value !== 'Essence')
const taskType = computed<ProtocolSpaceTab>(() =>
  taskTypes.some(option => option.value === formData.Task.SanityTaskType)
    ? (formData.Task.SanityTaskType as ProtocolSpaceTab)
    : 'OperatorProgression'
)
const field = computed(() => PROTOCOL_SPACE_TASK_FIELD_MAP[taskType.value])
const currentValue = computed(() => formData.Task[field.value])
const currentOptions = computed(() =>
  taskType.value === 'CrisisDrills'
    ? props.crisisDrillsOptions
    : PROTOCOL_SPACE_TASK_OPTIONS_MAP[taskType.value]
)
const taskTitle = computed(
  () =>
    PROTOCOL_SPACE_TASK_TITLE_MAP[
      props.isPlanMode && props.planModeConfig && props.planModeConfig.SanityTaskType !== 'Essence'
        ? props.planModeConfig.SanityTaskType
        : taskType.value
    ]
)
const displayType = computed(() =>
  props.planModeConfig
    ? SANITY_TASK_TYPE_LABEL_MAP[props.planModeConfig.SanityTaskType]
    : t('core.edit.maaEndPlanUnavailable')
)
const displayTask = computed(() =>
  props.planModeConfig
    ? getSanityTaskDisplayValue(props.planModeConfig, [], props.crisisDrillsOptions)
    : t('core.edit.maaEndPlanUnavailable')
)
const rewardEnabled = computed(() =>
  props.isPlanMode
    ? !!props.planModeConfig &&
      props.planModeConfig.SanityTaskType !== 'Essence' &&
      isProtocolSpaceRewardEnabled(props.planModeConfig)
    : currentOptions.value.some(
        option => option.value === currentValue.value && 'rewards' in option && option.rewards
      )
)

const handleTypeChange = (value: ProtocolSpaceTab) => {
  if (disabled.value) return
  formData.Task.SanityTaskType = value
  const changes: Array<{ key: string; value: unknown }> = [{ key: 'Task.SanityTaskType', value }]
  if (
    !currentOptions.value.some(option => option.value === currentValue.value) &&
    currentOptions.value[0]?.value
  ) {
    changes.push({ key: `Task.${field.value}`, value: currentOptions.value[0].value })
  }
  emit('saveBatch', changes)
}
const handleTaskChange = (value: string) => {
  if (disabled.value) return
  emit('save', `Task.${field.value}`, value)
}
</script>

<style scoped>
.plan-mode-display {
  min-height: 40px;
  display: flex;
  align-items: center;
  color: var(--ant-color-text-secondary);
}
</style>
