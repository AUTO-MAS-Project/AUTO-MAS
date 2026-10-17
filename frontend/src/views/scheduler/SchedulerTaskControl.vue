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
          <div v-if="status === '运行'" class="running-info">
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
          <!-- 本次运行的托管/账号范围：队列按托管分组，脚本任务只有一个托管；收进浮层，长队列不再撑高启动卡 -->
          <a-popover
            v-if="showRunScope"
            v-model:open="scopeOpen"
            placement="bottomLeft"
            trigger="click"
          >
            <template #content>
              <div class="queue-scope">
                <div class="queue-scope-head">
                  <span class="queue-scope-title">{{ t('scheduler.control.runScopeTitle') }}</span>
                  <a-tooltip :title="t('scheduler.control.runScopeTip')">
                    <QuestionCircleOutlined class="queue-scope-help" />
                  </a-tooltip>
                  <template v-if="!scopeLoading && !scopeFailed">
                    <span class="queue-scope-summary">
                      {{
                        t('scheduler.control.runScopeSelected', {
                          selected: scopeSelectedCount,
                          total: scopeUserCount,
                        })
                      }}
                    </span>
                    <a-button
                      type="link"
                      size="small"
                      :disabled="scopeSelectedCount >= scopeUserCount"
                      @click="selectAllScopeUsers"
                    >
                      {{ t('scheduler.control.selectAllUsers') }}
                    </a-button>
                    <a-button
                      type="link"
                      size="small"
                      :disabled="scopeSelectedCount === 0"
                      @click="clearAllScopeUsers"
                    >
                      {{ t('scheduler.control.clearAllUsers') }}
                    </a-button>
                  </template>
                </div>
                <div v-if="scopeLoading" class="queue-scope-tip">
                  {{ t('scheduler.control.runScopeLoading') }}
                </div>
                <div v-else-if="scopeFailed" class="queue-scope-error">
                  {{ t('scheduler.control.runScopeLoadFailed') }}
                  <a-button type="link" size="small" @click="retryScope">
                    {{ t('scheduler.control.runScopeRetry') }}
                  </a-button>
                </div>
                <div v-else-if="!scopeRows.length" class="queue-scope-tip">
                  {{ t('scheduler.control.runScopeNoUsers') }}
                </div>
                <div v-else class="queue-scope-groups">
                  <div v-for="row in scopeRows" :key="row.group.scriptId" class="queue-scope-group">
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
                      @change="onScopeUserChange(row.group, user.value, $event)"
                    >
                      {{ user.label }}
                    </a-checkbox>
                    <!-- 托管里跑不了的账号也列出来，标出原因；勾选后端会拒绝，所以只展示 -->
                    <a-checkbox
                      v-for="user in row.group.disabledUsers ?? []"
                      :key="user.value"
                      :checked="false"
                      disabled
                    >
                      {{ user.label }}
                      <span class="queue-scope-user-note">
                        {{
                          t(
                            user.reason === 'expired'
                              ? 'scheduler.control.runScopeUserExpired'
                              : 'scheduler.control.runScopeUserDisabled'
                          )
                        }}
                      </span>
                    </a-checkbox>
                  </div>
                </div>
              </div>
            </template>
            <a-button size="large">
              <template #icon>
                <TeamOutlined />
              </template>
              {{ t('scheduler.control.runScopeTitle') }}
              <span
                v-if="!scopeLoading && !scopeFailed"
                class="queue-scope-count"
                :class="{ 'is-partial': scopePartial }"
              >
                {{ scopeSelectedCount }}/{{ scopeUserCount }}
              </span>
            </a-button>
          </a-popover>
        </a-space>
        <div class="control-spacer"></div>
        <a-space size="middle">
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
import { computed, ref, watch } from 'vue'
import {
  PlayCircleOutlined,
  QuestionCircleOutlined,
  StopOutlined,
  TeamOutlined,
} from '@ant-design/icons-vue'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import type { ComboBoxItem } from '@/api/models/ComboBoxItem'
import type { WSTaskCyclePreviewData } from '@/services/websocket/types'
import { type SchedulerStatus, TASK_MODE_OPTIONS } from './schedulerConstants'
import {
  countQueueSelectedUsers,
  countQueueUsers,
  selectedQueueUsers,
  withoutAllQueueUsers,
  withQueueGroupSelection,
  type QueueScopeDisabledUser,
  type QueueScopeGroup,
  type QueueUserScope,
} from './schedulerQueueScope'
import { scriptScopeGroup, scriptScopeSelection, toScriptUserIds } from './schedulerUserOptions'

