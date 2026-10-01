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
            @dropdown-visible-change="onDropdownVisibleChange"
          />
          <a-select
            v-if="status !== '运行'"
            v-model:value="localSelectedMode"
            :placeholder="t('scheduler.control.modePlaceholder')"
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
              {{ t(option.labelKey) }}
            </a-select-option>
          </a-select>
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
          <a-select
            v-if="status !== '运行' && showUserSelect"
            v-model:value="localSelectedUserIds"
            mode="multiple"
            :placeholder="t('scheduler.control.runUsersPlaceholder')"
            style="width: 320px"
            :loading="userOptionsLoading"
            :options="userOptions || []"
            :disabled="disabled"
            :max-tag-count="'responsive'"
            allow-clear
            size="large"
            @change="onUserChange"
            @dropdown-visible-change="onUserDropdownVisibleChange"
          >
            <template #option="{ label, value }">
              <a-checkbox
                :checked="localSelectedUserIds.includes(value)"
                style="pointer-events: none"
              >
                {{ label }}
              </a-checkbox>
            </template>

            <template #dropdownRender="{ menuNode: menu }">
              <v-nodes :vnodes="menu" />
              <a-divider style="margin: 4px 0" />
              <a-space style="padding: 4px 8px" size="small">
                <a-button type="link" size="small" @click="selectAllUsers">
                  {{ t('scheduler.control.selectAllUsers') }}
                </a-button>
                <a-button type="link" size="small" @click="clearAllUsers">
                  {{ t('scheduler.control.clearAllUsers') }}
                </a-button>
              </a-space>
            </template>
          </a-select>
          <a-select
            v-if="status !== '运行' && showResumeScriptSelect"
            v-model:value="localResumeFromScriptId"
            :placeholder="t('scheduler.control.resumePlaceholder')"
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
              status === '运行'
                ? false
                : !localSelectedTaskId ||
                  !localSelectedMode ||
                  disabled ||
                  !taskOptions.some(option => option.value === localSelectedTaskId) ||
                  (showUserSelect && localSelectedUserIds.length === 0)
            "
            size="large"
            @click="onAction"
          >
            <template #icon>
              <StopOutlined v-if="status === '运行'" />
              <PlayCircleOutlined v-else />
            </template>
            {{ status === '运行' ? t('scheduler.control.stop') : t('scheduler.control.start') }}
          </a-button>
        </a-space>
      </div>

      <!-- 循环运行的下轮预览 -->
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
import { useI18n } from 'vue-i18n'
import { computed, defineComponent, ref, watch, type PropType, type VNode } from 'vue'
import { PlayCircleOutlined, StopOutlined } from '@ant-design/icons-vue'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import type { ComboBoxItem } from '@/api/models/ComboBoxItem'
import type { WSTaskCyclePreviewData } from '@/services/websocket/types'
import { type SchedulerStatus, getTaskModeOptions } from './schedulerConstants'

const { t } = useI18n()

const VNodes = defineComponent({
  props: {
    vnodes: {
      type: Object as PropType<VNode>,
      required: true,
    },
  },
  setup(props) {
    return () => props.vnodes
  },
})

interface Props {
  selectedTaskId: string | null
  selectedMode: TaskCreateIn.mode | null
  resumeFromScriptId?: string | null
  resumeScriptOptions?: Array<{ label: string; value: string }>
  resumeScriptLoading?: boolean
  selectedUserIds?: string[]
  userOptions?: Array<{ label: string; value: string }>
  userOptionsLoading?: boolean
  taskOptions: ComboBoxItem[]
  taskOptionsLoading: boolean
  status: SchedulerStatus
  disabled?: boolean
  runningTaskLabel?: string
  runningModeLabel?: string
  isCycleQueue?: boolean
  cycleNextList?: WSTaskCyclePreviewData[]
}

interface Emits {
  (e: 'update:selectedTaskId', value: string | null): void

  (e: 'update:selectedMode', value: TaskCreateIn.mode | null): void
  (e: 'update:resumeFromScriptId', value: string | null): void
  (e: 'update:selectedUserIds', value: string[]): void

  (e: 'start'): void

  (e: 'stop'): void

  (e: 'update:runningTaskLabel', value: string): void

  (e: 'update:runningModeLabel', value: string): void

  (e: 'refresh-tasks'): void
  (e: 'task-changed', value: string | null): void
  (e: 'refresh-resume-scripts'): void
  (e: 'refresh-users'): void
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
  resumeFromScriptId: null,
  resumeScriptOptions: () => [],
  resumeScriptLoading: false,
  selectedUserIds: () => [],
  userOptions: () => [],
  userOptionsLoading: false,
  runningTaskLabel: '',
  runningModeLabel: '',
  isCycleQueue: false,
  cycleNextList: () => [],
})

