<template>
  <div>
    <div class="sanity-task-toggle" :class="{ 'sanity-task-enabled': showSanityDetail }">
      <span>{{ t('edit.maaEndEnableSanity') }}</span>
      <a-switch
        v-model:checked="formData.Task.IfSanity"
        :disabled="controlsDisabled"
        :aria-label="t('edit.maaEndEnableSanity')"
        @change="emitSave('Task.IfSanity', formData.Task.IfSanity)"
      />
    </div>

    <a-row v-if="showSanityDetail" :gutter="24">
      <a-col :xs="24" :sm="12">
        <a-form-item :label="t('edit.sanityTaskConfigurationMode')">
          <a-select
            v-model:value="formData.Info.SanityMode"
            :options="resolvedSanityModeOptions"
            :disabled="loading"
            size="middle"
            @change="emitSave('Info.SanityMode', formData.Info.SanityMode)"
          />
        </a-form-item>
      </a-col>

      <a-col :xs="24" :sm="12">
        <a-form-item>
          <template #label>
            <a-tooltip :title="t('edit.pickSanityTaskType')">
              <span class="form-label">
                {{ t('edit.sanityTask') }}
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <div v-if="isPlanMode" class="plan-mode-display">
            <span>{{ displaySanityTaskType }}</span>
            <span class="plan-source">{{ t('edit.fromPlan') }}</span>
          </div>
          <a-select
            v-else
            v-model:value="formData.Task.SanityTaskType"
            :options="sanityTaskTypeOptions"
            :disabled="optionControlsDisabled"
            size="middle"
            @change="handleSanityTaskTypeChange"
          />
        </a-form-item>
      </a-col>

      <a-col v-if="effectiveSanityTaskType === 'Essence'" :xs="24" :sm="12">
        <a-form-item :label="t('edit.maaEndEssenceFarmMode')">
          <div v-if="isPlanMode" class="plan-mode-display">
            <span>{{ displayEssenceMenu }}</span>
            <span class="plan-source">{{ t('edit.fromPlan') }}</span>
          </div>
          <a-select
            v-else
            :value="formData.Task.AutoEssenceMenu"
            :options="resolvedEssenceMenuOptions"
            :disabled="optionControlsDisabled"
            size="middle"
            @change="handleEssenceMenuChange"
          />
        </a-form-item>
      </a-col>

      <a-col :xs="24" :sm="12">
        <a-form-item>
          <template #label>
            <a-tooltip :title="taskOptionTooltip">
              <span class="form-label">
                {{ taskOptionLabel }}
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <div v-if="isPlanMode" class="plan-mode-display">
            <span>{{ displayCurrentTask }}</span>
            <span class="plan-source">{{ t('edit.fromPlan') }}</span>
          </div>
          <a-select
            v-else
            v-model:value="currentTaskValue"
            :options="currentTaskOptions"
            :mode="isTargetEssenceMode ? 'multiple' : undefined"
            :disabled="optionControlsDisabled"
            :loading="normalizedSanityTaskType === 'Essence' && optionsLoading"
            size="middle"
            @change="handleTaskOptionChange"
          />
        </a-form-item>
      </a-col>
      <a-col v-if="showRewardGroupSelect" :xs="24" :sm="12">
        <a-form-item>
          <template #label>
            <a-tooltip :title="t('edit.rewardGroupsProtocolSpace')">
              <span class="form-label">
                {{ t('edit.rewardGroup') }}
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <div v-if="isPlanMode" class="plan-mode-display">
            <span>{{ displayRewardsSet }}</span>
            <span class="plan-source">{{ t('edit.fromPlan') }}</span>
          </div>
          <a-select
            v-else
            v-model:value="formData.Task.RewardsSetOption"
            :options="REWARD_OPTIONS"
            :disabled="optionControlsDisabled"
            size="middle"
            @change="emitSave('Task.RewardsSetOption', formData.Task.RewardsSetOption)"
          />
        </a-form-item>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, watch } from 'vue'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { ComboBoxItem } from '@/api'
