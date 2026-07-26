<template>
  <a-card title="任务列表" class="queue-item-card">
    <template #extra>
      <a-space>
        <a-tag :color="cycleEnabled ? 'processing' : 'default'">
          {{ cycleEnabled ? '循环队列已启用' : '循环队列未启用' }}
        </a-tag>
        <a-button type="primary" :loading="loading" @click="addQueueItem">
          <template #icon>
            <PlusOutlined />
          </template>
          添加任务
        </a-button>
      </a-space>
    </template>

    <div class="cycle-help">
      调度参数始终可以预先配置；只有队列的“循环运行”开启后，宿主才会按父级顺序执行已到期项目。
    </div>

    <div class="draggable-table-container">
      <div class="draggable-table-header">
        <div class="header-cell drag-cell"></div>
        <div class="header-cell index-cell">序号</div>
        <div class="header-cell script-cell">脚本任务</div>
        <div class="header-cell schedule-cell">循环调度</div>
        <div class="header-cell actions-cell">操作</div>
      </div>

      <draggable
        v-model="queueItems"
        group="queueItems"
        item-key="id"
        :animation="200"
        :disabled="loading"
        ghost-class="ghost"
        chosen-class="chosen"
        drag-class="drag"
        handle=".drag-handle"
        class="draggable-container"
        @start="onDragStart"
        @end="onDragEnd"
      >
        <template #item="{ element: record, index }">
          <div class="draggable-row" :class="{ 'row-dragging': loading }">
            <div class="row-cell drag-cell">
              <span class="drag-handle" title="拖拽排序" aria-label="拖拽排序">
                <span class="drag-dots" aria-hidden="true"></span>
              </span>
            </div>
            <div class="row-cell index-cell">{{ index + 1 }}</div>
            <div class="row-cell script-cell">
              <a-select
                :value="record.script"
                size="small"
                style="width: 200px"
                class="script-select"
                placeholder="请选择脚本"
                :options="scriptOptions"
                :disabled="loading"
                allow-clear
                @change="onScriptChange(record, $event)"
              />
            </div>
            <div class="row-cell schedule-cell">
              <div class="schedule-editor">
                <div class="schedule-row">
                  <span class="schedule-label">启用</span>
                  <a-switch
                    :checked="record.scheduleEnabled"
                    :disabled="loading"
                    @change="onScheduleEnabledChange(record, $event)"
                  />
                  <a-select
                    :value="record.scheduleMode"
                    class="schedule-mode"
                    size="small"
                    :disabled="loading"
                    @change="onScheduleModeChange(record, $event)"
                  >
                    <a-select-option value="fixed_time">固定时间</a-select-option>
                    <a-select-option value="interval">间隔运行</a-select-option>
                  </a-select>
                </div>

                <div v-if="record.scheduleMode === 'fixed_time'" class="schedule-row">
                  <a-input
                    :value="record.scheduleTime"
                    type="time"
                    size="small"
                    class="schedule-time"
                    :disabled="loading"
                    @blur="updateScheduleTime(record, $event)"
                  />
                  <a-checkbox-group
                    :value="record.scheduleDays"
                    :options="dayOptions"
                    :disabled="loading"
                    @change="onScheduleDaysChange(record, $event)"
                  />
                </div>

                <div v-else class="schedule-row">
                  <span class="schedule-label">每</span>
                  <a-input-number
                    :value="record.intervalMinutes"
                    :min="1"
                    :max="10080"
                    size="small"
                    :disabled="loading"
                    @change="updateIntervalMinutes(record, $event)"
                  />
                  <span class="schedule-label">分钟</span>
                  <a-select
                    :value="record.intervalAnchor"
                    class="schedule-anchor"
                    size="small"
                    :disabled="loading"
                    @change="onIntervalAnchorChange(record, $event)"
                  >
                    <a-select-option value="start">从开始时间</a-select-option>
                    <a-select-option value="finish">从完成时间</a-select-option>
                  </a-select>
                </div>

                <div class="schedule-row schedule-meta">
                  <span class="schedule-label">下次</span>
                  <a-input
                    :value="displayNextRunAt(record.nextRunAt)"
                    size="small"
                    class="next-run-input"
                    placeholder="YYYY-MM-DD HH:mm:ss"
                    :disabled="loading"
                    @blur="updateNextRunAt(record, $event)"
                  />
                  <span v-if="hasRun(record)" class="last-run">
                    上次完成 {{ displayTimestamp(record.lastCycleFinishedAt) }}
                  </span>
                </div>
                <div class="schedule-row cycle-state-row">
                  <a-tag :color="cycleStateColor(record.cycleState)">
                    {{ cycleStateLabel(record.cycleState) }}
                  </a-tag>
                  <span v-if="record.cycleError" class="cycle-error" :title="record.cycleError">
                    {{ record.cycleError }}
                  </span>
                  <span v-else-if="record.cycleState === 'running'" class="cycle-run-id">
                    运行 ID {{ shortRunId(record.cycleRunId) }}
                  </span>
                  <span v-if="hasCycleUpdate(record)" class="cycle-updated-at">
                    更新于 {{ displayTimestamp(record.cycleUpdatedAt) }}
                  </span>
                </div>
              </div>
            </div>
            <div class="row-cell actions-cell">
              <a-popconfirm
                title="确定要删除这个任务吗？"
                ok-text="确定"
                cancel-text="取消"
                @confirm="deleteQueueItem(record.id)"
              >
                <a-button size="middle" danger :disabled="loading">
                  <DeleteOutlined />
                  删除
                </a-button>
              </a-popconfirm>
            </div>
          </div>
        </template>
      </draggable>

      <EmptyState
        v-if="queueItems.length === 0"
        compact
        title="暂无队列项"
        description="添加脚本任务后，可在这里调整执行顺序和循环计划。"
      />
    </div>
  </a-card>
