<template>
  <div class="task-control">
    <div class="control-card">
      <div class="control-row">
        <a-space size="middle">
          <a-select
            v-if="status !== '运行'"
            v-model:value="localSelectedTaskId"
            placeholder="选择任务项"
            style="width: 200px"
            :loading="taskOptionsLoading"
            :options="filteredTaskOptions"
            :disabled="disabled"
            size="large"
            @change="onTaskChange"
            @dropdown-visible-change="onDropdownVisibleChange"
          />
          <a-select
            v-if="status !== '运行'"
            v-model:value="localSelectedMode"
            placeholder="选择模式"
            style="width: 120px"
            :disabled="disabled"
            size="large"
            @change="onModeChange"
          >
            <a-select-option
              v-for="option in modeOptions"
              :key="option.value"
              :value="option.value"
            >
              {{ option.label }}
            </a-select-option>
          </a-select>
          <div v-else class="running-info">
            <span class="info-item">
              <span class="label">任务：</span>
              <span class="value">{{ runningTaskLabel }}</span>
            </span>
            <span class="divider">|</span>
            <span class="info-item">
              <span class="label">模式：</span>
              <span class="value">{{ runningModeLabel }}</span>
            </span>
          </div>
        </a-space>
        <div class="control-spacer"></div>
        <a-space size="middle">
          <a-select
            v-if="status !== '运行' && showResumeScriptSelect"
            v-model:value="localResumeFromScriptId"
            placeholder="从指定脚本继续（默认第一个）"
            style="width: 260px"
            :loading="resumeScriptLoading"
            :options="resumeScriptOptions || []"
            :disabled="disabled"
            allow-clear
            size="large"
            @change="onResumeScriptChange"
            @dropdown-visible-change="onResumeDropdownVisibleChange"
          />
          <a-button
            :type="status === '运行' ? 'default' : 'primary'"
            :danger="status === '运行'"
            :disabled="
              status === '运行' ? false : !localSelectedTaskId || !localSelectedMode || disabled
            "
            size="large"
            @click="onAction"
          >
            <template #icon>
              <StopOutlined v-if="status === '运行'" />
              <PlayCircleOutlined v-else />
            </template>
            {{ status === '运行' ? '停止任务' : '开始执行' }}
          </a-button>
        </a-space>
      </div>
      <div v-if="showCyclePreview" class="cycle-preview">
        <div class="cycle-preview-head">
          <span class="cycle-preview-title">下轮任务</span>
          <span class="cycle-preview-meta">按当前队列循环配置预览</span>
        </div>
        <div class="cycle-preview-grid">
          <div
            v-for="item in cyclePreviewItems"
            :key="`${item.isPlaceholder ? 'empty' : item.queueItemId}-${item.slotIndex}`"
            class="cycle-preview-item"
            :class="{ 'is-running': item.isRunning, 'is-empty': item.isPlaceholder }"
          >
            <div class="cycle-preview-name" :title="item.scriptName">{{ item.scriptName }}</div>
            <div class="cycle-preview-time">
              {{ formatCyclePreviewTime(item) }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { PlayCircleOutlined, StopOutlined } from '@ant-design/icons-vue'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import type { ComboBoxItem } from '@/api/models/ComboBoxItem'
import {
  CYCLE_RUN_MODE,
  type CycleNextInfo,
  type SchedulerStatus,
  TASK_MODE_OPTIONS,
} from './schedulerConstants'

interface Props {
  selectedTaskId: string | null
  selectedMode: TaskCreateIn.mode | null
  resumeFromScriptId?: string | null
  resumeScriptOptions?: Array<{ label: string; value: string }>
  resumeScriptLoading?: boolean
  taskOptions: ComboBoxItem[]
  taskOptionsLoading: boolean
  status: SchedulerStatus
  disabled?: boolean
  runningTaskLabel?: string
  runningModeLabel?: string
  cycleNext?: CycleNextInfo | null
  cycleNextList?: CycleNextInfo[]
}

type Emits = {
  'update:selectedTaskId': [value: string | null]
  'update:selectedMode': [value: TaskCreateIn.mode | null]
  'update:resumeFromScriptId': [value: string | null]
  start: []
  stop: []
  'update:runningTaskLabel': [value: string]
  'update:runningModeLabel': [value: string]
  'refresh-tasks': []
  'task-changed': [value: string | null]
  'mode-changed': [value: TaskCreateIn.mode]
  'refresh-resume-scripts': []
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
  resumeFromScriptId: null,
  resumeScriptOptions: () => [],
  resumeScriptLoading: false,
  runningTaskLabel: '',
  runningModeLabel: '',
  cycleNext: null,
  cycleNextList: () => [],
})

const emit = defineEmits<Emits>()

const cyclePreviewSlotCount = 4

type CyclePreviewSlot = CycleNextInfo & {
  slotIndex: number
  isPlaceholder?: boolean
}

// 本地状态，用于双向绑定
const localSelectedTaskId = ref(props.selectedTaskId)
const localSelectedMode = ref(props.selectedMode)
const localResumeFromScriptId = ref(props.resumeFromScriptId ?? null)

// 模式选项
const modeOptions = TASK_MODE_OPTIONS

const isQueueOption = (option?: ComboBoxItem | null) => {
  return Boolean(option?.label?.startsWith('队列 - '))
}

const filteredTaskOptions = computed(() => {
  if (localSelectedMode.value !== CYCLE_RUN_MODE) return props.taskOptions
  return props.taskOptions.filter(option => option.value == null || isQueueOption(option))
})

