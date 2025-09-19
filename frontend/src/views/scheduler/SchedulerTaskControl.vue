<template>
  <div class="task-control">
    <div class="control-row">
      <a-select
        v-model:value="localSelectedTaskId"
        placeholder="选择任务项"
        style="width: 200px"
        :loading="taskOptionsLoading"
        :options="taskOptions"
        show-search
        :filter-option="filterTaskOption"
        :disabled="disabled"
        @change="onTaskChange"
      />
      <a-select
        v-model:value="localSelectedMode"
        placeholder="选择模式"
        style="width: 120px"
        :disabled="disabled"
        @change="onModeChange"
      >
        <a-select-option v-for="option in modeOptions" :key="option.value" :value="option.value">
          {{ option.label }}
        </a-select-option>
      </a-select>
      <div class="control-spacer"></div>
      <a-button
        v-if="status !== '运行'"
        type="primary"
        @click="onStart"
        :icon="h(PlayCircleOutlined)"
        :disabled="!canStart"
      >
        开始任务
      </a-button>
      <a-button v-else danger @click="onStop" :icon="h(StopOutlined)"> 中止任务</a-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, h, ref, watch } from 'vue'
import { PlayCircleOutlined, StopOutlined } from '@ant-design/icons-vue'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import type { ComboBoxItem } from '@/api/models/ComboBoxItem'
import { type SchedulerStatus, TASK_MODE_OPTIONS } from './schedulerConstants'

interface Props {
  selectedTaskId: string | null
  selectedMode: TaskCreateIn.mode | null
  taskOptions: ComboBoxItem[]
  taskOptionsLoading: boolean
  status: SchedulerStatus
  disabled?: boolean
}

interface Emits {
  (e: 'update:selectedTaskId', value: string | null): void

  (e: 'update:selectedMode', value: TaskCreateIn.mode | null): void

  (e: 'start'): void

  (e: 'stop'): void
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
})

const emit = defineEmits<Emits>()

// 本地状态，用于双向绑定
const localSelectedTaskId = ref(props.selectedTaskId)
const localSelectedMode = ref(props.selectedMode)

// 模式选项
const modeOptions = TASK_MODE_OPTIONS

// 计算属性
const canStart = computed(() => {
  return !!(localSelectedTaskId.value && localSelectedMode.value) && !props.disabled
})

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

// 事件处理
const onTaskChange = (value: string) => {
  emit('update:selectedTaskId', value)
}

const onModeChange = (value: TaskCreateIn.mode) => {
  emit('update:selectedMode', value)
}

const onStart = () => {
  emit('start')
}

const onStop = () => {
  emit('stop')
}

// 任务选项过滤
const filterTaskOption = (input: string, option: any) => {
  return (option?.label || '').toLowerCase().includes(input.toLowerCase())
}
</script>

<style scoped>
.task-control {
  margin-bottom: 16px;
}

.control-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 20px;
  background: var(--ant-color-bg-container);
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  transition: all 0.3s ease;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.control-row:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.control-label {
  font-weight: 500;
  color: var(--ant-color-text);
  white-space: nowrap;
}

.control-select {
  min-width: 200px;
}

.control-spacer {
  flex: 1;
}

.control-button {
  min-width: 100px;
}

/* 暗色模式适配 */
@media (prefers-color-scheme: dark) {
  .control-row {
    background: var(--ant-color-bg-container, #1f1f1f);
    border: 1px solid var(--ant-color-border, #424242);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
  }

  .control-row:hover {
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
  }

  .control-label {
    color: var(--ant-color-text, #ffffff);
  }
}

@media (max-width: 768px) {
  .control-row {
    flex-direction: column;
    align-items: stretch;
    padding: 16px;
  }

  .control-select {
    min-width: auto;
  }

  .control-spacer {
    display: none;
  }

  .control-button {
    width: 100%;
  }
}
</style>
