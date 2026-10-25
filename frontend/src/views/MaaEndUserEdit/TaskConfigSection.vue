<template>
  <div v-if="showManagedTaskConfig" class="task-config-section">
    <div class="task-editor-layout">
      <div class="task-list-column">
        <div class="column-header">{{ t('edit.maaEndTaskGroups') }}</div>
        <div class="task-group-list" :aria-label="t('edit.maaEndTaskGroups')" role="group">
          <button
            v-for="group in visibleTaskGroups"
            :key="group.key"
            type="button"
            class="task-group-row"
            :class="{ 'task-group-selected': selectedGroup.key === group.key }"
            :aria-pressed="selectedGroup.key === group.key"
            @click="selectedGroupKey = group.key"
          >
            <span class="task-title">{{ group.label }}</span>
            <span class="group-count">
              {{ enabledGroupTaskCount(group) }} / {{ group.tasks.length }}
            </span>
          </button>
        </div>
      </div>
      <div class="task-option-column">
        <div class="column-header">
          <span>{{ selectedGroup.label }}</span>
          <a-tooltip :title="t('edit.maaEndEnableGroup')">
            <a-switch
              v-if="selectedGroup.tasks.length > 1"
              size="small"
              :checked="isGroupEnabled(selectedGroup)"
              :disabled="controlsDisabled"
              :aria-label="`${taskLabel(selectedGroup.label)} ${t('edit.maaEndEnableGroup')}`"
              @change="handleGroupSwitchChange(selectedGroup, $event)"
            />
          </a-tooltip>
        </div>
        <div class="task-option-panel">
          <button
            v-for="task in selectedGroup.tasks"
            :key="task.name"
            type="button"
            role="switch"
            class="task-row"
            :class="{ 'task-row-skipped': !isTaskEnabled(task.name) }"
            :aria-label="taskLabel(task.label)"
            :aria-checked="isTaskEnabled(task.name)"
            :disabled="controlsDisabled"
            @click="handleTaskSwitchChange(task.name)"
          >
            <span class="task-title">{{ task.label }}</span>
            <a-tooltip
              :title="t(isTaskEnabled(task.name) ? 'edit.queueTaskRuns' : 'edit.queueTaskSkipped')"
            >
              <span class="task-lamp-area" aria-hidden="true">
                <span class="task-lamp" />
              </span>
            </a-tooltip>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, ref } from 'vue'
import type { MaaEndUserForm } from './userDefaults'
import { MAAEND_TASK_GROUPS, type MaaEndTaskSwitch } from '@/utils/maaEndProtocolSpace'

const { t } = useI18n()

interface FieldChange {
  key: string
  value: boolean
}

const props = withDefaults(
  defineProps<{
    formData: MaaEndUserForm
    loading?: boolean
    ifQuickConfig?: boolean
  }>(),
  {
    loading: false,
    ifQuickConfig: true,
  }
)

const emit = defineEmits<{
  save: [key: string, value: boolean]
  saveBatch: [changes: FieldChange[]]
}>()

const showManagedTaskConfig = computed(() => props.ifQuickConfig)
const visibleTaskGroups = computed(() => MAAEND_TASK_GROUPS.filter(group => group.key !== 'Sanity'))
const selectedGroupKey = ref<(typeof visibleTaskGroups.value)[number]['key']>('Infrastructure')
const selectedGroup = computed(
  () =>
    visibleTaskGroups.value.find(group => group.key === selectedGroupKey.value) ??
    visibleTaskGroups.value[0]
)
const controlsDisabled = computed(() => props.loading || !props.ifQuickConfig)

const emitSave = (key: string, value: boolean) => {
  if (controlsDisabled.value) return
  emit('save', key, value)
}

const taskSwitchKey = (taskName: MaaEndTaskSwitch) => `If${taskName}` as const

const isTaskEnabled = (taskName: MaaEndTaskSwitch) =>
  Boolean(props.formData.Task[taskSwitchKey(taskName)])

const handleTaskSwitchChange = (taskName: MaaEndTaskSwitch) => {
  if (controlsDisabled.value) return
  const key = taskSwitchKey(taskName)
  props.formData.Task[key] = !props.formData.Task[key]
  emitSave(`Task.${key}`, props.formData.Task[key])
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
    props.formData.Task[key] = enabled
    return { key: `Task.${key}`, value: enabled }
  })
  emitSaveBatch(changes)
}

const emitSaveBatch = (changes: FieldChange[]) => {
  if (controlsDisabled.value || !changes.length) return
  emit('saveBatch', changes)
}

const taskLabel = (label: string) => label.slice(label.indexOf(' ') + 1)
</script>

<style scoped>
.task-config-section {
  container-type: inline-size;
  margin-bottom: 16px;
}
.task-editor-layout {
  display: grid;
  grid-template-columns: 184px minmax(0, 1fr);
  align-items: start;
  gap: 16px;
}
.task-list-column,
.task-option-column {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.column-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  min-height: 24px;
  margin-bottom: 8px;
  color: var(--ant-color-text);
  font-size: 14px;
  font-weight: 600;
}
.task-group-list {
  overflow: hidden;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
}
.task-option-panel {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}
.group-count {
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 400;
  color: var(--ant-color-text-tertiary);
  font-variant-numeric: tabular-nums;
}
.task-group-row,
.task-row {
  width: 100%;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  min-height: 44px;
  padding: 6px 12px;
  border: none;
  border-bottom: 1px solid var(--ant-color-border-secondary);
  background: var(--ant-color-bg-container);
  color: var(--ant-color-text);
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: background-color 0.2s ease;
}
.task-group-row {
  min-height: 56px;
}
.task-group-row:last-child {
  border-bottom: none;
}
.task-row {
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
}
.task-group-row:hover,
.task-row:hover:not(:disabled) {
  background: var(--ant-color-fill-quaternary);
}
.task-group-selected,
.task-group-selected:hover {
  padding-left: 9px;
  border-left: 3px solid var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
}
.task-title {
  min-width: 0;
  overflow-wrap: anywhere;
  font-weight: 600;
}
.task-row .task-title {
  font-weight: 400;
}
.task-row-skipped .task-title {
  color: var(--ant-color-text-tertiary);
}
.task-row:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}
.task-group-row:focus-visible,
.task-row:focus-visible {
  outline: 2px solid var(--ant-color-primary);
  outline-offset: -2px;
}
.task-lamp-area {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 24px;
  height: 24px;
}
.task-lamp {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--ant-color-success);
}
.task-row-skipped .task-lamp {
  background: var(--ant-color-fill-secondary);
}
@container (max-width: 1200px) {
  .task-option-panel {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
@container (max-width: 960px) {
  .task-option-panel {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@container (max-width: 640px) {
  .task-editor-layout {
    grid-template-columns: minmax(0, 1fr);
    gap: 16px;
  }
  .task-group-list {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@container (max-width: 420px) {
  .task-option-panel {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