import {
  PROTOCOL_SPACE_TASK_FIELD_MAP,
  PROTOCOL_SPACE_TASK_OPTIONS_MAP,
  PROTOCOL_SPACE_TASK_TITLE_MAP,
  PROTOCOL_SPACE_TASK_TOOLTIP_MAP,
  REWARD_OPTIONS,
  REWARD_LABEL_MAP,
  SANITY_TASK_TYPE_OPTIONS,
  SANITY_TASK_TYPE_LABEL_MAP,
  getSanityTaskDisplayValue,
  isProtocolSpaceRewardEnabled,
  normalizeMaaEndSanityConfig,
  AUTO_ESSENCE_MENU_OPTIONS,
  type AutoEssenceMenu,
  type MaaEndEssenceTargetGroup,
  type MaaEndSanityConfig,
  type ProtocolSpaceTab,
  type SanityTaskType,
} from '@/utils/maaEndProtocolSpace'

const { t } = useI18n()

interface FieldChange {
  key: string
  value: any
}

const props = withDefaults(
  defineProps<{
    formData: any
    loading?: boolean
    ifQuickConfig?: boolean
    essenceLocationOptions: ComboBoxItem[]
    essenceMenuOptions?: ComboBoxItem[]
    essenceTargetWeaponGroups?: MaaEndEssenceTargetGroup[]
    optionsLoading?: boolean
    optionsLoaded?: boolean
    isPlanMode?: boolean
    // 默认值不写在 withDefaults 里：defineProps 会被提升到 setup() 之外，
    // 引用不到 useI18n() 的 t。兜底见下方 resolvedSanityModeOptions。
    // oxlint-disable-next-line vue/require-default-prop
    sanityModeOptions?: Array<{ label: string; value: string }>
    planModeConfig?: MaaEndSanityConfig | null
  }>(),
  {
    loading: false,
    ifQuickConfig: true,
    optionsLoading: false,
    optionsLoaded: false,
    isPlanMode: false,
    essenceMenuOptions: () => [],
    essenceTargetWeaponGroups: () => [],
    planModeConfig: null,
  }
)

// 默认值不能写在 withDefaults 里：defineProps 会被提升到 setup() 之外，
// 引用不到 useI18n() 返回的 t，编译期直接报错。改成在这里兜底。
const resolvedSanityModeOptions = computed(
  () => props.sanityModeOptions ?? [{ label: t('edit.fixed'), value: 'Fixed' }]
)

const emit = defineEmits<{
  save: [key: string, value: any]
  saveBatch: [changes: FieldChange[]]
}>()

const formData = props.formData
const controlsDisabled = computed(() => {
  return props.loading || !props.ifQuickConfig
})

const optionControlsDisabled = computed(() => controlsDisabled.value || props.optionsLoading)
const displayPlanConfig = computed(() =>
  props.planModeConfig ? normalizeMaaEndSanityConfig(props.planModeConfig) : null
)
const displaySanityTaskType = computed(() =>
  displayPlanConfig.value
    ? SANITY_TASK_TYPE_LABEL_MAP[displayPlanConfig.value.SanityTaskType]
    : '未读取到计划表配置'
)
const displayCurrentTask = computed(() =>
  displayPlanConfig.value
    ? getSanityTaskDisplayValue(displayPlanConfig.value, props.essenceLocationOptions)
    : '未读取到计划表配置'
)
const displayEssenceMenu = computed(() => {
  if (!displayPlanConfig.value || displayPlanConfig.value.SanityTaskType !== 'Essence') {
    return '未读取到计划表配置'
  }
  return (
    resolvedEssenceMenuOptions.value.find(
      option => option.value === displayPlanConfig.value?.AutoEssenceMenu
    )?.label ?? displayPlanConfig.value.AutoEssenceMenu
  )
})
const displayRewardsSet = computed(() =>
  displayPlanConfig.value
    ? REWARD_LABEL_MAP[displayPlanConfig.value.RewardsSetOption]
    : '未读取到计划表配置'
)

const sanityTaskTypeOptions = computed(() =>
  SANITY_TASK_TYPE_OPTIONS.filter(
    option =>
      option.value !== 'Essence' ||
      !props.optionsLoaded ||
      props.essenceLocationOptions.length > 0 ||
      props.essenceTargetWeaponGroups.length > 0
  )
)

const resolvedEssenceMenuOptions = computed(() => {
  if (props.essenceMenuOptions.length) return props.essenceMenuOptions
  // 旧版 MaaEnd 没有 AutoEssenceMenu；只暴露 MAS 原有的指定地点语义。
  if (props.optionsLoaded) return [{ label: '指定地点', value: 'Location' }]
  return AUTO_ESSENCE_MENU_OPTIONS.map(option => ({
    label: option.label,
    value: option.value,
  }))
})

