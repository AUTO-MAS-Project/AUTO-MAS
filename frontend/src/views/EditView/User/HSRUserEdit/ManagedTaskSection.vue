<template>
  <div class="managed-task-section">
    <div class="section-header section-header-with-action">
      <h3>{{ t('edit.tasksManagedByMas') }}</h3>
      <div class="section-header-action">
        <a-typography-text type="secondary" class="reset-hint">
          {{ t('edit.resetManagedOverridesHint') }}
        </a-typography-text>
        <a-popconfirm
          :title="t('edit.resetManagedOverridesConfirmTitle')"
          :description="t('edit.resetManagedOverridesConfirmDesc')"
          :ok-text="t('edit.ok')"
          :cancel-text="t('edit.cancel')"
          ok-type="danger"
          :disabled="loading || saving"
          @confirm="emit('resetOverrides')"
        >
          <a-button danger :loading="loading" :disabled="saving">
            {{ t('edit.resetManagedOverrides') }}
          </a-button>
        </a-popconfirm>
      </div>
    </div>
    <a-alert
      v-for="warning in snapshot?.warnings || []"
      :key="warning"
      type="warning"
      show-icon
      :message="warning"
      class="snapshot-warning"
    />

    <a-spin :spinning="loading">
      <a-empty v-if="!snapshot && !loading" :description="t('edit.nativeTaskConfigurationHas')" />
      <a-row v-else-if="snapshot" :gutter="[24, 16]" class="task-editor-layout">
        <a-col :xs="24" :lg="12" class="task-list-column">
          <div class="column-header">
            <span>{{ t('edit.taskModule') }}</span>
            <a-typography-text type="secondary"
              >动态 {{ snapshot.tasks.length }} 项</a-typography-text
            >
          </div>
          <div class="task-list">
            <button
              v-for="task in snapshot.tasks"
              :key="task.key"
              type="button"
              class="task-row"
              :class="{ 'task-row-selected': selectedTaskKey === task.key }"
              @click="selectedTaskKey = task.key"
            >
              <div class="task-row-main">
                <div class="task-row-title">
                  <span>{{ task.name }}</span>
                  <a-tag color="default">{{ phaseLabel(task.phase) }}</a-tag>
                  <a-tag v-if="droppedOverridesOf(task).length" color="warning">
                    {{ t('edit.invalidOverridesCount', { n: droppedOverridesOf(task).length }) }}
                  </a-tag>
                </div>
                <div class="task-row-summary">{{ taskSummary(task) }}</div>
              </div>
              <div class="task-row-actions">
                <span @click.stop>
                  <a-switch
                    :checked="Boolean(taskSwitch[task.key])"
                    :disabled="saving"
                    size="small"
                    @change="emit('taskToggle', task.key, Boolean($event))"
                  />
                </span>
                <a-tag :color="engineColor(mappedEngine(task))">
                  {{ engineLabel(mappedEngine(task)) }}
                </a-tag>
                <RightOutlined aria-hidden="true" />
              </div>
            </button>
          </div>
        </a-col>

        <a-col :xs="24" :lg="12" class="task-option-column">
          <div class="column-header">
            <span>{{ t('edit.details') }}</span>
            <a-typography-text type="secondary">
              {{ selectedTask ? phaseLabel(selectedTask.phase) : '' }}
            </a-typography-text>
          </div>
          <div v-if="selectedTask" class="task-option-panel">
            <div class="selected-task-header">
              <div>
                <div class="selected-task-title">{{ selectedTask.name }}</div>
                <div class="selected-task-description">{{ selectedTask.description }}</div>
              </div>
              <a-tag :color="engineColor(selectedEngine)">{{ engineLabel(selectedEngine) }}</a-tag>
            </div>

            <a-form-item
              v-if="engineOptions.length > 1"
              :label="t('edit.engine')"
              :extra="t('edit.hsrEngineSwitchHint')"
            >
              <a-segmented
                :value="selectedEngine"
                :options="engineOptions"
                :disabled="saving"
                block
                @change="handleEngineChange"
              />
            </a-form-item>

            <a-alert
              v-if="!Boolean(taskSwitch[selectedTask.key])"
              type="info"
              show-icon
              :message="t('edit.thisModuleNotEnabled')"
              class="panel-alert"
            />

            <template v-if="selectedForm">
              <a-alert
                v-for="warning in selectedForm.warnings || []"
                :key="warning"
                type="warning"
                show-icon
                :message="warning"
                class="panel-alert"
              />
              <a-typography-text type="secondary" class="source-line">
                读取自：{{ selectedForm.source }}
              </a-typography-text>
              <a-alert
                v-if="selectedDroppedOverrides.length"
                type="warning"
                show-icon
                class="panel-alert"
                :message="
                  t('edit.invalidManagedOverridesTitle', { n: selectedDroppedOverrides.length })
                "
              >
                <template #description>
                  <ul class="dropped-list">
                    <li v-for="item in selectedDroppedOverrides" :key="item.key">
                      <code>{{ item.key }}</code>
                      <span>{{ droppedReasonLabel(item.reason) }}</span>
                      <span class="dropped-value">
                        {{
                          t('edit.invalidManagedOverrideSaved', {
                            value: formatOverrideValue(item.value),
                          })
                        }}
                      </span>
                    </li>
                  </ul>
                  <a-popconfirm
                    :title="
                      t('edit.clearInvalidManagedOverridesConfirm', {
                        n: selectedDroppedOverrides.length,
                      })
                    "
                    :ok-text="t('edit.ok')"
                    :cancel-text="t('edit.cancel')"
                    ok-type="danger"
                    :disabled="saving"
                    @confirm="handleClearInvalidOverrides"
                  >
                    <a-button size="small" danger :disabled="saving">
                      {{ t('edit.clearInvalidManagedOverrides') }}
                    </a-button>
                  </a-popconfirm>
                </template>
              </a-alert>
              <DynamicManagedFields
                :fields="selectedForm.fields"
                :disabled="saving"
                @change="handleFieldChange"
              />
            </template>
            <a-alert v-else type="warning" show-icon :message="t('edit.engineReturnedNoDynamic')" />
          </div>
          <div v-else class="task-option-empty">
            <a-empty :description="t('edit.nothingConfigure')" />
          </div>
        </a-col>
      </a-row>
    </a-spin>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, ref, watch } from 'vue'
