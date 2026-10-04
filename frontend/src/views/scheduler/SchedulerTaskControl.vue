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
            :disabled="startDisabled"
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
      <!-- 队列任务本次运行的托管/账号范围：常驻展示、账号旁勾选，默认全勾 -->
      <div v-if="showQueueScope" class="queue-scope">
        <div class="queue-scope-head">
          <span class="queue-scope-title">{{ t('scheduler.control.runScopeTitle') }}</span>
          <a-tooltip :title="t('scheduler.control.runScopeTip')">
            <QuestionCircleOutlined class="queue-scope-help" />
          </a-tooltip>
          <a-tooltip :title="queueScopeToggleText">
            <a-button
              type="text"
              size="small"
              class="queue-scope-toggle"
              :aria-expanded="queueScopeExpanded"
              :aria-label="queueScopeToggleText"
              @click="toggleQueueScope"
            >
              <DownOutlined
                class="queue-scope-chevron"
                :class="{ 'is-collapsed': !queueScopeExpanded }"
              />
            </a-button>
          </a-tooltip>
          <template v-if="!queueScopeLoading && !queueScopeFailed">
            <span class="queue-scope-summary">
              {{
                t('scheduler.control.runScopeSelected', {
                  selected: queueScopeSelectedCount,
                  total: queueScopeUserCount,
                })
              }}
            </span>
            <a-button
              type="link"
              size="small"
              :disabled="queueScopeSelectedCount >= queueScopeUserCount"
              @click="selectAllQueueUsers"
            >
              {{ t('scheduler.control.selectAllUsers') }}
            </a-button>
            <a-button
              type="link"
              size="small"
              :disabled="queueScopeSelectedCount === 0"
              @click="clearAllQueueUsers"
            >
              {{ t('scheduler.control.clearAllUsers') }}
            </a-button>
          </template>
        </div>
        <div v-if="queueScopeLoading" class="queue-scope-tip">
          {{ t('scheduler.control.runScopeLoading') }}
        </div>
        <div v-else-if="queueScopeFailed" class="queue-scope-error">
          {{ t('scheduler.control.runScopeLoadFailed') }}
          <a-button type="link" size="small" @click="retryQueueScope">
            {{ t('scheduler.control.runScopeRetry') }}
          </a-button>
        </div>
        <div v-else-if="queueScopeExpanded && !queueScopeRows.length" class="queue-scope-tip">
          {{ t('scheduler.control.runScopeNoUsers') }}
        </div>
        <div v-else-if="queueScopeExpanded" class="queue-scope-groups">
          <div v-for="row in queueScopeRows" :key="row.group.scriptId" class="queue-scope-group">
            <span class="queue-scope-group-name" :title="row.group.scriptName">
              {{ row.group.scriptName }}
            </span>
            <span v-if="!row.group.users.length" class="queue-scope-group-empty">
              {{ t('scheduler.control.runScopeNoUsers') }}
            </span>
            <a-checkbox
              v-for="user in row.group.users"
              :key="user.value"
              :checked="row.selected.has(user.value)"
              @change="onQueueUserChange(row.group, user.value, $event)"
            >
              {{ user.label }}
            </a-checkbox>
          </div>
        </div>
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
import {
  DownOutlined,
  PlayCircleOutlined,
  QuestionCircleOutlined,
  StopOutlined,
} from '@ant-design/icons-vue'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import type { ComboBoxItem } from '@/api/models/ComboBoxItem'
import type { WSTaskCyclePreviewData } from '@/services/websocket/types'
import { type SchedulerStatus, getTaskModeOptions } from './schedulerConstants'
import {
  countQueueSelectedUsers,
  countQueueUsers,
  selectedQueueUsers,
  withoutAllQueueUsers,
  withQueueGroupSelection,
  type QueueScopeGroup,
  type QueueUserScope,
} from './schedulerQueueScope'

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
  // 队列任务本次运行的托管/账号范围，语义见 schedulerQueueScope.ts
  queueUserScope?: QueueUserScope
  queueScopeGroups?: QueueScopeGroup[]
  queueScopeLoading?: boolean
  queueScopeFailed?: boolean
}

