<template>
  <div class="task-control" :class="isRunning ? 'app-page-section' : 'draft-bar'">
    <div class="control-card">
      <div class="control-row">
        <div v-if="!isRunning" class="queue-scope-pair">
          <a-select
            :id="targetId"
            :value="selectedTaskId"
            :placeholder="t('core.scheduler.control.taskPlaceholder')"
            :title="selectedTarget?.label"
            class="target-select run-control-trigger"
            :class="{ 'pointer-focused': targetPointerFocus }"
            option-label-prop="name"
            :bordered="false"
            :dropdown-match-select-width="false"
            :loading="taskOptionsLoading"
            :options="taskOptions"
            :disabled="disabled || starting"
            size="large"
            @pointerdown.capture="targetPointerFocus = true"
            @keydown="targetPointerFocus = false"
            @blur="targetPointerFocus = false"
            @change="onTargetChange"
            @dropdown-visible-change="onDropdown"
          />
          <label
            :for="targetId"
            class="target-icon"
            :aria-label="selectedTarget?.label || t('core.scheduler.control.taskPlaceholder')"
          >
            <component
              :is="selectedTarget?.kind === 'script' ? FileTextOutlined : UnorderedListOutlined"
              aria-hidden="true"
            />
          </label>
          <SchedulerRunScope
            :key="selectedTaskId ?? undefined"
            :has-target="!!selectedTarget"
            :model-value="scope"
            :loading="scopeLoading"
            :error="scopeError"
            :disabled="disabled || starting"
            @update:model-value="value => emit('update:scope', value)"
            @refresh="emit('refresh-scope')"
          />
        </div>
        <div v-else class="running-info">
          <span class="info-item">
            <span class="label">{{ t('core.scheduler.control.taskLabel') }}</span>
            <span class="value">{{ runningTaskLabel }}</span>
          </span>
          <span class="divider">|</span>
          <span class="info-item">
            <span class="label">{{ t('core.scheduler.control.modeLabel') }}</span>
            <span class="value">{{ runningModeLabel }}</span>
          </span>
        </div>
        <a-button
          class="run-action"
          :type="isRunning ? 'default' : 'primary'"
          :danger="isRunning"
          :loading="starting"
          :disabled="!isRunning && startDisabled"
          size="large"
          @click="isRunning ? emit('stop') : emit('start')"
        >
          <template #icon><StopOutlined v-if="isRunning" /><PlayCircleOutlined v-else /></template>
          {{ isRunning ? t('core.scheduler.control.stop') : t('core.scheduler.control.start') }}
        </a-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, useId } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  FileTextOutlined,
  PlayCircleOutlined,
  StopOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons-vue'
import { scopeRequest, type TaskScopeDraft } from '@/composables/taskSelection'
import type { TaskTarget } from '@/composables/useTaskOptions'
import type { SchedulerStatus } from './schedulerConstants'
import SchedulerRunScope from './SchedulerRunScope.vue'

const props = defineProps<{
  selectedTaskId: string | null
  taskOptions: TaskTarget[]
  taskOptionsLoading: boolean
  status: SchedulerStatus
  scope?: TaskScopeDraft
  scopeLoading?: boolean
  scopeError?: string
  disabled?: boolean
  starting?: boolean
  runningTaskLabel?: string
  runningModeLabel?: string
}>()
const emit = defineEmits<{
  'task-changed': [value: string | null]
  'update:scope': [value: TaskScopeDraft]
  'refresh-scope': []
  'refresh-tasks': []
  start: []
  stop: []
}>()
const { t } = useI18n()
const targetId = useId()
// Select 内部是只读搜索框，Chromium 在鼠标点击时也会匹配 :focus-visible。
const targetPointerFocus = ref(false)
const selectedTarget = computed(() =>
  props.taskOptions.find(option => option.value === props.selectedTaskId)
)
const onTargetChange = (value: unknown) =>
  emit('task-changed', typeof value === 'string' ? value : null)
const onDropdown = (visible: boolean) => {
  if (visible) emit('refresh-tasks')
}
const isRunning = computed(() => props.status === '运行')
const startDisabled = computed(() => {
  if (
    props.disabled ||
    props.starting ||
    props.taskOptionsLoading ||
    props.scopeLoading ||
    props.scopeError ||
    !props.scope ||
    !selectedTarget.value
  )
    return true
  try {
    scopeRequest(props.scope)
    return false
  } catch {
    return true
  }
})
</script>

