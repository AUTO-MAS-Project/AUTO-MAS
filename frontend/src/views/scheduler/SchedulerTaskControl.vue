<template>
  <div class="task-control" :class="isRunning ? 'app-page-section' : 'draft-bar'">
    <div class="control-card">
      <div class="control-row">
        <div v-if="!isRunning" class="queue-scope-pair">
          <a-select
            :value="selectedTaskId"
            :placeholder="t('core.scheduler.control.taskPlaceholder')"
            class="target-select"
            :bordered="false"
            :dropdown-match-select-width="false"
            :loading="taskOptionsLoading"
            :options="taskOptions"
            :disabled="disabled || starting"
            size="large"
            @change="onTargetChange"
            @dropdown-visible-change="onDropdown"
          />
          <SchedulerRunScope
            v-if="selectedTaskId"
            :key="selectedTaskId"
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
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { PlayCircleOutlined, StopOutlined } from '@ant-design/icons-vue'
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
    !props.scope
  )
    return true
  if (!props.taskOptions.some(option => option.value === props.selectedTaskId)) return true
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
}
.draft-bar .control-card {
  padding: 0 0 0 2px;
}
.draft-bar .control-row {
  gap: 4px 8px;
}
.queue-scope-pair {
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  background: var(--ant-color-fill-tertiary);
  border-radius: var(--ant-border-radius);
}
.target-select {
  width: 178px;
  min-width: 0;
  border-radius: inherit;
}
.target-select:not(:only-child) {
  border-start-end-radius: 0;
  border-end-end-radius: 0;
}
.target-select:not(.ant-select-disabled):hover {
  background: var(--ant-color-fill-quaternary);
}
.target-select.ant-select-focused {
  outline: 2px solid var(--ant-color-primary);
  outline-offset: -2px;
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
