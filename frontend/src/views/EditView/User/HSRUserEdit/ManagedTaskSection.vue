<template>
  <div class="managed-task-section">
    <div class="section-header">
      <h3>{{ t('edit.hsrTaskConfig') }}</h3>
      <!-- 脚本态编辑的是共享的那份：标题旁一个标签说明，代替原先的整条提示 -->
      <a-tooltip v-if="shared" :title="t('edit.hsrSharedPlanHint')">
        <a-tag color="blue" class="shared-tag">{{ t('edit.hsrSharedPlanTag') }}</a-tag>
      </a-tooltip>
    </div>
    <!-- 快照诊断合成一条：区块内最多一条提示 -->
    <a-alert
      v-if="snapshotWarnings.length"
      type="warning"
      show-icon
      :message="snapshotWarnings.length === 1 ? snapshotWarnings[0] : snapshotWarnings.join('；')"
      class="snapshot-warning"
    />

    <a-spin :spinning="loading">
      <a-empty v-if="!snapshot && !loading" :description="t('edit.nativeTaskConfigurationHas')" />
      <!-- 与 MFW 任务队列同一种布局：左边模块列表、右边所选模块的设置，两栏定高各自滚动 -->
      <a-row v-else-if="snapshot" :gutter="24" class="module-layout">
        <a-col :xs="24" :lg="9" class="module-list-column">
          <div class="module-list">
            <div
              v-for="task in snapshot.tasks"
              :key="task.key"
              class="module-row"
              :class="{
                'module-row-selected': selectedTask?.key === task.key,
                'module-row-disabled': !isEnabled(task),
              }"
              role="button"
              tabindex="0"
              :data-testid="`hsr-module-${task.key}`"
              @click="selectedKey = task.key"
              @keydown.enter.self="selectedKey = task.key"
            >
              <div class="module-main">
                <div class="module-title">
                  <span class="module-name">{{ task.name }}</span>
                  <a-tag class="phase-tag">{{ phaseLabel(task.phase) }}</a-tag>
                  <a-tag v-if="droppedOverridesOf(task).length" color="warning">
                    {{ t('edit.invalidOverridesCount', { n: droppedOverridesOf(task).length }) }}
                  </a-tag>
                </div>
                <div class="module-summary" :title="taskSummary(task)">{{ taskSummary(task) }}</div>
              </div>
              <span class="module-switch" @click.stop @keydown.stop>
                <a-switch
                  :checked="isEnabled(task)"
                  :disabled="saving"
                  size="small"
                  :aria-label="task.name"
                  @change="emit('taskToggle', task.key, Boolean($event))"
                />
              </span>
              <a-tag :color="engineColor(mappedEngine(task))" class="module-engine">
                {{ engineLabel(mappedEngine(task)) }}
              </a-tag>
            </div>
          </div>
        </a-col>
        <a-col :xs="24" :lg="15" class="module-panel-column">
          <ManagedModulePanel
            v-if="selectedTask"
            :task="selectedTask"
            :engine="selectedEngine"
            :form="selectedForm"
            :engine-options="engineOptions"
            :engine-name="engineLabel(selectedEngine)"
            :engine-color="engineColor(selectedEngine)"
            :saving="saving"
            :loading="loading"
            :shared="shared"
            :cloud="cloud"
            @engine-change="handleEngineChange"
            @field-change="handleFieldChange"
            @field-reset="handleFieldReset"
            @reset-module="handleModuleReset"
            @clear-invalid="handleClearInvalidOverrides"
          >
            <template #extra>
              <slot
                name="module-extra"
                :task="selectedTask"
                :engine="selectedEngine"
                :form="selectedForm"
              />
            </template>
          </ManagedModulePanel>
        </a-col>
      </a-row>
    </a-spin>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, ref } from 'vue'
import {
  getHSRDroppedOverrides,
  type HSREngine,
  type HSRManagedConfigSnapshot,
  type HSRManagedTask,
} from '@/composables/useHSRPluginApi'
import ManagedModulePanel from './ManagedModulePanel.vue'
import { summarizeOverriddenFields } from './managedFields'

const { t } = useI18n()

const props = defineProps<{
  snapshot: HSRManagedConfigSnapshot | null
  taskSwitch: Record<string, boolean | null | undefined>
  saving: boolean
  loading: boolean
  /** 当前编辑的是脚本共享计划（「脚本」来源）：只影响提示与确认文案。 */
  shared?: boolean
  /** 云·星穹铁道：引擎恒为三月七，不给引擎分段控件。 */
  cloud?: boolean
  /** 页面顶部已经显示过的能力提示，快照里重复的同一句不再在本区块显示。 */
  shownWarnings?: readonly string[]
  /** 页面给出的模块摘要（体力模块写副本与历战余响）；没给的模块按改过的设置概括。 */
  summaries?: Partial<Record<string, string>>
}>()

const emit = defineEmits<{
  taskToggle: [task: string, enabled: boolean]
  mappingChange: [task: string, engine: HSREngine]
  fieldChange: [engine: HSREngine, task: string, key: string, value: unknown]
  /** 删掉单个键的覆盖值。 */
  fieldReset: [engine: HSREngine, task: string, key: string]
  /** 只清当前引擎当前模块的全部覆盖值。 */
  moduleReset: [engine: HSREngine, task: string]
  /** 只从 Managed.Options 里剔掉后端报告为失效的键。 */
  clearInvalidOverrides: [engine: HSREngine, task: string, keys: string[]]
}>()

const selectedKey = ref('')

const snapshotWarnings = computed(() =>
  (props.snapshot?.warnings ?? []).filter(warning => !props.shownWarnings?.includes(warning))
)

const isEnabled = (task: HSRManagedTask) => Boolean(props.taskSwitch[task.key])