</template>

<script setup lang="ts">
import { Service, type QueueItem_Schedule } from '@/api'
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { nextTick, onMounted, ref, watch } from 'vue'
import draggable from 'vuedraggable'
import EmptyState from '@/components/v6/EmptyState.vue'
import type { QueueItemRecord } from '../useQueueLogic'

const logger = window.electronAPI.getLogger('队列项管理')
const SENTINEL_TIMESTAMP = '2000-01-01 00:00:00'

type ScheduleDay =
  | 'Monday'
  | 'Tuesday'
  | 'Wednesday'
  | 'Thursday'
  | 'Friday'
  | 'Saturday'
  | 'Sunday'

interface Props {
  queueId: string
  queueItems: QueueItemRecord[]
  cycleEnabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  cycleEnabled: false,
})
const emit = defineEmits<{
  refresh: [queueId: string]
}>()

const loading = ref(false)
const isDraggingQueueItem = ref(false)
const scriptOptions = ref<Array<{ label: string; value: string | null }>>([])
const dayOptions: Array<{ label: string; value: ScheduleDay }> = [
  { label: '一', value: 'Monday' },
  { label: '二', value: 'Tuesday' },
  { label: '三', value: 'Wednesday' },
  { label: '四', value: 'Thursday' },
  { label: '五', value: 'Friday' },
  { label: '六', value: 'Saturday' },
  { label: '日', value: 'Sunday' },
]

const cloneItem = (item: QueueItemRecord): QueueItemRecord => ({
  ...item,
  scheduleDays: [...item.scheduleDays],
})
const cloneItems = (items: QueueItemRecord[]): QueueItemRecord[] => items.map(cloneItem)
const queueItems = ref<QueueItemRecord[]>(cloneItems(props.queueItems))
let pendingPropsSync = false

const syncFromProps = () => {
  queueItems.value = cloneItems(props.queueItems)
  pendingPropsSync = false
}

watch(
  [() => props.queueId, () => props.queueItems],
  () => {
    if (isDraggingQueueItem.value || loading.value) {
      pendingPropsSync = true
      return
    }
    syncFromProps()
  },
  { deep: true }
)

