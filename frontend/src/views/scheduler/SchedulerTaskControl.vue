<template>
  <div class="task-control">
    <div class="control-card">
      <div class="control-row">
        <a-space size="middle">
          <a-select
            v-if="!isRunning"
            :value="selectedTaskId"
            :placeholder="t('core.scheduler.control.taskPlaceholder')"
            style="width: 200px"
            :loading="taskOptionsLoading"
            :options="taskOptions"
            :disabled="disabled || starting"
            size="large"
            @change="onTargetChange"
            @dropdown-visible-change="onDropdown"
          />
          <div v-if="isRunning" class="running-info">
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
          <!-- 范围编辑保留原控制栏位置，只替换内部要求树数据。 -->
          <SchedulerRunScope
            v-if="!isRunning && selectedTaskId"
            :model-value="scope"
            :loading="scopeLoading"
            :error="scopeError"
            :disabled="disabled || starting"
            @update:model-value="value => emit('update:scope', value)"
            @refresh="emit('refresh-scope')"
          />
        </a-space>
        <div class="control-spacer"></div>
        <a-space size="middle">
          <a-button
            :type="isRunning ? 'default' : 'primary'"
            :danger="isRunning"
            :loading="starting"
            :disabled="!isRunning && startDisabled"
            size="large"
            @click="isRunning ? emit('stop') : emit('start')"
          >
            <template #icon
              ><StopOutlined v-if="isRunning" /><PlayCircleOutlined v-else
            /></template>
            {{ isRunning ? t('core.scheduler.control.stop') : t('core.scheduler.control.start') }}
          </a-button>
        </a-space>
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
  margin-bottom: 16px;
  border-radius: 12px;
  background-color: var(--app-background-card-bg, var(--ant-color-bg-container));
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  border: 1px solid var(--ant-color-border-secondary);
  overflow: hidden;
}

.control-card {
  padding: 16px;
}

.control-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
}

.control-spacer {
  flex: 1;
}

/* 响应式 - 移动端适配 */
@media (max-width: 768px) {
  .control-row {
    flex-direction: column;
    align-items: stretch;
  }

  .control-spacer {
    display: none;
  }

  .control-card {
    padding: 12px;
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