import { RightOutlined } from '@ant-design/icons-vue'
import {
  getHSRDroppedOverrides,
  type HSRDroppedOverride,
  type HSRDroppedOverrideReason,
  type HSREngine,
  type HSRManagedConfigSnapshot,
  type HSRManagedTask,
} from '@/composables/useHSRPluginApi'
import DynamicManagedFields from './DynamicManagedFields.vue'

const { t } = useI18n()

const props = defineProps<{
  snapshot: HSRManagedConfigSnapshot | null
  taskSwitch: Record<string, boolean | null | undefined>
  saving: boolean
  loading: boolean
}>()

const emit = defineEmits<{
  /** 清空这个用户的全部 Managed.Options 覆盖值，重新按源配置读取。 */
  resetOverrides: []
  taskToggle: [task: string, enabled: boolean]
  mappingChange: [task: string, engine: HSREngine]
  fieldChange: [engine: HSREngine, task: string, key: string, value: unknown]
  /** 只从 Managed.Options 里剔掉后端报告为失效的键。 */
  clearInvalidOverrides: [engine: HSREngine, task: string, keys: string[]]
}>()

const selectedTaskKey = ref('')

watch(
  () => props.snapshot?.tasks,
  tasks => {
    if (!tasks?.length) {
      selectedTaskKey.value = ''
      return
    }
    if (!tasks.some(task => task.key === selectedTaskKey.value)) {
      selectedTaskKey.value = tasks[0].key
    }
  },
  { immediate: true }
)

const selectedTask = computed(
  () => props.snapshot?.tasks.find(task => task.key === selectedTaskKey.value) ?? null
)

const availableEngines = (task: HSRManagedTask): HSREngine[] =>
  task.engines.filter(engine => Boolean(task.forms?.[engine]))

const mappedEngine = (task: HSRManagedTask): HSREngine | undefined => {
  const configured = props.snapshot?.task_mapping?.[task.key]
  const available = availableEngines(task)
  if (configured && available.includes(configured)) return configured
  return available[0]
}

const selectedEngine = computed(() =>
  selectedTask.value ? mappedEngine(selectedTask.value) : undefined
)

const selectedForm = computed(() => {
  const task = selectedTask.value
  const engine = selectedEngine.value
  return task && engine ? task.forms?.[engine] : undefined
})

const droppedOverridesOf = (task: HSRManagedTask, engine = mappedEngine(task)) =>
  engine ? getHSRDroppedOverrides(task.forms?.[engine]) : []

const selectedDroppedOverrides = computed<HSRDroppedOverride[]>(() =>
  selectedTask.value ? droppedOverridesOf(selectedTask.value, selectedEngine.value) : []
)

const droppedReasonLabel = (reason: HSRDroppedOverrideReason) =>
  reason === 'type' ? t('edit.invalidManagedOverrideType') : t('edit.invalidManagedOverrideUnknown')