const availableEngines = (task: HSRManagedTask): HSREngine[] =>
  task.engines.filter(engine => Boolean(task.forms?.[engine]))

const mappedEngine = (task: HSRManagedTask): HSREngine | undefined => {
  const configured = props.snapshot?.task_mapping?.[task.key]
  const available = availableEngines(task)
  if (configured && available.includes(configured)) return configured
  return available[0]
}

const formOf = (task: HSRManagedTask, engine = mappedEngine(task)) =>
  engine ? task.forms?.[engine] : undefined

// 没选过或选中的模块已不在快照里时，默认显示第一个模块
const selectedTask = computed(() => {
  const tasks = props.snapshot?.tasks ?? []
  return tasks.find(task => task.key === selectedKey.value) ?? tasks[0] ?? null
})
const selectedEngine = computed(() =>
  selectedTask.value ? mappedEngine(selectedTask.value) : undefined
)
const selectedForm = computed(() =>
  selectedTask.value ? formOf(selectedTask.value, selectedEngine.value) : undefined
)

const droppedOverridesOf = (task: HSRManagedTask) => getHSRDroppedOverrides(formOf(task))

const engineOptions = computed(() =>
  selectedTask.value
    ? availableEngines(selectedTask.value).map(engine => ({
        value: engine,
        label: engineLabel(engine),
      }))
    : []
)

const phaseLabel = (phase: string) => (phase === 'weekly' ? t('edit.weekly') : t('edit.daily'))
const engineLabel = (engine?: HSREngine) =>
  engine === 'M7A'
    ? t('edit.directEngineM7a')
    : engine === 'SRA'
      ? 'SRA'
      : t('edit.hsrEngineUnavailable')
const engineColor = (engine?: HSREngine) =>
  engine === 'M7A' ? 'purple' : engine === 'SRA' ? 'blue' : 'default'

const taskSummary = (task: HSRManagedTask) => {
  const pageSummary = props.summaries?.[task.key]
  if (pageSummary) return pageSummary
  const engine = mappedEngine(task)
  const form = formOf(task, engine)
  if (!form) return t('edit.hsrNativeConfigNotLoaded')
  const summary = summarizeOverriddenFields(form.fields, {
    on: t('edit.hsrValueOn'),
    off: t('edit.hsrValueOff'),
    empty: t('edit.hsrValueEmpty'),
  })
  if (!summary) return t('edit.hsrSummaryNative', { engine: engineLabel(engine) })
  const text = summary.items
    .map(item => t('edit.hsrSummaryItem', { label: item.label, value: item.value }))
    .join(' · ')
  return summary.rest ? t('edit.hsrSummaryMore', { text, n: summary.rest }) : text
}

const handleEngineChange = (engine: HSREngine) => {
  if (!selectedTask.value) return
  emit('mappingChange', selectedTask.value.key, engine)
}

const handleFieldChange = (key: string, value: unknown) => {
  if (!selectedTask.value || !selectedEngine.value) return
  emit('fieldChange', selectedEngine.value, selectedTask.value.key, key, value)
}

const handleFieldReset = (key: string) => {
  if (!selectedTask.value || !selectedEngine.value) return
  emit('fieldReset', selectedEngine.value, selectedTask.value.key, key)
}

const handleModuleReset = () => {
  if (!selectedTask.value || !selectedEngine.value) return
  emit('moduleReset', selectedEngine.value, selectedTask.value.key)
}

const handleClearInvalidOverrides = (keys: string[]) => {
  if (!selectedTask.value || !selectedEngine.value || keys.length === 0) return
  emit('clearInvalidOverrides', selectedEngine.value, selectedTask.value.key, keys)
}
</script>

<style scoped>
.managed-task-section {
  margin-bottom: 24px;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.section-header h3 {
  gap: 10px;
  font-size: 18px;
}

.section-header h3::before {
  height: 20px;
  background: var(--ant-color-primary);
}

.shared-tag {
  cursor: default;
}

.snapshot-warning {
  margin-bottom: 12px;
}

/* 左右两栏等高、高度固定：体力模块设置再多也不把页面撑长，各自在框里滚 */
.module-layout {
  height: 640px;
}

.module-list-column,
.module-panel-column {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.module-list {
  flex: 1;
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
}

.module-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
  color: var(--ant-color-text);
  cursor: pointer;
  transition: background-color 0.2s ease;
}

.module-row:last-child {
  border-bottom: 0;
}

.module-row:hover,
.module-row:focus-visible {
  background: var(--ant-color-fill-quaternary);
  outline: none;
}

.module-row-selected,
.module-row-selected:hover {
  padding-left: 13px;
  border-left: 3px solid var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
}

.module-switch {
  display: inline-flex;
  flex-shrink: 0;
  cursor: default;
}

.module-engine {
  flex-shrink: 0;
  margin-inline-end: 0;
}

.module-main {
  min-width: 0;
  flex: 1;
}

.module-title {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.module-title :deep(.ant-tag) {
  margin-inline-end: 0;
}

.module-name {
  font-weight: 600;
}

.module-row-disabled .module-name,
.module-row-disabled .module-summary {
  color: var(--ant-color-text-tertiary);
}

.module-summary {
  overflow: hidden;
  margin-top: 4px;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 与 :lg 断点对齐：栅格在 992px 以下就折成上下两块，定高要在同一宽度放开，否则两栏叠在 640px 里溢出 */
@media (max-width: 991px) {
  /* 折成上下两块后整行不再定高，改成每一栏各自定高 */
  .module-layout {
    height: auto;
    row-gap: 16px;
  }

  .module-list-column {
    height: auto;
  }

  .module-panel-column {
    height: 560px;
  }
}
</style>