<style scoped>
.task-control {
  margin-bottom: var(--app-page-content-gap);
  overflow: hidden;
}

.control-card {
  padding: var(--app-page-content-padding);
}

.control-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
}

.run-action {
  margin-inline-start: auto;
}
.draft-bar {
  flex-shrink: 0;
  overflow: visible;
}
.draft-bar .control-card {
  padding: 0 0 0 2px;
}
.draft-bar .control-row {
  gap: 4px 8px;
}
.queue-scope-pair {
  --trigger-face: color-mix(in srgb, var(--ant-color-bg-elevated) 97%, var(--ant-color-text));
  --trigger-hover: color-mix(in srgb, var(--ant-color-bg-elevated) 93%, var(--ant-color-text));
  --trigger-rim: var(--ant-color-text-light-solid);
  --trigger-shadow: color-mix(in srgb, var(--ant-color-bg-mask) 30%, transparent);
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  max-width: 100%;
}
html.dark .queue-scope-pair {
  --trigger-face: color-mix(
    in srgb,
    var(--ant-color-bg-elevated) 90%,
    var(--ant-color-text-light-solid)
  );
  --trigger-hover: color-mix(
    in srgb,
    var(--ant-color-bg-elevated) 85%,
    var(--ant-color-text-light-solid)
  );
  --trigger-rim: color-mix(in srgb, var(--ant-color-text-light-solid) 19%, transparent);
  --trigger-shadow: var(--ant-color-bg-mask);
}
.queue-scope-pair :deep(.run-control-trigger) {
  height: 40px;
  min-width: 0;
  border: 0;
  border-radius: var(--ant-border-radius);
  background: var(--trigger-face);
  color: var(--ant-color-text);
  box-shadow:
    inset 0 1px 0 var(--trigger-rim),
    0 1px 1px var(--trigger-shadow),
    0 3px 4px -2px var(--trigger-shadow);
  transition: background-color 100ms ease-out;
}
.queue-scope-pair
  :deep(
    .run-control-trigger:not(:disabled, .ant-select-disabled):is(
        :hover,
        .ant-select-open,
        [aria-expanded='true']
      )
  ) {
  background: var(--trigger-hover);
}
.queue-scope-pair :deep(.run-control-trigger:is(:disabled, .ant-select-disabled)),
.target-select.ant-select-disabled + .target-icon {
  opacity: 0.55;
}
.queue-scope-pair :deep(.run-control-trigger:focus-visible),
.target-select:not(.pointer-focused):has(:focus-visible) {
  outline: 2px solid var(--ant-color-primary);
  outline-offset: -2px;
}
@media (prefers-reduced-motion: reduce) {
  .queue-scope-pair :deep(.run-control-trigger) {
    transition: none;
  }
}
.target-select {
  width: 174px;
}
.target-icon {
  position: absolute;
  display: inline-flex;
  inset-inline-start: 12px;
  pointer-events: none;
  font-size: 16px;
  color: var(--ant-color-text-secondary);
}
.queue-scope-pair .target-select :deep(.ant-select-selector) {
  padding-inline: 36px 31px;
}
.queue-scope-pair .target-select :deep(.ant-select-selection-item),
.queue-scope-pair .target-select :deep(.ant-select-selection-placeholder) {
  padding: 0;
  font-size: 14px;
}
.queue-scope-pair .target-select :deep(.ant-select-selection-item) {
  font-weight: 500;
  color: var(--ant-color-text);
}
.target-select :deep(.ant-select-arrow) {
  inset-inline-end: 12px;
  width: 12px;
  justify-content: center;
  font-size: 11px;
  color: var(--ant-color-text-secondary);
}
.target-select.ant-select-open :deep(.ant-select-arrow) {
  color: var(--ant-color-link);
}
.target-select.ant-select-open :deep(.anticon-down svg) {
  transform: rotate(180deg);
}

/* 响应式 - 移动端适配 */
@media (max-width: 768px) {
  .app-page-section .control-row {
    flex-direction: column;
    align-items: stretch;
  }

  .app-page-section .run-action {
    align-self: flex-start;
    margin-inline-start: 0;
  }
}

.running-info {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 0 8px;
}

.info-item {
  display: flex;
  align-items: center;
  font-size: 16px;
}

.info-item .label {
  color: var(--ant-color-text-secondary);
  margin-right: 4px;
}

.info-item .value {
  color: var(--ant-color-text);
  font-weight: 500;
}

.divider {
  color: var(--ant-color-border);
}
</style>
