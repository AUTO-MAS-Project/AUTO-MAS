<template>
  <div>
    <div v-if="showManagedTaskConfig && visibleTaskGroups.length" class="task-switch-layout">
      <div class="task-group-sidebar">
        <button
          v-for="group in visibleTaskGroups"
          :key="group.key"
          class="task-group-item"
          :class="{ active: group.key === activeGroupKey }"
          type="button"
          @click="activeGroupKey = group.key"
        >
          <span class="task-group-main">
            <span class="task-group-title">{{ group.label }}</span>
            <span class="task-group-count">
              {{ enabledGroupTaskCount(group) }}/{{ group.tasks.length }}
            </span>
          </span>
          <span class="task-group-switch" @click.stop>
            <a-switch
              :checked="isGroupEnabled(group)"
              :disabled="controlsDisabled"
              size="small"
              @change="handleGroupSwitchChange(group, $event)"
            />
          </span>
        </button>
      </div>

      <div v-if="activeGroup" class="task-group-detail">
        <div class="task-group-detail-header">
          <span>{{ activeGroup.label }}</span>
          <span class="task-group-count">
            {{ enabledGroupTaskCount(activeGroup) }}/{{ activeGroup.tasks.length }}
          </span>
        </div>

        <div class="task-switch-list">
          <div v-for="task in activeGroup.tasks" :key="task.name" class="task-switch-row">
            <span class="task-switch-label">{{ task.label }}</span>
            <a-switch
              v-model:checked="formData.Task[taskSwitchKey(task.name)]"
              :disabled="controlsDisabled"
              @change="handleTaskSwitchChange(task.name)"
            />
          </div>
        </div>
      </div>
    </div>

    <a-row :gutter="24" class="daily-once-row">
      <a-col :span="8">
        <a-form-item>
          <template #label>
            <a-tooltip :title="t('edit.maaEndDailyOnceTasksHint')">
              <span class="form-label">
                {{ t('edit.maaEndDailyOnceTasks') }}
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            :value="dailyOnceTaskValues"
            mode="multiple"
            size="large"
            :options="dailyOnceTaskOptions"
            :disabled="props.loading"
            option-filter-prop="label"
            show-search
            :max-tag-count="'responsive'"
            :placeholder="t('edit.maaEndDailyOnceTasksPlaceholder')"
            @change="handleDailyOnceTasksChange"
          />
        </a-form-item>
      </a-col>
    </a-row>

    <a-row v-if="showSanityDetail" :gutter="24">
      <a-col :span="optionColumnSpan">
        <a-form-item :label="t('edit.sanityTaskConfigurationMode')">
          <a-select
            v-model:value="formData.Info.SanityMode"
            :options="resolvedSanityModeOptions"
            :disabled="loading"
            size="large"
            @change="emitSave('Info.SanityMode', formData.Info.SanityMode)"
          />
        </a-form-item>
      </a-col>

      <a-col :span="optionColumnSpan">
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
            size="large"
            @change="handleSanityTaskTypeChange"
          />
        </a-form-item>
      </a-col>

      <a-col :span="optionColumnSpan">
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
            :disabled="optionControlsDisabled"
            :loading="normalizedSanityTaskType === 'Essence' && optionsLoading"
            size="large"
            @change="handleTaskOptionChange"
          />
        </a-form-item>
      </a-col>
    </a-row>

    <a-row v-if="showRewardGroupSelect" :gutter="24">
      <a-col :span="8">
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
            size="large"
            @change="emitSave('Task.RewardsSetOption', formData.Task.RewardsSetOption)"
          />
        </a-form-item>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, ref, watch } from 'vue'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { ComboBoxItem } from '@/api'