const emit = defineEmits<Emits>()

// 本地状态，用于双向绑定
const localSelectedTaskId = ref(props.selectedTaskId)
const localSelectedMode = ref(props.selectedMode)
const localResumeFromScriptId = ref(props.resumeFromScriptId ?? null)
const localSelectedUserIds = ref<string[]>([...(props.selectedUserIds ?? [])])

// 「循环运行」只对循环队列开放，其余任务仍然只有自动代理
const modeOptions = computed(() =>
  getTaskModeOptions(props.isCycleQueue ? null : [TaskCreateIn.mode.AUTO_PROXY])
)

const cyclePreview = computed(() => (props.status === '运行' ? (props.cycleNextList ?? []) : []))

// 仅当选中队列任务时显示恢复脚本下拉框。
// 注：通过任务选项 label 的 "队列 - " 前缀判断，与 useSchedulerLogic.isQueueTask 保持同步。
const showResumeScriptSelect = computed(() => {
  const selectedTaskId = localSelectedTaskId.value
  if (!selectedTaskId) return false

  const taskOption = props.taskOptions.find(opt => opt.value === selectedTaskId)
  return Boolean(taskOption?.label.startsWith('队列 - '))
})

// 脚本自动代理始终保留用户选择框，列表暂时为空时也可打开下拉重试加载。
const showUserSelect = computed(() => {
  if (localSelectedMode.value !== TaskCreateIn.mode.AUTO_PROXY) return false
  const taskOption = props.taskOptions.find(opt => opt.value === localSelectedTaskId.value)
  return Boolean(taskOption && !taskOption.label.startsWith('队列 - '))
})

// 运行时的显示文本 - 直接使用 props，不再需要本地 ref
// const runningTaskLabel = ref('')
// const runningModeLabel = ref('')

// 刷新页面时任务选项还没加载完，运行态文案会先落成裸 ID；选项到了再补成名称
watch(
  () => props.taskOptions,
  options => {
    if (props.status !== '运行' || !props.selectedTaskId) return
    if (props.runningTaskLabel && props.runningTaskLabel !== props.selectedTaskId) return
    const taskOption = options.find(opt => opt.value === props.selectedTaskId)
    if (taskOption?.label) emit('update:runningTaskLabel', taskOption.label)
  }
)

// 监听状态变化，记录运行时的文本信息
watch(
  () => props.status,
  newStatus => {
    if (newStatus === '运行') {
      const taskOption = props.taskOptions.find(opt => opt.value === props.selectedTaskId)
      const taskLabel = taskOption?.label || props.selectedTaskId || ''
      emit('update:runningTaskLabel', taskLabel)

      const modeOption = modeOptions.value.find(opt => opt.value === props.selectedMode)
      const modeLabel = modeOption ? t(modeOption.labelKey) : props.selectedMode || ''
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

watch(modeOptions, options => {
  if (options.some(option => option.value === localSelectedMode.value)) return
  const nextMode = options[0]?.value ?? null
  localSelectedMode.value = nextMode
  emit('update:selectedMode', nextMode)
})

watch(
  () => props.resumeFromScriptId,
  newVal => {
    localResumeFromScriptId.value = newVal ?? null
  },
  { immediate: true }
)

watch(
  () => props.selectedUserIds,
  newVal => {
    localSelectedUserIds.value = [...(newVal ?? [])]
  },
  { immediate: true, deep: true }
)

// 事件处理
const onTaskChange = (value: string) => {
  emit('update:selectedTaskId', value)
  emit('task-changed', value)
}

const onModeChange = (value: TaskCreateIn.mode) => {
  emit('update:selectedMode', value)
}

const onResumeScriptChange = (value: string | undefined) => {
  emit('update:resumeFromScriptId', value ?? null)
}

const onResumeDropdownVisibleChange = (open: boolean) => {
  if (open) emit('refresh-resume-scripts')
}

const onUserChange = (value: string[]) => {
  emit('update:selectedUserIds', [...value])
}

const selectAllUsers = () => {
  const value = (props.userOptions ?? []).map(item => item.value)
  localSelectedUserIds.value = value
  emit('update:selectedUserIds', [...value])
}

const clearAllUsers = () => {
  localSelectedUserIds.value = []
  emit('update:selectedUserIds', [])
}

const onUserDropdownVisibleChange = (open: boolean) => {
  if (open) emit('refresh-users')
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