interface Emits {
  (e: 'update:selectedTaskId', value: string | null): void

  (e: 'update:selectedMode', value: TaskCreateIn.mode | null): void
  (e: 'update:resumeFromScriptId', value: string | null): void
  (e: 'update:selectedUserIds', value: string[] | undefined): void

  (e: 'start'): void

  (e: 'stop'): void

  (e: 'update:runningTaskLabel', value: string): void

  (e: 'update:runningModeLabel', value: string): void

  (e: 'refresh-tasks'): void
  (e: 'task-changed', value: string | null): void
  (e: 'refresh-resume-scripts'): void
  (e: 'refresh-users'): void

  (e: 'update:queueUserScope', value: QueueUserScope): void
  (e: 'refresh-queue-scope'): void
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
  resumeFromScriptId: null,
  resumeScriptOptions: () => [],
  resumeScriptLoading: false,
  selectedUserIds: undefined,
  userOptions: () => [],
  userOptionsLoading: false,
  runningTaskLabel: '',
  runningModeLabel: '',
  isCycleQueue: false,
  cycleNextList: () => [],
  queueUserScope: () => ({}),
  queueScopeGroups: () => [],
  queueScopeLoading: false,
  queueScopeFailed: false,
})

const emit = defineEmits<Emits>()

// 本地状态，用于双向绑定
const localSelectedTaskId = ref(props.selectedTaskId)
const localSelectedMode = ref(props.selectedMode)
const localResumeFromScriptId = ref(props.resumeFromScriptId ?? null)
const localSelectedUserIds = computed({
  get: () => props.selectedUserIds ?? props.userOptions.map(option => option.value),
  set: value => {
    // 仅用户主动勾满列表时切回全选；选项刷新不能把显式子集扩大成全部用户。
    const allSelected =
      props.userOptions.length > 0 &&
      value.length === props.userOptions.length &&
      props.userOptions.every(option => value.includes(option.value))
    emit('update:selectedUserIds', allSelected ? undefined : [...value])
  },
})

// 「循环运行」只对循环队列开放，其余任务仍然只有自动代理
const modeOptions = computed(() =>
  getTaskModeOptions(props.isCycleQueue ? null : [TaskCreateIn.mode.AUTO_PROXY])
)

const cyclePreview = computed(() => (props.status === '运行' ? (props.cycleNextList ?? []) : []))

// 仅当选中队列任务时显示恢复脚本下拉框与本次运行范围。
// 注：通过任务选项 label 的 "队列 - " 前缀判断，与 useSchedulerLogic.isQueueTask 保持同步。
const selectedIsQueueTask = computed(() => {
  const taskOption = props.taskOptions.find(opt => opt.value === localSelectedTaskId.value)
  return Boolean(taskOption?.label.startsWith('队列 - '))
})

const showResumeScriptSelect = computed(
  () => Boolean(localSelectedTaskId.value) && selectedIsQueueTask.value
)

// 脚本自动代理始终保留用户选择框，列表暂时为空时也可打开下拉重试加载。
const showUserSelect = computed(() => {
  if (localSelectedMode.value !== TaskCreateIn.mode.AUTO_PROXY) return false
  const taskOption = props.taskOptions.find(opt => opt.value === localSelectedTaskId.value)
  return Boolean(taskOption && !taskOption.label.startsWith('队列 - '))
})

const queueScopeUserCount = computed(() => countQueueUsers(props.queueScopeGroups ?? []))

const queueScopeSelectedCount = computed(() =>
  countQueueSelectedUsers(props.queueUserScope ?? {}, props.queueScopeGroups ?? [])
)

// 面板按托管平铺「账号 + 勾选框」，把勾选查表提前算好，避免模板里逐项线性查找
const queueScopeRows = computed(() =>
  (props.queueScopeGroups ?? []).map(group => ({
    group,
    selected: new Set(selectedQueueUsers(props.queueUserScope ?? {}, group)),
  }))
)