const normalizeScriptId = (value: unknown): string | null =>
  typeof value === 'string' && value.length > 0 ? value : null
const normalizeMode = (value: unknown): 'fixed_time' | 'interval' =>
  value === 'interval' ? 'interval' : 'fixed_time'
const normalizeAnchor = (value: unknown): 'start' | 'finish' =>
  value === 'finish' ? 'finish' : 'start'
const normalizeDays = (value: unknown): ScheduleDay[] =>
  Array.isArray(value)
    ? value.filter((day): day is ScheduleDay => dayOptions.some(option => option.value === day))
    : []
const eventValue = (event: Event): string => (event.target as HTMLInputElement | null)?.value ?? ''
const displayTimestamp = (value: string): string =>
  !value || value === SENTINEL_TIMESTAMP ? '尚未运行' : value
const displayNextRunAt = (value: string): string => (value === SENTINEL_TIMESTAMP ? '' : value)
const hasRun = (record: QueueItemRecord): boolean =>
  record.lastCycleFinishedAt !== SENTINEL_TIMESTAMP
const hasCycleUpdate = (record: QueueItemRecord): boolean =>
  record.cycleUpdatedAt !== SENTINEL_TIMESTAMP
const shortRunId = (runId: string): string => runId.slice(0, 8) || '待分配'
const cycleStateLabel = (state: QueueItemRecord['cycleState']): string =>
  ({
    idle: '尚未运行',
    running: '运行中',
    succeeded: '上次成功',
    failed: '上次失败',
    cancelled: '上次取消',
  })[state]
const cycleStateColor = (
  state: QueueItemRecord['cycleState']
): 'default' | 'processing' | 'success' | 'error' | 'warning' =>
  ({
    idle: 'default',
    running: 'processing',
    succeeded: 'success',
    failed: 'error',
    cancelled: 'warning',
  })[state] as 'default' | 'processing' | 'success' | 'error' | 'warning'

const finishMutation = async () => {
  loading.value = false
  await nextTick()
  if (pendingPropsSync && !isDraggingQueueItem.value) syncFromProps()
}

