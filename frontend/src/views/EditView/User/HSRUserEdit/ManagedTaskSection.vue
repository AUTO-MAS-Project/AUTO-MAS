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
      <div v-else-if="snapshot" class="module-list">
        <div
          v-for="task in snapshot.tasks"
          :key="task.key"
          class="module-row"
          :class="{ 'module-row-disabled': !isEnabled(task) }"
          role="button"
          tabindex="0"
          :data-testid="`hsr-module-${task.key}`"
          @click="openTask(task.key)"
          @keydown.enter.self="openTask(task.key)"
        >
          <span class="module-switch" @click.stop @keydown.stop>
            <a-switch
              :checked="isEnabled(task)"
              :disabled="saving"
              size="small"
              :aria-label="task.name"
              @change="emit('taskToggle', task.key, Boolean($event))"
            />
          </span>
          <div class="module-main">
            <div class="module-title">
              <span class="module-name">{{ task.name }}</span>
              <a-tag class="phase-tag">{{ phaseLabel(task.phase) }}</a-tag>
              <a-tag :color="engineColor(mappedEngine(task))">
                {{ engineLabel(mappedEngine(task)) }}
              </a-tag>
              <a-tooltip v-if="!isEnabled(task)" :title="notEnabledTip">
                <a-tag class="not-enabled-tag">{{ t('edit.hsrTaskNotEnabled') }}</a-tag>
              </a-tooltip>
              <a-tag v-if="droppedOverridesOf(task).length" color="warning">
                {{ t('edit.invalidOverridesCount', { n: droppedOverridesOf(task).length }) }}
              </a-tag>
            </div>
            <div class="module-summary" :title="taskSummary(task)">{{ taskSummary(task) }}</div>
          </div>
          <a-button size="small" class="module-settings" @click.stop="openTask(task.key)">
            <template #icon>
              <SettingOutlined />
            </template>
            {{ t('edit.hsrModuleSettings') }}
          </a-button>
        </div>
      </div>
    </a-spin>

    <ManagedModuleDialog
      :open="Boolean(openTaskKey && openedTask)"
      :task="openedTask"
      :engine="openedEngine"
      :form="openedForm"
      :engine-options="engineOptions"
      :engine-name="engineLabel(openedEngine)"
      :enabled="openedTask ? isEnabled(openedTask) : false"
      :saving="saving"
      :loading="loading"
      :shared="shared"
      :cloud="cloud"
      @update:open="value => !value && (openTaskKey = '')"
      @engine-change="handleEngineChange"
      @field-change="handleFieldChange"
      @field-reset="handleFieldReset"
      @reset-module="handleModuleReset"
      @clear-invalid="handleClearInvalidOverrides"
    >
      <template #extra>
        <slot
          v-if="openedTask"
          name="module-extra"
          :task="openedTask"
          :engine="openedEngine"
          :form="openedForm"
        />
      </template>
    </ManagedModuleDialog>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, ref } from 'vue'
import { SettingOutlined } from '@ant-design/icons-vue'
import {
  getHSRDroppedOverrides,
  type HSREngine,
  type HSRManagedConfigSnapshot,
  type HSRManagedTask,
} from '@/composables/useHSRPluginApi'
import ManagedModuleDialog from './ManagedModuleDialog.vue'
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

const openTaskKey = ref('')

const openTask = (key: string) => {
  openTaskKey.value = key
}

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

const openedTask = computed(
  () => props.snapshot?.tasks.find(task => task.key === openTaskKey.value) ?? null
)
const openedEngine = computed(() => (openedTask.value ? mappedEngine(openedTask.value) : undefined))
const openedForm = computed(() =>
  openedTask.value ? formOf(openedTask.value, openedEngine.value) : undefined
)

const droppedOverridesOf = (task: HSRManagedTask) => getHSRDroppedOverrides(formOf(task))

const engineOptions = computed(() =>
  openedTask.value
    ? availableEngines(openedTask.value).map(engine => ({
        value: engine,
        label: engineLabel(engine),
      }))
    : []
)

const notEnabledTip = computed(() =>
  props.shared ? t('edit.hsrSharedModuleNotEnabled') : t('edit.thisModuleNotEnabled')
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
  if (!openedTask.value) return
  emit('mappingChange', openedTask.value.key, engine)
}

const handleFieldChange = (key: string, value: unknown) => {
  if (!openedTask.value || !openedEngine.value) return
  emit('fieldChange', openedEngine.value, openedTask.value.key, key, value)
}

const handleFieldReset = (key: string) => {
  if (!openedTask.value || !openedEngine.value) return
  emit('fieldReset', openedEngine.value, openedTask.value.key, key)
}

const handleModuleReset = () => {
  if (!openedTask.value || !openedEngine.value) return
  emit('moduleReset', openedEngine.value, openedTask.value.key)
}

const handleClearInvalidOverrides = (keys: string[]) => {
  if (!openedTask.value || !openedEngine.value || keys.length === 0) return
  emit('clearInvalidOverrides', openedEngine.value, openedTask.value.key, keys)
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

.module-list {
  overflow: hidden;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
}

.module-row {
  display: flex;
  align-items: center;
  gap: 16px;
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

.module-switch {
  display: inline-flex;
  cursor: default;
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

.not-enabled-tag {
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

.module-settings {
  flex-shrink: 0;
}
</style>
