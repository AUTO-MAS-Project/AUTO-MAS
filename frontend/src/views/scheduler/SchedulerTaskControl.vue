<template>
  <div class="task-control">
    <div class="control-card">
      <div class="control-row">
        <a-space size="middle">
          <a-select
            v-if="status !== '运行'"
            v-model:value="localSelectedTaskId"
            :placeholder="t('scheduler.control.taskPlaceholder')"
            style="width: 200px"
            :loading="taskOptionsLoading"
            :options="taskOptions"
            :disabled="disabled"
            size="large"
            @change="onTaskChange"
            @dropdown-visible-change="onTasksDropdownVisible"
          />
          <a-select
            v-if="status !== '运行'"
            v-model:value="localSelectedMode"
            :placeholder="t('scheduler.control.modePlaceholder')"
            style="width: 120px"
            :disabled="disabled"
            size="large"
            :options="modeOptions"
          />
          <div v-else class="running-info">
            <span class="info-item">
              <span class="label">{{ t('scheduler.control.taskLabel') }}</span>
              <span class="value">{{ runningTaskLabel }}</span>
            </span>
            <span class="divider">|</span>
            <span class="info-item">
              <span class="label">{{ t('scheduler.control.modeLabel') }}</span>
              <span class="value">{{ runningModeLabel }}</span>
            </span>
          </div>
        </a-space>
        <div class="control-spacer"></div>
        <a-space size="middle">
          <template v-if="showQueueCursor">
            <a-select
              v-model:value="localStartScriptId"
              :placeholder="t('scheduler.control.startScriptPlaceholder')"
              style="width: 260px"
              :loading="resumeScriptLoading"
              :options="resumeScriptOptions"
              :disabled="disabled"
              allow-clear
              size="large"
              @change="onStartScriptChange"
              @dropdown-visible-change="onScriptDropdownVisible"
            />
            <a-select
              v-if="localStartScriptId"
              v-model:value="localStartUserId"
              :placeholder="t('scheduler.control.startUserPlaceholder')"
              style="width: 200px"
              :loading="userOptionsLoading"
              :options="userOptions"
              :disabled="disabled"
              allow-clear
              size="large"
              @change="onStartUserChange"
              @dropdown-visible-change="onUserDropdownVisible"
            />
          </template>
          <a-button
            :type="status === '运行' ? 'default' : 'primary'"
            :danger="status === '运行'"
            :disabled="startDisabled"
            size="large"
            @click="status === '运行' ? emit('stop') : emit('start')"
          >
            <template #icon>
              <StopOutlined v-if="status === '运行'" />
              <PlayCircleOutlined v-else />
            </template>
            {{ status === '运行' ? t('scheduler.control.stop') : t('scheduler.control.start') }}
          </a-button>
        </a-space>
      </div>
      <div v-if="cyclePreview.length" class="cycle-preview">
        <span class="cycle-preview-label">{{ t('scheduler.cycle.nextTitle') }}</span>
        <a-space size="small" wrap>
          <a-tag
            v-for="item in cyclePreview"
            :key="item.queueItemId"
            :color="item.isRunning ? 'blue' : item.isDue ? 'orange' : 'default'"
          >
            {{ item.scriptName }}
            <span class="cycle-preview-time">
              {{
                item.isRunning
                  ? t('scheduler.cycle.running')
                  : item.isDue
                    ? t('scheduler.cycle.due')
                    : item.nextRunAt
              }}
            </span>
          </a-tag>
        </a-space>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { PlayCircleOutlined, StopOutlined } from '@ant-design/icons-vue'
import type { SchedulerTaskOption } from './schedulerConstants'
import { TaskMode } from '@/api/models/TaskMode'
import type { WSTaskCyclePreviewData } from '@/services/websocket/types'