import {
  MAAEND_TASK_GROUPS,
  MAAEND_DAILY_ONCE_TASK_OPTIONS,
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
  type MaaEndSanityConfig,
  type MaaEndTaskSwitch,
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
const optionColumnSpan = 8
const activeGroupKey = ref('')
const showManagedTaskConfig = computed(() => props.ifQuickConfig)
const visibleTaskGroups = computed(() => MAAEND_TASK_GROUPS)
const activeGroup = computed(
  () => visibleTaskGroups.value.find(group => group.key === activeGroupKey.value) ?? null
)
const activeGroupHasSanity = computed(
  () => activeGroup.value?.tasks.some(task => task.name === 'Sanity') ?? false
)

const controlsDisabled = computed(() => {
  return props.loading || !props.ifQuickConfig
})

const optionControlsDisabled = computed(() => controlsDisabled.value || props.optionsLoading)
const dailyOnceTaskValues = computed(() => {
  const value = formData.Task.DailyOnceTasks
  if (Array.isArray(value)) {
    return value.filter((item: unknown): item is string => typeof item === 'string')
  }
  if (typeof value === 'string' && value.trim()) {
    try {
      const parsed: unknown = JSON.parse(value)
      return Array.isArray(parsed)
        ? parsed.filter((item): item is string => typeof item === 'string')
        : []
    } catch {
      return []
    }
  }
  return []
})
const dailyOnceTaskOptions = MAAEND_DAILY_ONCE_TASK_OPTIONS.map(task => ({
  label: task.label,
  value: task.name,
}))
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
const displayRewardsSet = computed(() =>
  displayPlanConfig.value
    ? REWARD_LABEL_MAP[displayPlanConfig.value.RewardsSetOption]
    : '未读取到计划表配置'
)

const sanityTaskTypeOptions = computed(() =>
  SANITY_TASK_TYPE_OPTIONS.filter(
    option =>
      option.value !== 'Essence' || !props.optionsLoaded || props.essenceLocationOptions.length > 0
  )
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
    ? 'Task.AutoEssenceSpecifiedLocation'
    : `Task.${currentField.value}`
)

const currentTaskOptions = computed(() => {
  if (normalizedSanityTaskType.value === 'Essence') {
    return props.essenceLocationOptions
  }
  return PROTOCOL_SPACE_TASK_OPTIONS_MAP[normalizedSanityTaskType.value as ProtocolSpaceTab] ?? []
})

const currentTaskValue = computed({
  get: () => {
    if (normalizedSanityTaskType.value === 'Essence') {
      return formData.Task.AutoEssenceSpecifiedLocation
    }
    return formData.Task[currentField.value]
  },
  set: value => {
    if (normalizedSanityTaskType.value === 'Essence') {
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
  if (normalizedSanityTaskType.value === 'Essence') return false
  return Boolean(
    currentTaskOption.value &&
    'rewards' in currentTaskOption.value &&
    currentTaskOption.value.rewards
  )
})

const taskOptionLabel = computed(() =>
  effectiveSanityTaskType.value === 'Essence'
    ? '基质地点'
    : (PROTOCOL_SPACE_TASK_TITLE_MAP[effectiveSanityTaskType.value as ProtocolSpaceTab] ??
      '协议空间任务')
)

const taskOptionTooltip = computed(() =>
  effectiveSanityTaskType.value === 'Essence'
    ? '选择当前基质刷取地点'
    : (PROTOCOL_SPACE_TASK_TOOLTIP_MAP[effectiveSanityTaskType.value as ProtocolSpaceTab] ??
      '选择当前协议空间任务')
)

const emitSave = (key: string, value: any) => {
  if (controlsDisabled.value) return
  emit('save', key, value)
}

const handleDailyOnceTasksChange = (values: string[]) => {
  if (props.loading) return
  const normalized = Array.from(new Set(values.filter(Boolean)))
  const serialized = JSON.stringify(normalized)
  formData.Task.DailyOnceTasks = serialized
  // 非快速配置同样开放此用户级选项，不能走仅允许快速配置任务开关的 emitSave。
  emit('save', 'Task.DailyOnceTasks', serialized)
}

const taskSwitchKey = (taskName: MaaEndTaskSwitch) => `If${taskName}` as const

const isTaskEnabled = (taskName: MaaEndTaskSwitch) =>
  Boolean(formData.Task[taskSwitchKey(taskName)])

const showSanityDetail = computed(
  () => props.ifQuickConfig && activeGroupHasSanity.value && isTaskEnabled('Sanity')
)
const showRewardGroupSelect = computed(
  () =>
    showSanityDetail.value &&
    (displayPlanConfig.value
      ? displayPlanConfig.value.SanityTaskType !== 'Essence' &&
        isProtocolSpaceRewardEnabled(displayPlanConfig.value)
      : rewardGroupEnabled.value)
)

const handleTaskSwitchChange = (taskName: MaaEndTaskSwitch) => {
  emitSave(`Task.${taskSwitchKey(taskName)}`, formData.Task[taskSwitchKey(taskName)])
}

const enabledGroupTaskCount = (group: (typeof visibleTaskGroups.value)[number]) =>
  group.tasks.filter(task => isTaskEnabled(task.name)).length

const isGroupEnabled = (group: (typeof visibleTaskGroups.value)[number]) =>
  enabledGroupTaskCount(group) === group.tasks.length

const handleGroupSwitchChange = (
  group: (typeof visibleTaskGroups.value)[number],
  checked: boolean | string | number
) => {
  if (controlsDisabled.value) return
  const enabled = Boolean(checked)
  const changes = group.tasks.map(task => {
    const key = taskSwitchKey(task.name)
    formData.Task[key] = enabled
    return { key: `Task.${key}`, value: enabled }
  })
  emitSaveBatch(changes)
}

const emitSaveBatch = (changes: FieldChange[]) => {
  if (controlsDisabled.value || !changes.length) return
  emit('saveBatch', changes)
}

const ensureCurrentTaskValue = (): FieldChange | null => {
  if (optionControlsDisabled.value) return null
  const options = currentTaskOptions.value
  if (!options.length) return null
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

watch(
  visibleTaskGroups,
  groups => {
    if (!groups.length) {
      activeGroupKey.value = ''
      return
    }
    if (!groups.some(group => group.key === activeGroupKey.value)) {
      activeGroupKey.value = groups[0].key
    }
  },
  { immediate: true }
)
</script>

<style scoped>
.task-switch-layout {
  display: grid;
  grid-template-columns: minmax(240px, 300px) minmax(360px, 1fr);
  gap: 24px;
  margin-bottom: 20px;
}

.daily-once-row :deep(.ant-select) {
  width: 100%;
}

.task-group-sidebar {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.task-group-item {
  width: 100%;
  min-height: 52px;
  padding: 10px 12px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
  color: var(--ant-color-text);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  text-align: left;
  transition:
    border-color 0.2s ease,
    background 0.2s ease;
}

.task-group-item.active {
  border-color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
}

.task-group-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.task-group-title {
  font-size: 14px;
  font-weight: 600;
}

.task-group-count {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

.task-group-detail {
  min-height: 220px;
  padding: 4px 0;
}

.task-group-detail-header {
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: var(--ant-color-text);
  font-size: 15px;
  font-weight: 600;
}

.task-switch-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 10px 20px;
}

.task-switch-row {
  min-height: 44px;
  padding: 8px 0;
  border-bottom: 1px solid var(--ant-color-border-secondary);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.task-switch-label {
  color: var(--ant-color-text);
  font-size: 14px;
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

@media (max-width: 900px) {
  .task-switch-layout {
    grid-template-columns: 1fr;
  }

  .task-group-sidebar {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .task-switch-list {
    grid-template-columns: 1fr;
  }
}
</style>