const loadOptions = async () => {
  try {
    const scriptsResponse = await Service.getScriptComboxApiInfoComboxScriptPost()
    if (scriptsResponse.code === 200) {
      scriptOptions.value = scriptsResponse.data || []
    } else {
      logger.error(`脚本 API 响应错误: ${JSON.stringify(scriptsResponse)}`)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载脚本选项失败: ${errorMsg}`)
  }
}

const updateQueueItem = async (
  record: QueueItemRecord,
  data: Record<string, unknown>,
  applyLocal: () => void,
  failureLabel: string
) => {
  if (loading.value) return
  const requestQueueId = props.queueId
  try {
    loading.value = true
    const response = await Service.updateItemApiQueueItemUpdatePost({
      queueId: requestQueueId,
      queueItemId: record.id,
      data,
    })
    if (response.code !== 200) {
      message.error(`${failureLabel}: ${response.message || '未知错误'}`)
      return
    }
    if (props.queueId === requestQueueId) {
      applyLocal()
      emit('refresh', requestQueueId)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`${failureLabel}: ${errorMsg}`)
    message.error(`${failureLabel}: ${errorMsg}`)
  } finally {
    await finishMutation()
  }
}

const updateQueueItemScript = async (record: QueueItemRecord, script: string | null) => {
  if (script === record.script) return
  await updateQueueItem(
    record,
    { Info: { ScriptId: script } },
    () => {
      record.script = script
    },
    '脚本更新失败'
  )
}

const onScriptChange = (record: QueueItemRecord, value: unknown) =>
  updateQueueItemScript(record, normalizeScriptId(value))

const applySchedulePatch = (record: QueueItemRecord, patch: QueueItem_Schedule) => {
  if (patch.Enabled !== undefined && patch.Enabled !== null) record.scheduleEnabled = patch.Enabled
  if (patch.Mode) record.scheduleMode = patch.Mode
  if (patch.Days) record.scheduleDays = [...patch.Days]
  if (patch.Time) record.scheduleTime = patch.Time
  if (patch.IntervalMinutes !== undefined && patch.IntervalMinutes !== null)
    record.intervalMinutes = patch.IntervalMinutes
  if (patch.IntervalAnchor) record.intervalAnchor = patch.IntervalAnchor
  if (patch.NextRunAt) record.nextRunAt = patch.NextRunAt
}

const updateSchedule = async (record: QueueItemRecord, patch: QueueItem_Schedule) => {
  await updateQueueItem(
    record,
    { Schedule: patch },
    () => applySchedulePatch(record, patch),
    '循环调度更新失败'
  )
}

const onScheduleEnabledChange = (record: QueueItemRecord, value: unknown) =>
  updateSchedule(record, { Enabled: Boolean(value) })
const onScheduleModeChange = (record: QueueItemRecord, value: unknown) =>
  updateSchedule(record, { Mode: normalizeMode(value) })
const onScheduleDaysChange = (record: QueueItemRecord, value: unknown) =>
  updateSchedule(record, { Days: normalizeDays(value) })
const onIntervalAnchorChange = (record: QueueItemRecord, value: unknown) =>
  updateSchedule(record, { IntervalAnchor: normalizeAnchor(value) })

const updateScheduleTime = async (record: QueueItemRecord, event: Event) => {
  const value = eventValue(event)
  if (!/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(value)) {
    message.error('运行时间必须使用 HH:mm 格式')
    return
  }
  if (value !== record.scheduleTime) await updateSchedule(record, { Time: value })
}

const updateIntervalMinutes = async (record: QueueItemRecord, value: unknown) => {
  const minutes = Number(value)
  if (!Number.isInteger(minutes) || minutes < 1 || minutes > 10080) {
    message.error('间隔分钟数必须是 1 到 10080 的整数')
    return
  }
  if (minutes !== record.intervalMinutes) await updateSchedule(record, { IntervalMinutes: minutes })
}

const updateNextRunAt = async (record: QueueItemRecord, event: Event) => {
  const value = eventValue(event).trim() || SENTINEL_TIMESTAMP
  if (
    value !== SENTINEL_TIMESTAMP &&
    !/^\d{4}-\d{2}-\d{2} (?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d$/.test(value)
  ) {
    message.error('下次运行时间必须使用 YYYY-MM-DD HH:mm:ss 格式')
    return
  }
  if (value !== record.nextRunAt) await updateSchedule(record, { NextRunAt: value })
}

const addQueueItem = async () => {
  if (loading.value) return
  const requestQueueId = props.queueId
  try {
    loading.value = true
    const response = await Service.addItemApiQueueItemAddPost({ queueId: requestQueueId })
    if (response.code === 200 && response.queueItemId) {
      if (props.queueId === requestQueueId) emit('refresh', requestQueueId)
    } else {
      message.error(`任务添加失败: ${response.message || '未知错误'}`)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`添加任务失败: ${errorMsg}`)
    message.error(`添加任务失败: ${errorMsg}`)
  } finally {
    await finishMutation()
  }
}

const deleteQueueItem = async (itemId: string) => {
  if (loading.value) return
  const requestQueueId = props.queueId
  try {
    loading.value = true
    const response = await Service.deleteItemApiQueueItemDeletePost({
      queueId: requestQueueId,
      queueItemId: itemId,
    })
    if (response.code === 200) {
      if (props.queueId === requestQueueId) {
        queueItems.value = queueItems.value.filter(item => item.id !== itemId)
        emit('refresh', requestQueueId)
      }
    } else {
      message.error(`删除队列项失败: ${response.message || '未知错误'}`)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`删除队列项失败: ${errorMsg}`)
    message.error(`删除队列项失败: ${errorMsg}`)
  } finally {
    await finishMutation()
  }
}

let dragStartSnapshot: QueueItemRecord[] = []
let dragStartQueueId = ''

const onDragStart = () => {
  isDraggingQueueItem.value = true
  dragStartQueueId = props.queueId
  dragStartSnapshot = cloneItems(queueItems.value)
}

const onDragEnd = async (event: { oldIndex?: number; newIndex?: number }) => {
  if (event.oldIndex === event.newIndex) {
    dragStartSnapshot = []
    isDraggingQueueItem.value = false
    if (props.queueId !== dragStartQueueId) syncFromProps()
    else pendingPropsSync = false
    dragStartQueueId = ''
    return
  }

  const requestQueueId = props.queueId
  const rollbackLocalOrder = () => {
    if (dragStartSnapshot.length > 0) queueItems.value = cloneItems(dragStartSnapshot)
  }

  try {
    loading.value = true
    const response = await Service.reorderItemApiQueueItemOrderPost({
      queueId: requestQueueId,
      indexList: queueItems.value.map(item => item.id),
    })
    if (response.code === 200) {
      if (props.queueId === requestQueueId) emit('refresh', requestQueueId)
    } else {
      rollbackLocalOrder()
      message.error(`更新任务顺序失败: ${response.message || '未知错误'}`)
    }
  } catch (error) {
    rollbackLocalOrder()
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`拖拽排序失败: ${errorMsg}`)
    message.error(`更新任务顺序失败: ${errorMsg}`)
    if (props.queueId === requestQueueId) emit('refresh', requestQueueId)
  } finally {
    loading.value = false
    dragStartSnapshot = []
    isDraggingQueueItem.value = false
    await nextTick()
    if (props.queueId !== requestQueueId) syncFromProps()
    else pendingPropsSync = false
    dragStartQueueId = ''
  }
}

onMounted(loadOptions)
</script>

<style scoped>
/* 队列页的两个管理区属于同一工作台：外层卡片弱化为透明容器,
   只保留轻量分节标题,避免 queue-workspace 卡片内再套白色卡片 */
.queue-item-card {
  margin: var(--v6-space-4) 0 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.queue-item-card :deep(.ant-card-head) {
  min-height: 52px;
  padding: 0;
  border-bottom: 1px solid var(--v6-color-border-subtle);
}

.queue-item-card :deep(.ant-card-head-title) {
  padding: var(--v6-space-3) 0;
  font-size: 15px;
  font-weight: 600;
}

.queue-item-card :deep(.ant-card-extra) {
  padding: var(--v6-space-2) 0;
}

.queue-item-card :deep(.ant-card-body) {
  padding: var(--v6-space-3) 0 0;
}

.cycle-help {
  margin-bottom: 12px;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
}

/* 操作按钮布局 */
:deep(.ant-btn) {
  min-width: auto;
  height: 32px;
  padding: 0 8px;
  font-size: 14px;
  line-height: 1.5;
}

:deep(.ant-space) {
  gap: 6px !important;
}

:deep(.ant-space-item) {
  margin-right: 6px !important;
}

/* 按钮图标样式调整 */
:deep(.ant-btn .anticon) {
  font-size: 14px;
}

/* 队列项列表样式 */
.queue-items-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.queue-item-row {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  background: var(--app-background-card-bg, var(--ant-color-bg-container));
  border: 1px solid var(--ant-color-border);
  border-radius: 6px;
  transition: all 0.2s ease;
}

.queue-item-row:hover {
  border-color: var(--ant-color-primary);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.item-left {
  flex: 0 0 120px;
}

.item-index {
  font-weight: 500;
  color: var(--ant-color-text);
  font-size: 14px;
}

.item-center {
  flex: 1;
  padding: 0 16px;
}

.script-name {
  color: var(--ant-color-text);
  font-size: 14px;
}

.item-right {
  flex: 0 0 auto;
  display: flex;
  gap: 8px;
}

/* 拖拽表格样式:窄容器下允许横向滚动兜底,避免撑破页面 */
.draggable-table-container {
  width: 100%;
  border: 1px solid var(--ant-color-border);
  border-radius: 6px;
  overflow-x: auto;
  overflow-y: hidden;
  scrollbar-color: var(--v6-color-border) transparent;
}

.draggable-table-header {
  display: flex;
  background-color: var(--app-background-card-elevated-bg, var(--ant-color-fill-quaternary));
  border-bottom: 1px solid var(--ant-color-border);
}

.header-cell {
  padding: 12px 16px;
  font-weight: 600;
  color: var(--ant-color-text);
  text-align: center;
  border-right: 1px solid var(--ant-color-border);
}

.header-cell:last-child {
  border-right: none;
}

.index-cell {
  width: 80px;
  min-width: 80px;
  max-width: 80px;
}

.drag-cell {
  width: 36px;
  min-width: 36px;
  max-width: 36px;
}

.script-cell {
  width: 220px;
  min-width: 220px;
}

.schedule-cell {
  flex: 1;
  /* 原 520px 导致行最小宽约 976px,窄容器必然溢出;
     调度编辑器内部 schedule-row 已支持 flex-wrap,300px 足够可用 */
  min-width: 300px;
}

.actions-cell {
  width: 120px;
  min-width: 120px;
  max-width: 120px;
}

.draggable-container {
  min-height: 60px;
}

.draggable-row {
  display: flex;
  align-items: center;
  background: var(--app-background-card-bg, var(--ant-color-bg-container));
  border-bottom: 1px solid var(--ant-color-border);
  transition: all 0.2s ease;
  cursor: default;
}

.draggable-row:last-child {
  border-bottom: none;
}

.draggable-row:hover {
  background-color: var(--app-background-card-elevated-bg, var(--ant-color-fill-quaternary));
}

.draggable-row.row-dragging {
  cursor: not-allowed;
}

.row-cell {
  padding: 12px 16px;
  text-align: center;
  border-right: 1px solid var(--ant-color-border);
  display: flex;
  align-items: center;
  justify-content: center;
}

.row-cell:last-child {
  border-right: none;
}

.row-cell.index-cell {
  width: 80px;
  min-width: 80px;
  max-width: 80px;
  font-weight: 500;
  color: var(--ant-color-text-secondary);
}

.row-cell.drag-cell {
  width: 36px;
  min-width: 36px;
  max-width: 36px;
}

.row-cell.script-cell {
  width: 220px;
  min-width: 220px;
}

.row-cell.schedule-cell {
  flex: 1;
  min-width: 300px;
  justify-content: flex-start;
  text-align: left;
}

.row-cell.actions-cell {
  width: 120px;
  min-width: 120px;
  max-width: 120px;
}

.schedule-editor {
  display: flex;
  width: 100%;
  flex-direction: column;
  gap: 8px;
}

.schedule-row {
  display: flex;
  min-height: 28px;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.schedule-label {
  color: var(--ant-color-text-secondary);
  white-space: nowrap;
}

.schedule-mode,
.schedule-anchor {
  width: 132px;
}

.schedule-time {
  width: 112px;
}

.schedule-meta {
  flex-wrap: nowrap;
}

.next-run-input {
  width: 172px;
}

.last-run {
  overflow: hidden;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cycle-state-row {
  min-width: 0;
  flex-wrap: nowrap;
}

.cycle-error,
.cycle-run-id,
.cycle-updated-at {
  overflow: hidden;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cycle-error {
  max-width: 260px;
  color: var(--ant-color-error);
}

.cycle-run-id {
  max-width: 150px;
}

.cycle-updated-at {
  margin-left: auto;
}

/* 拖拽状态样式 */
.ghost {
  opacity: 0 !important;
  background: transparent !important;
  border-color: transparent !important;
  box-shadow: none !important;
}

.chosen {
  cursor: grabbing !important;
}

.drag {
  transform: rotate(3deg);
  opacity: 1 !important;
}

.drag .draggable-row {
  opacity: 1 !important;
  transition: none !important;
}

.drag-handle {
  width: 16px;
  height: 20px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--ant-color-text-tertiary);
  background: transparent;
  border: none;
  cursor: grab;
  user-select: none;
}

.drag-handle:active {
  cursor: grabbing;
}

.drag-dots {
  width: 10px;
  height: 16px;
  display: block;
  background-image: radial-gradient(currentColor 1.2px, transparent 1.2px);
  background-size: 5px 5px;
  opacity: 0.65;
}

.drag-handle:hover .drag-dots {
  opacity: 0.85;
}

/* 空状态样式 */
.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 132px;
  padding: var(--v6-space-4);
}

/* 响应式设计:按队列页容器宽度响应(侧栏挤压时同样生效),不用视口 @media */
@container queue-page (max-width: 1200px) {
  .queue-items-grid {
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  }
}

@container queue-page (max-width: 768px) {
  .queue-items-grid {
    grid-template-columns: 1fr;
  }

  .queue-item-card-item {
    padding: 12px;
  }

  .draggable-row {
    flex-direction: column;
    align-items: stretch;
  }

  .row-cell,
  .header-cell {
    border-right: none;
    border-bottom: 1px solid var(--ant-color-border);
  }

  .row-cell:last-child,
  .header-cell:last-child {
    border-bottom: none;
  }

  .index-cell,
  .drag-cell,
  .script-cell,
  .schedule-cell,
  .actions-cell {
    width: 100% !important;
    min-width: auto !important;
    max-width: none !important;
  }

  .draggable-table-header {
    display: none;
  }

  .schedule-meta {
    flex-wrap: wrap;
  }
}

/* 标签样式 */
:deep(.ant-tag) {
  margin: 0;
  border-radius: 4px;
}

/* 脚本下拉框样式 - 使用与TimeSetManager.vue状态下拉框相同的样式 */
.script-select :deep(.ant-select-selector) {
  background: transparent !important;
  border: none !important;
  padding: 0 6px !important;
  min-height: 28px !important;
  line-height: 26px !important;
  box-shadow: none !important;
  text-align: center;
}

.script-select :deep(.ant-select-selection-item) {
  line-height: 26px !important;
  color: var(--ant-color-text) !important;
  font-weight: 500;
  padding: 0;
  margin: 0;
}

.script-select :deep(.ant-select-selection-placeholder) {
  line-height: 26px !important;
  color: var(--ant-color-text-placeholder) !important;
  padding: 0;
  margin: 0;
}

.script-select :deep(.ant-select-clear) {
  display: none !important;
}

.script-select :deep(.ant-select-selection-search) {
  margin: 0 !important;
  padding: 0;
}

.script-select :deep(.ant-select-selection-search-input) {
  padding: 0 !important;
  margin: 0 !important;
  height: 26px !important;
}

.script-select:hover :deep(.ant-select-selector) {
  border: none !important;
  box-shadow: none !important;
  background: transparent !important;
}

.script-select:focus-within :deep(.ant-select-selector),
.script-select.ant-select-focused :deep(.ant-select-selector) {
  border: none !important;
  box-shadow: none !important;
  background: transparent !important;
  outline: none !important;
}

.script-select :deep(.ant-select-selector):focus,
.script-select :deep(.ant-select-selector):focus-within {
  border: none !important;
  box-shadow: none !important;
  background: transparent !important;
  outline: none !important;
  cursor: default !important;
}

/* 下拉箭头样式 */
.script-select :deep(.ant-select-arrow) {
  right: 4px;
  color: var(--ant-color-text-tertiary);
  font-size: 10px;
}

.script-select :deep(.ant-select-arrow:hover) {
  color: var(--ant-color-primary);
}

/* 自定义下拉框样式 - 增加下拉菜单宽度 */
.script-select :deep(.ant-select-dropdown) {
  min-width: 200px !important;
  max-width: 300px !important;
}

.script-select :deep(.ant-select-item) {
  padding: 8px 12px !important;
}
</style>