const { t } = useI18n()

interface Props {
  selectedTaskId: string | null
  selectedMode: TaskCreateIn.mode | null
  resumeFromScriptId?: string | null
  resumeScriptOptions?: Array<{ label: string; value: string }>
  resumeScriptLoading?: boolean
  selectedUserIds?: string[]
  userOptions?: Array<{ label: string; value: string }>
  // 托管里未启用/天数耗尽的账号，只在面板里展示状态，不参与勾选
  userDisabledOptions?: QueueScopeDisabledUser[]
  userOptionsLoading?: boolean
  taskOptions: ComboBoxItem[]
  taskOptionsLoading: boolean
  status: SchedulerStatus
  disabled?: boolean
  runningTaskLabel?: string
  runningModeLabel?: string
  cycleNextList?: WSTaskCyclePreviewData[]
  // 队列任务本次运行的托管/账号范围，语义见 schedulerQueueScope.ts
  queueUserScope?: QueueUserScope
  queueScopeGroups?: QueueScopeGroup[]
  queueScopeLoading?: boolean
  queueScopeFailed?: boolean
}

interface Emits {
  (e: 'update:selectedTaskId', value: string | null): void

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
  userDisabledOptions: () => [],
  userOptionsLoading: false,
  runningTaskLabel: '',
  runningModeLabel: '',
  cycleNextList: () => [],
  queueUserScope: () => ({}),
  queueScopeGroups: () => [],
  queueScopeLoading: false,
  queueScopeFailed: false,
})

const emit = defineEmits<Emits>()

// 本地状态，用于双向绑定
const localSelectedTaskId = ref(props.selectedTaskId)
const localResumeFromScriptId = ref(props.resumeFromScriptId ?? null)

const cyclePreview = computed(() => (props.status === '运行' ? (props.cycleNextList ?? []) : []))

// 仅当选中队列任务时显示恢复脚本下拉框。
// 注：通过任务选项 label 的 "队列 - " 前缀判断，与 useSchedulerLogic.isQueueTask 保持同步。
const selectedTaskOption = computed(() =>
  props.taskOptions.find(opt => opt.value === localSelectedTaskId.value)
)

const selectedIsQueueTask = computed(() =>
  Boolean(selectedTaskOption.value?.label.startsWith('队列 - '))
)

const showResumeScriptSelect = computed(
  () => Boolean(localSelectedTaskId.value) && selectedIsQueueTask.value
)

// 脚本任务（非队列）也用「本次运行范围」挑账号，它是唯一入口：
// 单个脚本包成一个托管分组，勾选结果写回既有的 userIds。列表为空时同样保留面板以便重试。
const showScriptRunScope = computed(
  () => Boolean(selectedTaskOption.value) && !selectedIsQueueTask.value
)

const scriptScope = computed(() =>
  scriptScopeGroup(
    localSelectedTaskId.value,
    selectedTaskOption.value?.label ?? '',
    props.userOptions ?? [],
    props.userDisabledOptions ?? []
  )
)

// 数据来源按任务类型切换：队列用后端拉回的托管分组，脚本任务用该脚本自己的账号列表
const scopeGroups = computed<QueueScopeGroup[]>(() =>
  selectedIsQueueTask.value
    ? (props.queueScopeGroups ?? [])
    : scriptScope.value
      ? [scriptScope.value]
      : []
)

const scopeSelection = computed<QueueUserScope>(() =>
  selectedIsQueueTask.value
    ? (props.queueUserScope ?? {})
    : scriptScope.value
      ? scriptScopeSelection(scriptScope.value, props.selectedUserIds)
      : {}
)

const scopeLoading = computed(() =>
  selectedIsQueueTask.value ? props.queueScopeLoading === true : props.userOptionsLoading === true
)

// 脚本任务的账号列表加载失败只弹提示、不给重试态，所以这里只有队列会进失败分支
const scopeFailed = computed(() => selectedIsQueueTask.value && props.queueScopeFailed === true)

