<template>
  <div class="task-control">
    <div class="control-card">
      <div class="control-row">
        <a-space size="middle">
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
            size="large"
          />
          <a-select
            v-model:value="localSelectedMode"
            placeholder="选择模式"
            style="width: 120px"
            :disabled="disabled"
            @change="onModeChange"
            size="large"
          >
            <a-select-option v-for="option in modeOptions" :key="option.value" :value="option.value">
              {{ option.label }}
            </a-select-option>
          </a-select>
        </a-space>
        <div class="control-spacer"></div>
        <a-space size="middle">
          <a-button
            @click="onAction"
            :type="status === '运行' ? 'default' : 'primary'"
            :danger="status === '运行'"
            :disabled="status === '运行' ? false : (!localSelectedTaskId || !localSelectedMode || disabled)"
            size="large"
          >
            <template #icon>
              <StopOutlined v-if="status === '运行'" />
              <PlayCircleOutlined v-else />
            </template>
            {{ status === '运行' ? '停止任务' : '开始执行' }}
          </a-button>
        </a-space>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
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

// 合并的按钮事件处理
const onAction = () => {
  if (props.status === '运行') {
    emit('stop')
  } else {
    emit('start')
  }
}

// 任务选项过滤
const filterTaskOption = (input: string, option: any) => {
  return (option?.label || '').toLowerCase().includes(input.toLowerCase())
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
</style>