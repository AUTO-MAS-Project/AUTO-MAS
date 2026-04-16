<template>
  <div class="task-control">
    <div class="control-card">
      <div class="control-row">
        <a-space size="middle">
          <a-select
            v-if="status !== '杩愯'"
            v-model:value="localSelectedTaskId"
            placeholder="閫夋嫨浠诲姟椤?
            style="width: 200px"
            :loading="taskOptionsLoading"
            :options="taskOptions"
            :disabled="disabled"
            size="large"
            @change="onTaskChange"
            @dropdownVisibleChange="onDropdownVisibleChange"
          />
          <a-select
            v-if="status !== '杩愯'"
            v-model:value="localSelectedMode"
            placeholder="閫夋嫨妯″紡"
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
              <span class="label">浠诲姟锛?/span>
              <span class="value">{{ runningTaskLabel }}</span>
            </span>
            <span class="divider">|</span>
            <span class="info-item">
              <span class="label">妯″紡锛?/span>
              <span class="value">{{ runningModeLabel }}</span>
            </span>
          </div>
        </a-space>
        <div class="control-spacer"></div>
        <a-space size="middle">
          <a-button
            :type="status === '杩愯' ? 'default' : 'primary'"
            :danger="status === '杩愯'"
            :disabled="
              status === '杩愯' ? false : !localSelectedTaskId || !localSelectedMode || disabled
            "
            size="large"
            @click="onAction"
          >
            <template #icon>
              <StopOutlined v-if="status === '杩愯'" />
              <PlayCircleOutlined v-else />
            </template>
            {{ status === '杩愯' ? '鍋滄浠诲姟' : '寮€濮嬫墽琛? }}
          </a-button>
        </a-space>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { PlayCircleOutlined, StopOutlined } from '@ant-design/icons-vue'
import { type ComboBoxItem, type TaskCreateMode } from '@/api'
import { type SchedulerStatus, TASK_MODE_OPTIONS } from './schedulerConstants'

interface Props {
  selectedTaskId: string | null
  selectedMode: TaskCreateMode | null
  taskOptions: ComboBoxItem[]
  taskOptionsLoading: boolean
  status: SchedulerStatus
  disabled?: boolean
  runningTaskLabel?: string
  runningModeLabel?: string
}

interface Emits {
  (e: 'update:selectedTaskId', value: string | null): void

  (e: 'update:selectedMode', value: TaskCreateMode | null): void

  (e: 'start'): void

  (e: 'stop'): void

  (e: 'update:runningTaskLabel', value: string): void

  (e: 'update:runningTaskLabel', value: string): void

  (e: 'update:runningModeLabel', value: string): void

  (e: 'refresh-tasks'): void
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
})

const emit = defineEmits<Emits>()

// 鏈湴鐘舵€侊紝鐢ㄤ簬鍙屽悜缁戝畾
const localSelectedTaskId = ref(props.selectedTaskId)
const localSelectedMode = ref(props.selectedMode)

// 妯″紡閫夐」
const modeOptions = TASK_MODE_OPTIONS

// 杩愯鏃剁殑鏄剧ず鏂囨湰 - 鐩存帴浣跨敤 props锛屼笉鍐嶉渶瑕佹湰鍦?ref
// const runningTaskLabel = ref('')
// const runningModeLabel = ref('')

// 鐩戝惉鐘舵€佸彉鍖栵紝璁板綍杩愯鏃剁殑鏂囨湰淇℃伅
watch(
  () => props.status,
  (newStatus) => {
    if (newStatus === '杩愯') {
      const taskOption = props.taskOptions.find(opt => opt.value === props.selectedTaskId)
      const taskLabel = taskOption?.label || props.selectedTaskId || ''
      emit('update:runningTaskLabel', taskLabel)

      const modeOption = modeOptions.find(opt => opt.value === props.selectedMode)
      const modeLabel = modeOption?.label || props.selectedMode || ''
      emit('update:runningModeLabel', modeLabel)
    }
  }
)


// 鐩戝惉 props 鍙樺寲锛屽悓姝ュ埌鏈湴鐘舵€?
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

// 浜嬩欢澶勭悊
const onTaskChange = (value: string) => {
  emit('update:selectedTaskId', value)
}

const onModeChange = (value: TaskCreateMode) => {
  emit('update:selectedMode', value)
}

// 鍚堝苟鐨勬寜閽簨浠跺鐞?
const onAction = () => {
  if (props.status === '杩愯') {
    emit('stop')
  } else {
    emit('start')
  }
}

// 涓嬫媺妗嗗睍寮€鏃跺埛鏂颁换鍔″垪琛?
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

/* 鍝嶅簲寮?- 绉诲姩绔€傞厤 */
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