// 长的队列会把启动卡撑高、压缩下方的任务总览与日志，允许收起只留标题
const queueScopeExpanded = ref(true)

const queueScopeToggleText = computed(() =>
  t(
    queueScopeExpanded.value
      ? 'scheduler.control.runScopeCollapse'
      : 'scheduler.control.runScopeExpand'
  )
)

// 运行态整卡换成 running-info，范围面板自然收起
const showQueueScope = computed(
  () => props.status !== '运行' && Boolean(localSelectedTaskId.value) && selectedIsQueueTask.value
)

// 启动按钮的禁用条件集中在这里维护，模板里的表达式不再继续膨胀
const startDisabled = computed(() => {
  if (props.status === '运行') return false
  if (!localSelectedTaskId.value || !localSelectedMode.value || props.disabled) return true
  if (!props.taskOptions.some(option => option.value === localSelectedTaskId.value)) return true
  if (
    showUserSelect.value &&
    (props.userOptionsLoading ||
      (props.selectedUserIds !== undefined && localSelectedUserIds.value.length === 0))
  ) {
    return true
  }
  if (!selectedIsQueueTask.value) return false
  // 范围还没加载完先不让启动；加载失败则放开按钮，由点击后的报错说明原因
  if (props.queueScopeLoading) return true
  return queueScopeUserCount.value > 0 && queueScopeSelectedCount.value === 0
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

const selectAllUsers = () => {
  emit('update:selectedUserIds', undefined)
}

const clearAllUsers = () => {
  localSelectedUserIds.value = []
}

const onUserDropdownVisibleChange = (open: boolean) => {
  if (open) emit('refresh-users')
}

// 全选 = 清掉所有显式勾选，回到「缺键即不限制」的默认口径
const selectAllQueueUsers = () => {
  emit('update:queueUserScope', {})
}

const clearAllQueueUsers = () => {
  emit('update:queueUserScope', withoutAllQueueUsers(props.queueScopeGroups ?? []))
}

const onQueueUserChange = (
  group: QueueScopeGroup,
  userId: string,
  event: { target: { checked: boolean } }
) => {
  const current = selectedQueueUsers(props.queueUserScope ?? {}, group)
  const next = event.target.checked ? [...current, userId] : current.filter(id => id !== userId)
  emit('update:queueUserScope', withQueueGroupSelection(props.queueUserScope ?? {}, group, next))
}

const retryQueueScope = () => {
  emit('refresh-queue-scope')
}

const toggleQueueScope = () => {
  queueScopeExpanded.value = !queueScopeExpanded.value
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

/* 队列任务「本次运行范围」：与启动栏同一张卡，用一条分隔线分区 */
.queue-scope {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--ant-color-border-secondary);
}

.queue-scope-head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}

.queue-scope-title {
  font-size: 13px;
  color: var(--ant-color-text);
}

.queue-scope-help {
  color: var(--ant-color-text-tertiary);
  cursor: help;
}

.queue-scope-toggle {
  padding: 0 4px;
  color: var(--ant-color-text-tertiary);
}

.queue-scope-chevron {
  font-size: 12px;
  transition: transform 0.2s ease;
}

.queue-scope-chevron.is-collapsed {
  transform: rotate(-90deg);
}

.queue-scope-summary {
  margin-left: 8px;
  font-size: 12px;
  color: var(--ant-color-text-secondary);
  font-variant-numeric: tabular-nums;
}

.queue-scope-error {
  margin-top: 4px;
  font-size: 12px;
  color: var(--ant-color-error);
}

.queue-scope-tip {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--ant-color-text-tertiary);
}

.queue-scope-groups {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 8px;
}

.queue-scope-group {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.queue-scope-group-empty {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}

.queue-scope-group-name {
  min-width: 96px;
  max-width: 200px;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  font-size: 13px;
  color: var(--ant-color-text-secondary);
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

  .queue-scope-group {
    gap: 8px;
  }

  .queue-scope-group-name {
    min-width: 0;
    max-width: 100%;
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
