<!-- eslint-disable vue/no-mutating-props -->
<template>
  <div class="form-section">
    <div class="section-header">
      <h3>任务配置</h3>
    </div>

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

    <a-row v-if="showSanityDetail" :gutter="24">
      <a-col :span="optionColumnSpan">
        <a-form-item>
          <template #label>
            <a-tooltip title="选择当前执行的理智任务类型">
              <span class="form-label">
                理智任务
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select
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
    </a-row>

    <a-row v-if="showRewardGroupSelect" :gutter="24">
      <a-col :span="8">
        <a-form-item>
          <template #label>
            <a-tooltip title="协议空间奖励任务可在这里选择奖励组">
              <span class="form-label">
                可选奖励组
                <QuestionCircleOutlined class="help-icon" />
              </span>
            </a-tooltip>
          </template>
          <a-select
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
import { computed, ref, watch } from 'vue'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import {
  AUTO_ESSENCE_LOCATION_OPTIONS,
  MAAEND_CONTROLLER_TASKS,
  MAAEND_TASK_GROUPS,
  PROTOCOL_SPACE_TASK_FIELD_MAP,
  PROTOCOL_SPACE_TASK_OPTIONS_MAP,
  PROTOCOL_SPACE_TASK_TITLE_MAP,
  PROTOCOL_SPACE_TASK_TOOLTIP_MAP,
  REWARD_OPTIONS,
  SANITY_TASK_TYPE_OPTIONS,
  type MaaEndTaskSwitch,
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
    ifQuickConfig?: boolean
    controllerType?: string | null
  }>(),
  {
    loading: false,
    ifQuickConfig: true,
    controllerType: null,
  }
)

const emit = defineEmits<{
  save: [key: string, value: any]
  saveBatch: [changes: FieldChange[]]
}>()

const formData = props.formData
const optionColumnSpan = 12
const activeGroupKey = ref('')
const showManagedTaskConfig = computed(() => props.ifQuickConfig)
const supportedTaskNames = computed(
  () => new Set(MAAEND_CONTROLLER_TASKS[props.controllerType ?? ''] ?? [])
)
const showSanityOptions = computed(() => supportedTaskNames.value.has('Sanity'))
const visibleTaskGroups = computed(() =>
  MAAEND_TASK_GROUPS.map(group => ({
    ...group,
    tasks: group.tasks.filter(task => supportedTaskNames.value.has(task.name)),
  })).filter(group => group.tasks.length > 0)
)
const activeGroup = computed(
  () => visibleTaskGroups.value.find(group => group.key === activeGroupKey.value) ?? null
)
const activeGroupHasSanity = computed(
  () => activeGroup.value?.tasks.some(task => task.name === 'Sanity') ?? false
)

const controlsDisabled = computed(() => {
  return props.loading || !props.ifQuickConfig
})

const optionControlsDisabled = computed(() => controlsDisabled.value)

const normalizedSanityTaskType = computed<SanityTaskType>(() =>
  SANITY_TASK_TYPE_OPTIONS.some(option => option.value === formData.Task.SanityTaskType)
    ? formData.Task.SanityTaskType
    : 'OperatorProgression'
)

const currentField = computed(
  () => PROTOCOL_SPACE_TASK_FIELD_MAP[normalizedSanityTaskType.value as ProtocolSpaceTab]
)

const currentTaskOptions = computed(() => {
  if (normalizedSanityTaskType.value === 'Essence') {
    return AUTO_ESSENCE_LOCATION_OPTIONS
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
  normalizedSanityTaskType.value === 'Essence'
    ? '基质地点'
    : (PROTOCOL_SPACE_TASK_TITLE_MAP[normalizedSanityTaskType.value as ProtocolSpaceTab] ??
      '协议空间任务')
)

const taskOptionTooltip = computed(() =>
  normalizedSanityTaskType.value === 'Essence'
    ? '选择当前基质刷取地点'
    : (PROTOCOL_SPACE_TASK_TOOLTIP_MAP[normalizedSanityTaskType.value as ProtocolSpaceTab] ??
      '选择当前协议空间任务')
)

const emitSave = (key: string, value: any) => {
  if (controlsDisabled.value) return
  emit('save', key, value)
}

const taskSwitchKey = (taskName: MaaEndTaskSwitch) => `If${taskName}` as const

const isTaskEnabled = (taskName: MaaEndTaskSwitch) =>
  Boolean(formData.Task[taskSwitchKey(taskName)])

const showSanityDetail = computed(
  () =>
    props.ifQuickConfig &&
    activeGroupHasSanity.value &&
    showSanityOptions.value &&
    isTaskEnabled('Sanity')
)
const showRewardGroupSelect = computed(() => showSanityDetail.value && rewardGroupEnabled.value)

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

const ensureCurrentTaskValue = () => {
  if (optionControlsDisabled.value) return
  const options = currentTaskOptions.value
  if (!options.length) return
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

  if (normalizedSanityTaskType.value === 'Essence') {
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
    if (optionControlsDisabled.value) return
    const changes: FieldChange[] = []
    if (formData.Task.SanityTaskType !== normalizedSanityTaskType.value) {
      formData.Task.SanityTaskType = normalizedSanityTaskType.value
      changes.push({ key: 'Task.SanityTaskType', value: formData.Task.SanityTaskType })
    }
    ensureCurrentTaskValue()
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

.task-switch-layout {
  display: grid;
  grid-template-columns: minmax(240px, 300px) minmax(360px, 1fr);
  gap: 24px;
  margin-bottom: 20px;
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