const props = withDefaults(
  defineProps<{
    selectedTaskId: string | null
    selectedMode: TaskMode | null
    resumeFromScriptId?: string | null
    resumeScriptOptions?: Array<{ label: string; value: string }>
    resumeScriptLoading?: boolean
    startUserId?: string | null
    userOptions?: Array<{ label: string; value: string }>
    userOptionsLoading?: boolean
    taskOptions: SchedulerTaskOption[]
    taskOptionsLoading: boolean
    status: string
    disabled?: boolean
    runningTaskLabel?: string
    runningModeLabel?: string
    cycleNextList?: WSTaskCyclePreviewData[]
  }>(),
  {
    resumeFromScriptId: null,
    resumeScriptOptions: () => [],
    resumeScriptLoading: false,
    startUserId: null,
    userOptions: () => [],
    userOptionsLoading: false,
    disabled: false,
    runningTaskLabel: '',
    runningModeLabel: '',
    cycleNextList: () => [],
  }
)

const emit = defineEmits<{
  (event: 'update:selectedTaskId', value: string | null): void
  (event: 'update:selectedMode', value: TaskMode | null): void
  (event: 'update:resumeFromScriptId', value: string | null): void
  (event: 'update:startUserId', value: string | null): void
  (event: 'update:runningTaskLabel', value: string): void
  (event: 'update:runningModeLabel', value: string): void
  (event: 'start'): void
  (event: 'stop'): void
  (event: 'task-changed', value: string | null): void
  (event: 'refresh-tasks'): void
  (event: 'refresh-resume-scripts'): void
  (event: 'refresh-users'): void
}>()

const { t } = useI18n()
const localSelectedTaskId = ref(props.selectedTaskId)
const localSelectedMode = ref<TaskMode | null>(props.selectedMode ?? TaskMode.AUTO_PROXY)
const localStartScriptId = ref(props.resumeFromScriptId)
const localStartUserId = ref(props.startUserId)
const selectedTaskOption = computed(() =>
  props.taskOptions.find(item => item.value === localSelectedTaskId.value)
)
const showQueueCursor = computed(
  () => props.status !== '运行' && selectedTaskOption.value?.kind === 'queue'
)
const startDisabled = computed(
  () =>
    props.status !== '运行' &&
    (props.disabled ||
      !localSelectedTaskId.value ||
      !selectedTaskOption.value ||
      (showQueueCursor.value &&
        (props.resumeScriptLoading ||
          Boolean(localStartScriptId.value && props.userOptionsLoading))))
)
const modeOptions = computed(() => [
  { label: t('scheduler.mode.autoProxy'), value: TaskMode.AUTO_PROXY },
])
const cyclePreview = computed(() => (props.status === '运行' ? props.cycleNextList : []))

watch(
  () => props.selectedTaskId,
  value => (localSelectedTaskId.value = value)
)
watch(
  [() => props.status, () => props.selectedMode],
  ([status, value]) => {
    const next = status === '运行' ? (value ?? TaskMode.AUTO_PROXY) : TaskMode.AUTO_PROXY
    localSelectedMode.value = next
    if (status !== '运行' && value !== TaskMode.AUTO_PROXY) {
      emit('update:selectedMode', TaskMode.AUTO_PROXY)
    }
  },
  { immediate: true }
)
watch(
  () => props.resumeFromScriptId,
  value => (localStartScriptId.value = value)
)
watch(
  () => props.startUserId,
  value => (localStartUserId.value = value)
)

const onTaskChange = (value: string) => {
  emit('update:selectedTaskId', value)
  emit('task-changed', value)
}
const onTasksDropdownVisible = (open: boolean) => {
  if (open) emit('refresh-tasks')
}
const onScriptDropdownVisible = (open: boolean) => {
  if (open) emit('refresh-resume-scripts')
}
const onUserDropdownVisible = (open: boolean) => {
  if (open) emit('refresh-users')
}
const onStartScriptChange = (value: string | undefined) => {
  emit('update:resumeFromScriptId', value ?? null)
  if (!value) emit('update:startUserId', null)
  else emit('refresh-users')
}
const onStartUserChange = (value: string | undefined) => emit('update:startUserId', value ?? null)
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
.cycle-preview {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 16px;
}
.cycle-preview-label {
  color: var(--ant-color-text-secondary);
  font-size: 13px;
}
.cycle-preview-time {
  margin-left: 8px;
  font-variant-numeric: tabular-nums;
  opacity: 0.75;
}

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
  .control-row :deep(.ant-space) {
    flex-wrap: wrap;
  }
}
</style>