const showCyclePreview = computed(() => localSelectedMode.value === CYCLE_RUN_MODE)

const cyclePreviewItems = computed(() => {
  const sourceItems = props.cycleNextList?.length
    ? props.cycleNextList.slice(0, cyclePreviewSlotCount)
    : props.cycleNext
      ? [props.cycleNext]
      : []

  const previewItems: CyclePreviewSlot[] = sourceItems.map((item, index) => ({
    ...item,
    slotIndex: index,
  }))

  while (previewItems.length < cyclePreviewSlotCount) {
    previewItems.push({
      queueItemId: `empty-${previewItems.length}`,
      scriptId: '',
      scriptName: '',
      nextRunAt: '',
      isDue: false,
      isPlaceholder: true,
      slotIndex: previewItems.length,
    })
  }

  return previewItems
})

const formatCyclePreviewTime = (item: CyclePreviewSlot) => {
  if (item.isPlaceholder) return ''
  if (item.isRunning) return '运行中'
  if (item.isDue) return '等待执行'
  return item.nextRunAt || '启动后计算'
}

// 仅当选中队列任务时显示恢复脚本下拉框。
// 注：通过任务选项 label 的 "队列 - " 前缀判断，与 useSchedulerLogic.isQueueTask 保持同步。
const showResumeScriptSelect = computed(() => {
  const selectedTaskId = localSelectedTaskId.value
  if (!selectedTaskId) return false

  const taskOption = props.taskOptions.find(opt => opt.value === selectedTaskId)
  return localSelectedMode.value !== CYCLE_RUN_MODE && isQueueOption(taskOption)
})

// 运行时的显示文本 - 直接使用 props，不再需要本地 ref
// const runningTaskLabel = ref('')
// const runningModeLabel = ref('')

// 监听状态变化，记录运行时的文本信息
watch(
  () => props.status,
  newStatus => {
    if (newStatus === '运行') {
      const taskOption = props.taskOptions.find(opt => opt.value === props.selectedTaskId)
      const taskLabel = taskOption?.label || props.selectedTaskId || ''
      emit('update:runningTaskLabel', taskLabel)

      const modeOption = modeOptions.find(opt => opt.value === props.selectedMode)
      const modeLabel = modeOption?.label || props.selectedMode || ''
      emit('update:runningModeLabel', modeLabel)
    }
  }
)

// 监听 props 变化，同步到本地状态
watch(
  () => props.selectedTaskId,
  newVal => {
    localSelectedTaskId.value = newVal
  },
  { immediate: true }
)

watch(
  () => props.selectedMode,
  newVal => {
    localSelectedMode.value = newVal
  },
  { immediate: true }
)

watch(
  () => props.resumeFromScriptId,
  newVal => {
    localResumeFromScriptId.value = newVal ?? null
  },
  { immediate: true }
)

// 事件处理
const onTaskChange = (value: string) => {
  emit('update:selectedTaskId', value)
  emit('task-changed', value)
}

const onModeChange = (value: TaskCreateIn.mode) => {
  emit('update:selectedMode', value)
  emit('mode-changed', value)

  if (value === CYCLE_RUN_MODE) {
    const selectedTaskId = localSelectedTaskId.value
    const taskOption = props.taskOptions.find(opt => opt.value === selectedTaskId)
    if (selectedTaskId && !isQueueOption(taskOption)) {
      localSelectedTaskId.value = null
      emit('update:selectedTaskId', null)
      emit('task-changed', null)
    }
    localResumeFromScriptId.value = null
    emit('update:resumeFromScriptId', null)
  }
}

const onResumeScriptChange = (value: string | undefined) => {
  emit('update:resumeFromScriptId', value ?? null)
}

const onResumeDropdownVisibleChange = (open: boolean) => {
  if (open) emit('refresh-resume-scripts')
}

// 合并的按钮事件处理
const onAction = () => {
  if (props.status === '运行') {
    emit('stop')
  } else {
    emit('start')
  }
}

// 下拉框展开时刷新任务列表
const onDropdownVisibleChange = (open: boolean) => {
  if (open) {
    emit('refresh-tasks')
  }
}
</script>

<style scoped>
.task-control {
  margin-bottom: 16px;
  border-radius: 12px;
  background-color: var(--ant-color-bg-container);
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

.cycle-preview {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--ant-color-border-secondary);
}

.cycle-preview-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 10px;
}

.cycle-preview-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.cycle-preview-meta {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.cycle-preview-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.cycle-preview-item {
  min-width: 0;
  padding: 10px 12px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
}

.cycle-preview-item.is-running {
  border-color: var(--ant-color-primary-border);
  background: var(--ant-color-primary-bg);
}

.cycle-preview-item.is-empty {
  border-style: dashed;
  background: transparent;
}

.cycle-preview-name {
  min-height: 20px;
  overflow: hidden;
  color: var(--ant-color-text);
  font-size: 13px;
  font-weight: 600;
  line-height: 20px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cycle-preview-time {
  min-height: 20px;
  margin-top: 2px;
  color: var(--ant-color-primary);
  font-size: 13px;
  font-weight: 500;
  line-height: 20px;
}

.cycle-preview-item.is-empty .cycle-preview-name,
.cycle-preview-item.is-empty .cycle-preview-time {
  color: var(--ant-color-text-secondary);
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

  .cycle-preview-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
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