const essenceTargetWeaponOptions = computed<ComboBoxItem[]>(() => {
  const options = props.essenceTargetWeaponGroups.flatMap(group =>
    group.options.map(option => ({
      label: `${group.label} · ${option.label}`,
      value: option.value,
    }))
  )
  const values = new Set(options.map(option => option.value))
  const selected = Array.isArray(formData.Task.AutoEssenceTargetWeapons)
    ? formData.Task.AutoEssenceTargetWeapons
    : []
  for (const value of selected) {
    if (typeof value === 'string' && value && !values.has(value)) {
      options.unshift({ label: value, value })
    }
  }
  return options
})

const effectiveEssenceMenu = computed<AutoEssenceMenu>(() => {
  const value = displayPlanConfig.value?.AutoEssenceMenu ?? formData.Task.AutoEssenceMenu
  return resolvedEssenceMenuOptions.value.some(option => option.value === value)
    ? value
    : 'Location'
})
const isTargetEssenceMode = computed(
  () => normalizedSanityTaskType.value === 'Essence' && effectiveEssenceMenu.value === 'Target'
)

const normalizedSanityTaskType = computed<SanityTaskType>(() =>
  sanityTaskTypeOptions.value.some(option => option.value === formData.Task.SanityTaskType)
    ? formData.Task.SanityTaskType
    : 'OperatorProgression'
)

const effectiveSanityTaskType = computed<SanityTaskType>(
  () => displayPlanConfig.value?.SanityTaskType ?? normalizedSanityTaskType.value
)

const currentField = computed(
  () => PROTOCOL_SPACE_TASK_FIELD_MAP[normalizedSanityTaskType.value as ProtocolSpaceTab]
)
const currentTaskSaveKey = computed(() =>
  normalizedSanityTaskType.value === 'Essence'
    ? isTargetEssenceMode.value
      ? 'Task.AutoEssenceTargetWeapons'
      : 'Task.AutoEssenceSpecifiedLocation'
    : `Task.${currentField.value}`
)

const currentTaskOptions = computed(() => {
  if (normalizedSanityTaskType.value === 'Essence') {
    return isTargetEssenceMode.value
      ? essenceTargetWeaponOptions.value
      : props.essenceLocationOptions
  }
  return PROTOCOL_SPACE_TASK_OPTIONS_MAP[normalizedSanityTaskType.value as ProtocolSpaceTab] ?? []
})

const currentTaskValue = computed({
  get: () => {
    if (normalizedSanityTaskType.value === 'Essence') {
      return isTargetEssenceMode.value
        ? formData.Task.AutoEssenceTargetWeapons
        : formData.Task.AutoEssenceSpecifiedLocation
    }
    return formData.Task[currentField.value]
  },
  set: value => {
    if (normalizedSanityTaskType.value === 'Essence') {
      if (isTargetEssenceMode.value) {
        formData.Task.AutoEssenceTargetWeapons = Array.isArray(value) ? value : []
      } else {
        formData.Task.AutoEssenceSpecifiedLocation = value
      }
      return
    }
    formData.Task[currentField.value] = value
  },
})

const currentTaskOption = computed(() =>
  currentTaskOptions.value.find(option => option.value === currentTaskValue.value)
)

const rewardGroupEnabled = computed(() => {
  if (normalizedSanityTaskType.value === 'Essence') return false
  return Boolean(
    currentTaskOption.value &&
    'rewards' in currentTaskOption.value &&
    currentTaskOption.value.rewards
  )
})

const taskOptionLabel = computed(() =>
  effectiveSanityTaskType.value === 'Essence'
    ? effectiveEssenceMenu.value === 'Target'
      ? '目标武器'
      : '基质地点'
    : (PROTOCOL_SPACE_TASK_TITLE_MAP[effectiveSanityTaskType.value as ProtocolSpaceTab] ??
      '协议空间任务')
)

const taskOptionTooltip = computed(() =>
  effectiveSanityTaskType.value === 'Essence'
    ? effectiveEssenceMenu.value === 'Target'
      ? '选择需要刷取的目标武器，留空表示不限制武器'
      : '选择当前基质刷取地点'
    : (PROTOCOL_SPACE_TASK_TOOLTIP_MAP[effectiveSanityTaskType.value as ProtocolSpaceTab] ??
      '选择当前协议空间任务')
)