const scopeUserCount = computed(() => countQueueUsers(scopeGroups.value))

const scopeSelectedCount = computed(() =>
  countQueueSelectedUsers(scopeSelection.value, scopeGroups.value)
)

// 面板按托管平铺「账号 + 勾选框」，把勾选查表提前算好，避免模板里逐项线性查找
const scopeRows = computed(() =>
  scopeGroups.value.map(group => ({
    group,
    selected: new Set(selectedQueueUsers(scopeSelection.value, group)),
  }))
)

// 范围面板收进浮层，长队列不再把启动卡撑高、压缩下方的任务总览与日志
const scopeOpen = ref(false)

// 有账号被取消勾选时把计数标成警示色，收起后仍能一眼看出本次只跑一部分
const scopePartial = computed(
  () => scopeUserCount.value > 0 && scopeSelectedCount.value < scopeUserCount.value
)

// 运行态整卡换成 running-info，范围面板自然收起
const showRunScope = computed(
  () =>
    props.status !== '运行' &&
    Boolean(localSelectedTaskId.value) &&
    (selectedIsQueueTask.value || showScriptRunScope.value)
)

// 启动按钮的禁用条件集中在这里维护，模板里的表达式不再继续膨胀
const startDisabled = computed(() => {
  if (props.status === '运行') return false
  if (!localSelectedTaskId.value || props.disabled) return true
  if (!props.taskOptions.some(option => option.value === localSelectedTaskId.value)) return true
  // 脚本任务：账号还在加载、或显式取消到一个人都不剩时不让启动（与启动守卫同口径）
  if (showScriptRunScope.value) {
    return (
      props.userOptionsLoading ||
      (props.selectedUserIds !== undefined && scopeSelectedCount.value === 0)
    )
  }
  if (!selectedIsQueueTask.value) return false
  // 范围还没加载完先不让启动；加载失败则放开按钮，由点击后的报错说明原因
  if (props.queueScopeLoading) return true
  return scopeUserCount.value > 0 && scopeSelectedCount.value === 0
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

      const modeOption = TASK_MODE_OPTIONS.find(opt => opt.value === props.selectedMode)
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

const onResumeScriptChange = (value: string | undefined) => {
  emit('update:resumeFromScriptId', value ?? null)
}

const onResumeDropdownVisibleChange = (open: boolean) => {
  if (open) emit('refresh-resume-scripts')
}

// 队列任务写 queueUserIds（按脚本分组），脚本任务写既有的 userIds（undefined = 不限制）
const writeScopeSelection = (next: QueueUserScope) => {
  if (selectedIsQueueTask.value) {
    emit('update:queueUserScope', next)
    return
  }
  if (!scriptScope.value) return
  emit('update:selectedUserIds', toScriptUserIds(next, scriptScope.value))
}

// 全选 = 清掉所有显式勾选，回到「缺键即不限制」的默认口径
const selectAllScopeUsers = () => writeScopeSelection({})

const clearAllScopeUsers = () => writeScopeSelection(withoutAllQueueUsers(scopeGroups.value))

const onScopeUserChange = (
  group: QueueScopeGroup,
  userId: string,
  event: { target: { checked: boolean } }
) => {
  const current = selectedQueueUsers(scopeSelection.value, group)
  const next = event.target.checked ? [...current, userId] : current.filter(id => id !== userId)
  writeScopeSelection(withQueueGroupSelection(scopeSelection.value, group, next))
}

// 队列重拉范围，脚本任务重拉账号列表
const retryScope = () => {
  if (selectedIsQueueTask.value) emit('refresh-queue-scope')
  else emit('refresh-users')
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

/* 队列任务「本次运行范围」：收进浮层，宽度固定、账号多时浮层内部滚动 */
.queue-scope {
  width: 460px;
  max-width: 80vw;
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
  max-height: 45vh;
  overflow-y: auto;
}

.queue-scope-group {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

/* 不可勾选账号的原因标注 */
.queue-scope-user-note {
  margin-left: 6px;
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
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

/* 范围按钮上的「已选/总数」，只跑一部分账号时给个警示色 */
.queue-scope-count {
  margin-left: 8px;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--ant-color-text-secondary);
}

.queue-scope-count.is-partial {
  color: var(--ant-color-warning);
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
