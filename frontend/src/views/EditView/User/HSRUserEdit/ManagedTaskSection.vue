<template>
  <div class="managed-task-section">
    <div class="section-header section-header-with-action">
      <h3>MAS 管控任务</h3>
      <a-button :loading="loading" @click="emit('importSource')">一键从源配置导入</a-button>
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
      <a-empty v-if="!snapshot && !loading" description="尚未读取到原生任务配置" />
      <a-row v-else-if="snapshot" :gutter="[24, 16]" class="task-editor-layout">
        <a-col :xs="24" :lg="12" class="task-list-column">
          <div class="column-header">
            <span>任务模块</span>
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
                </div>
                <div class="task-row-summary">{{ taskSummary(task) }}</div>
              </div>
              <div class="task-row-actions">
                <a-switch
                  :checked="Boolean(taskSwitch[task.key])"
                  :disabled="saving"
                  size="small"
                  @click.stop
                  @change="emit('taskToggle', task.key, Boolean($event))"
                />
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
            <span>详细配置</span>
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

            <a-form-item v-if="engineOptions.length > 1" label="执行引擎">
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
              message="该用户暂未启用此模块；配置会保存，但本轮不会执行。"
              class="panel-alert"
            />

            <template v-if="selectedForm">
              <a-typography-text type="secondary" class="source-line">
                读取自：{{ selectedForm.source }}
              </a-typography-text>
              <DynamicManagedFields
                :fields="selectedForm.fields"
                :disabled="saving"
                @change="handleFieldChange"
              />
            </template>
            <a-alert
              v-else
              type="warning"
              show-icon
              message="所选引擎没有返回该模块的动态配置，请检查原生配置文件与适配器版本。"
            />
          </div>
          <div v-else class="task-option-empty">
            <a-empty description="没有可配置任务" />
          </div>
        </a-col>
      </a-row>
    </a-spin>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RightOutlined } from '@ant-design/icons-vue'
import type {
  HSREngine,
  HSRManagedConfigSnapshot,
  HSRManagedTask,
} from '@/composables/useHSRPluginApi'
import DynamicManagedFields from './DynamicManagedFields.vue'

const props = defineProps<{
  snapshot: HSRManagedConfigSnapshot | null
  taskSwitch: Record<string, boolean | null | undefined>
  saving: boolean
  loading: boolean
}>()

const emit = defineEmits<{
  importSource: []
  taskToggle: [task: string, enabled: boolean]
  mappingChange: [task: string, engine: HSREngine]
  fieldChange: [engine: HSREngine, task: string, key: string, value: unknown]
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

.snapshot-warning,
.panel-alert {
  margin-bottom: 12px;
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