const formatOverrideValue = (value: unknown) =>
  typeof value === 'string' ? value : JSON.stringify(value)

const handleClearInvalidOverrides = () => {
  const task = selectedTask.value
  const engine = selectedEngine.value
  const keys = selectedDroppedOverrides.value.map(item => item.key)
  if (!task || !engine || keys.length === 0) return
  emit('clearInvalidOverrides', engine, task.key, keys)
}

const engineOptions = computed(() =>
  selectedTask.value
    ? availableEngines(selectedTask.value).map(engine => ({
        value: engine,
        label: engineLabel(engine),
      }))
    : []
)

const phaseLabel = (phase: string) => (phase === 'weekly' ? '周常' : '日常')
const engineLabel = (engine?: HSREngine) =>
  engine === 'M7A' ? '三月七' : engine === 'SRA' ? 'SRA' : '不可用'
const engineColor = (engine?: HSREngine) =>
  engine === 'M7A' ? 'purple' : engine === 'SRA' ? 'blue' : 'default'

const taskSummary = (task: HSRManagedTask) => {
  const engine = mappedEngine(task)
  const form = engine ? task.forms?.[engine] : undefined
  if (!form) return '未读取到原生配置'
  const enabled = form.fields.filter(field => field.type === 'boolean' && field.value).length
  return `${props.taskSwitch[task.key] ? '已启用' : '未启用'} · ${form.fields.length} 项配置${enabled ? ` · ${enabled} 个开关已开` : ''}`
}

const handleEngineChange = (value: string | number) => {
  if (!selectedTask.value || (value !== 'SRA' && value !== 'M7A')) return
  emit('mappingChange', selectedTask.value.key, value)
}

const handleFieldChange = (key: string, value: unknown) => {
  if (!selectedTask.value || !selectedEngine.value) return
  emit('fieldChange', selectedEngine.value, selectedTask.value.key, key, value)
}
</script>

<style scoped>
.managed-task-section {
  margin-bottom: 24px;
}

.section-header,
.column-header,
.selected-task-header,
.task-row,
.task-row-title,
.task-row-actions {
  display: flex;
  align-items: center;
}

.section-header {
  margin-bottom: 12px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.section-header-with-action,
.column-header,
.selected-task-header,
.task-row {
  justify-content: space-between;
}

.section-header h3 {
  gap: 10px;
  font-size: 18px;
}

.section-header h3::before {
  height: 20px;
  background: var(--ant-color-primary);
}

.section-header-action {
  display: flex;
  align-items: center;
  gap: 12px;
}

.reset-hint {
  max-width: 360px;
  font-size: 12px;
  text-align: right;
}

.snapshot-warning,
.panel-alert {
  margin-bottom: 12px;
}

.dropped-list {
  margin: 0 0 8px;
  padding-left: 18px;
}

.dropped-list li {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: baseline;
}

.dropped-list code {
  font-size: 12px;
}

.dropped-value {
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}

.task-editor-layout {
  min-height: 420px;
}

.task-list-column,
.task-option-column {
  display: flex;
  flex-direction: column;
}

.column-header {
  gap: 12px;
  margin-bottom: 12px;
  font-size: 16px;
  font-weight: 600;
}

.task-list {
  flex: 1;
  overflow: hidden;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
}

.task-row {
  width: 100%;
  gap: 16px;
  padding: 16px;
  border: 0;
  border-bottom: 1px solid var(--ant-color-border-secondary);
  background: var(--ant-color-bg-container);
  color: var(--ant-color-text);
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition:
    background-color 0.2s ease,
    border-color 0.2s ease;
}

.task-row:hover {
  background: var(--ant-color-fill-quaternary);
}

.task-row:last-child {
  border-bottom: 0;
}

.task-row-selected {
  padding-left: 13px;
  border-left: 3px solid var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
}

.task-row-main {
  min-width: 0;
  flex: 1;
}

.task-row-title,
.task-row-actions {
  gap: 8px;
}

.task-row-title {
  font-weight: 600;
}

.task-row-summary,
.selected-task-description,
.source-line {
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}

.task-row-summary {
  overflow: hidden;
  margin-top: 6px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-option-panel {
  flex: 1;
  padding: 20px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
}

.selected-task-header {
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.selected-task-title {
  font-size: 18px;
  font-weight: 700;
}

.selected-task-description {
  margin-top: 4px;
}

.source-line {
  display: block;
  overflow: hidden;
  margin-bottom: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-option-empty {
  display: flex;
  flex: 1;
  min-height: 320px;
  align-items: center;
  justify-content: center;
  border: 1px dashed var(--ant-color-border);
  border-radius: 8px;
}
</style>