const emitSave = (key: string, value: any) => {
  if (controlsDisabled.value) return
  emit('save', key, value)
}

const handleEssenceMenuChange = (value: AutoEssenceMenu) => {
  if (optionControlsDisabled.value) return
  const normalized = AUTO_ESSENCE_MENU_OPTIONS.some(option => option.value === value)
    ? value
    : 'Location'
  formData.Task.AutoEssenceMenu = normalized
  const taskValueChange = ensureCurrentTaskValue()
  emitSaveBatch([
    { key: 'Task.AutoEssenceMenu', value: normalized },
    ...(taskValueChange ? [taskValueChange] : []),
  ])
}

const showSanityDetail = computed(() => props.ifQuickConfig && formData.Task.IfSanity)
const showRewardGroupSelect = computed(
  () =>
    showSanityDetail.value &&
    (displayPlanConfig.value
      ? displayPlanConfig.value.SanityTaskType !== 'Essence' &&
        isProtocolSpaceRewardEnabled(displayPlanConfig.value)
      : rewardGroupEnabled.value)
)

const emitSaveBatch = (changes: FieldChange[]) => {
  if (controlsDisabled.value || !changes.length) return
  emit('saveBatch', changes)
}

const ensureCurrentTaskValue = (): FieldChange | null => {
  if (optionControlsDisabled.value) return null
  const options = currentTaskOptions.value
  if (!options.length) return null
  if (isTargetEssenceMode.value) {
    const selected = Array.isArray(currentTaskValue.value) ? currentTaskValue.value : []
    const validValues = new Set(options.map(option => option.value).filter(Boolean))
    const normalized = selected.filter(
      (value: unknown): value is string => typeof value === 'string' && validValues.has(value)
    )
    if (JSON.stringify(normalized) === JSON.stringify(selected)) return null
    currentTaskValue.value = normalized
    return { key: currentTaskSaveKey.value, value: normalized }
  }
  if (options.some(option => option.value === currentTaskValue.value)) return null

  currentTaskValue.value = options[0].value
  return { key: currentTaskSaveKey.value, value: currentTaskValue.value }
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
  const taskValueChange = ensureCurrentTaskValue()

  const changes: FieldChange[] = [
    { key: 'Task.SanityTaskType', value: formData.Task.SanityTaskType },
    taskValueChange ?? { key: currentTaskSaveKey.value, value: currentTaskValue.value },
  ]

  const rewardGroupChange = normalizeRewardGroupState()
  if (rewardGroupChange) {
    changes.push(rewardGroupChange)
  }

  emitSaveBatch(changes)
}

const handleTaskOptionChange = () => {
  if (optionControlsDisabled.value) return
  const changes: FieldChange[] = [{ key: currentTaskSaveKey.value, value: currentTaskValue.value }]

  const rewardGroupChange = normalizeRewardGroupState()
  if (rewardGroupChange) {
    changes.push(rewardGroupChange)
  }

  emitSaveBatch(changes)
}

watch(
  [
    () => props.loading,
    () => props.optionsLoading,
    () => formData.Task.SanityTaskType,
    () => props.essenceLocationOptions,
    () => props.essenceMenuOptions,
    () => props.essenceTargetWeaponGroups,
    () => formData.Task.AutoEssenceMenu,
  ],
  () => {
    if (optionControlsDisabled.value) return
    const changes: FieldChange[] = []
    if (formData.Task.SanityTaskType !== normalizedSanityTaskType.value) {
      formData.Task.SanityTaskType = normalizedSanityTaskType.value
      changes.push({ key: 'Task.SanityTaskType', value: formData.Task.SanityTaskType })
    }
    const taskValueChange = ensureCurrentTaskValue()
    if (taskValueChange) {
      changes.push(taskValueChange)
    }
    const rewardGroupChange = normalizeRewardGroupState()
    if (rewardGroupChange) {
      changes.push(rewardGroupChange)
    }
    if (changes.length) {
      emitSaveBatch(changes)
    }
  },
  { immediate: true }
)
</script>

<style scoped>
.sanity-task-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 44px;
}

.sanity-task-enabled {
  margin-bottom: 24px;
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

.plan-source {
  flex-shrink: 0;
  color: var(--ant-color-primary);
  font-size: 12px;
}

.form-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 500;
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
