<template>
  <div>
    <div v-if="showManagedTaskConfig && visibleTaskGroups.length" class="task-switch-layout">
      <a-tabs v-model:active-key="activeGroupKey" size="small">
        <a-tab-pane v-for="group in visibleTaskGroups" :key="group.key">
          <template #tab>
            <span>{{ group.label }}</span>
            <span class="task-group-count"
              >{{ enabledGroupTaskCount(group) }}/{{ group.tasks.length }}</span
            >
          </template>
        </a-tab-pane>
      </a-tabs>

      <div v-if="activeGroup" class="task-group-detail">
        <div class="task-group-detail-header">
          <span>{{
            t('edit.maaEndGroupEnabled', {
              n: enabledGroupTaskCount(activeGroup),
              m: activeGroup.tasks.length,
            })
          }}</span>
          <label v-if="activeGroup.tasks.length > 1" class="task-group-toggle">
            <span>{{ t('edit.maaEndEnableGroup') }}</span>
            <a-switch
              :checked="isGroupEnabled(activeGroup)"
              :disabled="controlsDisabled"
              :aria-label="t('edit.maaEndEnableGroup')"
              @change="handleGroupSwitchChange(activeGroup, $event)"
            />
          </label>
        </div>

        <div class="task-switch-list">
          <div v-for="task in activeGroup.tasks" :key="task.name" class="task-switch-row">
            <span class="task-switch-label">{{ task.label }}</span>
            <a-switch
              v-model:checked="formData.Task[taskSwitchKey(task.name)]"
              :disabled="controlsDisabled"
              :aria-label="task.label"
              @change="handleTaskSwitchChange(task.name)"
            />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, ref, watch } from 'vue'
import { MAAEND_TASK_GROUPS, type MaaEndTaskSwitch } from '@/utils/maaEndProtocolSpace'

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
  }>(),
  {
    loading: false,
    ifQuickConfig: true,
  }
)

const emit = defineEmits<{
  save: [key: string, value: any]
  saveBatch: [changes: FieldChange[]]
}>()

const formData = props.formData
const activeGroupKey = ref('')
const showManagedTaskConfig = computed(() => props.ifQuickConfig)
const visibleTaskGroups = computed(() => MAAEND_TASK_GROUPS.filter(group => group.key !== 'Sanity'))
const activeGroup = computed(
  () => visibleTaskGroups.value.find(group => group.key === activeGroupKey.value) ?? null
)
const controlsDisabled = computed(() => props.loading || !props.ifQuickConfig)

const emitSave = (key: string, value: any) => {
  if (controlsDisabled.value) return
  emit('save', key, value)
}

const taskSwitchKey = (taskName: MaaEndTaskSwitch) => `If${taskName}` as const

const isTaskEnabled = (taskName: MaaEndTaskSwitch) =>
  Boolean(formData.Task[taskSwitchKey(taskName)])

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
  min-width: 0;
}

.task-group-count {
  margin-inline-start: 8px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}

.task-group-detail-header,
.task-group-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
}

.task-group-detail-header {
  justify-content: space-between;
  flex-wrap: wrap;
  margin-bottom: 8px;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
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

@media (max-width: 600px) {
  .task-switch-list {
    grid-template-columns: 1fr;
  }
}
</style>
