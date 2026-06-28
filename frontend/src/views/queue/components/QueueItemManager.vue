<template>
  <a-card title="任务列表" class="queue-item-card">
    <template #extra>
      <a-space>
        <a-button
          type="primary"
          :loading="loading"
          :disabled="isEditingDisabled"
          @click="addQueueItem"
        >
          <template #icon>
            <PlusOutlined />
          </template>
          添加任务
        </a-button>
      </a-space>
    </template>

    <!-- 使用vuedraggable替换a-table实现拖拽功能 -->
    <div class="draggable-table-container">
      <!-- 表头 -->
      <div class="draggable-table-header">
        <div class="header-cell drag-cell"></div>
        <div class="header-cell index-cell">序号</div>
        <div class="header-cell script-cell" :class="{ 'script-cell-wide': !showCycleConfig }">
          脚本任务
        </div>
        <div v-if="showCycleConfig" class="header-cell cycle-cell">循环配置</div>
        <div class="header-cell actions-cell">操作</div>
      </div>

      <!-- 拖拽内容区域 -->
      <draggable
        v-model="queueItems"
        group="queueItems"
        item-key="id"
        :animation="200"
        :disabled="isEditingDisabled"
        ghost-class="ghost"
        chosen-class="chosen"
        drag-class="drag"
        handle=".drag-handle"
        class="draggable-container"
        @end="onDragEnd"
      >
        <template #item="{ element: record, index }">
          <div class="draggable-row" :class="{ 'row-dragging': isEditingDisabled }">
            <div class="row-cell drag-cell">
              <span class="drag-handle" title="拖拽排序" aria-label="拖拽排序">
                <span class="drag-dots" aria-hidden="true"></span>
              </span>
            </div>
            <div class="row-cell index-cell">{{ index + 1 }}</div>
            <div class="row-cell script-cell" :class="{ 'script-cell-wide': !showCycleConfig }">
              <div class="script-editor">
                <a-select
                  v-model:value="record.script"
                  size="middle"
                  class="script-select"
                  placeholder="请选择脚本"
                  :options="scriptOptions"
                  allow-clear
                  :disabled="isEditingDisabled"
                  @change="updateQueueItemScript(record)"
                />
                <div v-if="showCycleConfig" class="script-enabled-control">
                  <span class="script-enabled-label">任务开关</span>
                  <a-switch
                    :checked="record.scheduleEnabled"
                    size="small"
                    checked-children="开"
                    un-checked-children="关"
                    :disabled="isEditingDisabled"
                    @change="(value: unknown) => handleScheduleEnabledChange(record, value)"
                  />
                </div>
              </div>
            </div>
            <div v-if="showCycleConfig" class="row-cell cycle-cell">
              <div class="cycle-panel">
                <div class="cycle-panel-row">
                  <a-select
                    v-model:value="record.scheduleMode"
                    size="middle"
                    class="cycle-mode-select"
                    :disabled="isEditingDisabled"
                    @change="(value: unknown) => handleScheduleModeChange(record, value)"
                  >
                    <a-select-option value="interval">间隔</a-select-option>
                    <a-select-option value="fixed_time">固定时间</a-select-option>
                  </a-select>
                  <template v-if="record.scheduleMode === 'interval'">
                    <a-input-number
                      v-model:value="record.intervalMinutes"
                      size="middle"
                      class="interval-input"
                      addon-after="分钟"
                      :min="1"
                      :max="10080"
                      :disabled="isEditingDisabled"
                      @change="(value: unknown) => handleIntervalMinutesChange(record, value)"
                    />
                    <a-select
                      v-model:value="record.intervalAnchor"
                      size="middle"
                      class="anchor-select"
                      :disabled="isEditingDisabled"
                      @change="(value: unknown) => handleIntervalAnchorChange(record, value)"
                    >
                      <a-select-option value="start">从开始算</a-select-option>
                      <a-select-option value="finish">从结束算</a-select-option>
                    </a-select>
                  </template>
                  <template v-else>
                    <a-time-picker
                      :value="toTimeValue(record.scheduleTime)"
                      format="HH:mm"
                      size="middle"
                      class="schedule-time-picker"
                      :disabled="isEditingDisabled"
                      @update:value="
                        (value: Dayjs | null) => handleScheduleTimeDraft(record, value)
                      "
                      @change="
                        (_value: Dayjs | null, value: string) =>
                          commitScheduleTime(record, value || '00:00')
                      "
                      @open-change="(open: boolean) => handleScheduleTimeOpenChange(record, open)"
                    />
                    <a-select
                      v-model:value="record.scheduleDays"
                      mode="multiple"
                      size="middle"
                      class="days-select"
                      :options="weekdayOptions"
                      :disabled="isEditingDisabled"
                      @change="(value: unknown) => handleScheduleDaysChange(record, value)"
                    >
                      <template #tagRender="{ value, closable, onClose }">
                        <a-tag
                          class="weekday-compact-tag"
                          :closable="closable"
                          @mousedown.prevent
                          @close="onClose"
                        >
                          {{ formatWeekdayShort(value) }}
                        </a-tag>
                      </template>
                    </a-select>
                  </template>
                </div>
                <div class="cycle-panel-row cycle-next-row">
                  <span class="next-run-label">插入一次</span>
                  <a-date-picker
                    :value="toDateTimeValue(record.nextRunAt)"
                    show-time
                    format="YYYY-MM-DD HH:mm:ss"
                    size="middle"
                    class="next-run-picker"
                    placeholder="不插入"
                    :disabled="isEditingDisabled"
                    @update:value="(value: Dayjs | null) => handleNextRunDraft(record, value)"
                    @change="
                      (_value: Dayjs | null, value: string) =>
                        commitNextRunAt(record, value || emptyDateTime)
                    "
                    @open-change="(open: boolean) => handleNextRunOpenChange(record, open)"
                  />
                </div>
              </div>
            </div>
            <div class="row-cell actions-cell">
              <a-space>
                <a-popconfirm
                  title="确定要删除这个任务吗？"
                  ok-text="确定"
                  cancel-text="取消"
                  @confirm="deleteQueueItem(record.id)"
                >
                  <a-button size="middle" danger :disabled="isEditingDisabled">
                    <DeleteOutlined />
                    删除
                  </a-button>
                </a-popconfirm>
              </a-space>
            </div>
          </div>
        </template>
      </draggable>

      <!-- 空状态 -->
      <div v-if="queueItems.length === 0" class="empty-state">
        <div class="empty-content">
          <img src="../../../assets/NoData.png" alt="无数据" class="empty-image" />
        </div>
      </div>
    </div>
  </a-card>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, nextTick, watch } from 'vue'
import { message } from 'ant-design-vue'
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons-vue'
import draggable from 'vuedraggable'
import dayjs from 'dayjs'
import type { Dayjs } from 'dayjs'
import { Service } from '@/api'
import type { ComboBoxItem } from '@/api/models/ComboBoxItem'
import type { QueueItem_Schedule } from '@/api/models/QueueItem_Schedule'
const logger = window.electronAPI.getLogger('队列项管理')

// Props
type QueueItemRecord = {
  id: string
  script: string | null
  scheduleEnabled: boolean
  scheduleMode: ScheduleMode
  scheduleDays: ScheduleDays
  scheduleTime: string
  intervalMinutes: number
  intervalAnchor: IntervalAnchor
  nextRunAt: string
  lastCycleStartedAt?: string
  lastCycleFinishedAt?: string
}

type ScheduleMode = NonNullable<QueueItem_Schedule['Mode']>
type ScheduleDays = NonNullable<QueueItem_Schedule['Days']>
type Weekday = ScheduleDays[number]
type IntervalAnchor = NonNullable<QueueItem_Schedule['IntervalAnchor']>
type QueueItemSchedulePatch = Partial<QueueItem_Schedule>

type DragEndEvent = {
  oldIndex?: number
  newIndex?: number
}

interface Props {
  queueId: string
  queueItems: QueueItemRecord[]
  showCycleConfig?: boolean
  disabled?: boolean
}

const props = defineProps<Props>()
const showCycleConfig = computed(() => props.showCycleConfig ?? true)
const isEditingDisabled = computed(() => loading.value || Boolean(props.disabled))

const ensureEditable = () => {
  if (!props.disabled) return true
  message.warning('循环队列正在运行，停止后才能修改配置')
  return false
}

// Emits
const emit = defineEmits<{
  refresh: []
}>()

// 响应式数据
const loading = ref(false)
const isDraggingQueueItem = ref(false)
const pendingScheduleTimeById = ref<Record<string, string>>({})
const pendingNextRunAtById = ref<Record<string, string>>({})

// 选项数据
const scriptOptions = ref<ComboBoxItem[]>([])
const weekdayOptions: Array<{ label: string; value: Weekday }> = [
  { label: '周一', value: 'Monday' },
  { label: '周二', value: 'Tuesday' },
  { label: '周三', value: 'Wednesday' },
  { label: '周四', value: 'Thursday' },
  { label: '周五', value: 'Friday' },
  { label: '周六', value: 'Saturday' },
  { label: '周日', value: 'Sunday' },
]
const weekdayValues = weekdayOptions.map(item => item.value)
const weekdayShortMap: Record<string, string> = {
  Monday: '一',
  Tuesday: '二',
  Wednesday: '三',
  Thursday: '四',
  Friday: '五',
  Saturday: '六',
  Sunday: '日',
}

const emptyDateTime = '2000-01-01 00:00:00'
const cycleScheduleUpdatedEvent = 'queue-cycle-schedule-updated'

const normalizeScheduleEnabled = (value: QueueItem_Schedule['Enabled']) => value ?? true
const normalizeScheduleMode = (value: QueueItem_Schedule['Mode']): ScheduleMode =>
  value ?? 'fixed_time'
const normalizeScheduleDays = (value: QueueItem_Schedule['Days']): ScheduleDays => value ?? []
const normalizeScheduleTime = (value: QueueItem_Schedule['Time']) => value ?? '00:00'
const normalizeIntervalMinutes = (value: QueueItem_Schedule['IntervalMinutes']) => value ?? 480
const normalizeIntervalAnchor = (value: QueueItem_Schedule['IntervalAnchor']): IntervalAnchor =>
  value ?? 'start'
const normalizeNextRunAt = (value: QueueItem_Schedule['NextRunAt']) => value ?? emptyDateTime

const isScheduleMode = (value: unknown): value is ScheduleMode =>
  value === 'fixed_time' || value === 'interval'
const isIntervalAnchor = (value: unknown): value is IntervalAnchor =>
  value === 'start' || value === 'finish'
const isWeekday = (value: unknown): value is Weekday => weekdayValues.includes(value as Weekday)

const notifyCycleScheduleUpdated = () => {
  window.dispatchEvent(
    new CustomEvent(cycleScheduleUpdatedEvent, {
      detail: { queueId: props.queueId },
    })
  )
}

const toTimeValue = (value: string) => {
  const [hour = 0, minute = 0] = String(value || '00:00')
    .split(':')
    .map(Number)
  return dayjs().hour(hour).minute(minute).second(0).millisecond(0)
}

const toDateTimeValue = (value: string) => {
  if (!value || value === emptyDateTime) return null
  const parsed = dayjs(value || emptyDateTime, 'YYYY-MM-DD HH:mm:ss')
  return parsed.isValid() ? parsed : null
}

const formatTimeValue = (value: Dayjs | null) => {
  return value?.isValid() ? value.format('HH:mm') : '00:00'
}

const formatDateTimeValue = (value: Dayjs | null) => {
  return value?.isValid() ? value.format('YYYY-MM-DD HH:mm:ss') : emptyDateTime
}

const formatWeekdayShort = (value: unknown) => {
  return weekdayShortMap[String(value)] || String(value)
}

const applySchedulePatchToRecord = (record: QueueItemRecord, patch: QueueItemSchedulePatch) => {
  if ('Enabled' in patch) record.scheduleEnabled = normalizeScheduleEnabled(patch.Enabled)
  if ('Mode' in patch) record.scheduleMode = normalizeScheduleMode(patch.Mode)
  if ('Days' in patch) record.scheduleDays = normalizeScheduleDays(patch.Days)
  if ('Time' in patch) record.scheduleTime = normalizeScheduleTime(patch.Time)
  if ('IntervalMinutes' in patch)
    record.intervalMinutes = normalizeIntervalMinutes(patch.IntervalMinutes)
  if ('IntervalAnchor' in patch)
    record.intervalAnchor = normalizeIntervalAnchor(patch.IntervalAnchor)
  if ('NextRunAt' in patch) record.nextRunAt = normalizeNextRunAt(patch.NextRunAt)
}

const handleScheduleEnabledChange = async (record: QueueItemRecord, value: unknown) => {
  await updateQueueItemSchedule(record, { Enabled: Boolean(value) })
}

const handleScheduleModeChange = async (record: QueueItemRecord, value: unknown) => {
  if (!isScheduleMode(value)) return
  await updateQueueItemSchedule(record, { Mode: value })
}

const handleIntervalMinutesChange = async (record: QueueItemRecord, value: unknown) => {
  const minutes = typeof value === 'number' ? value : Number(value)
  await updateQueueItemSchedule(record, { IntervalMinutes: minutes || 1 })
}

const handleIntervalAnchorChange = async (record: QueueItemRecord, value: unknown) => {
  if (!isIntervalAnchor(value)) return
  await updateQueueItemSchedule(record, { IntervalAnchor: value })
}

const handleScheduleDaysChange = async (record: QueueItemRecord, value: unknown) => {
  const days = Array.isArray(value) ? value.filter(isWeekday) : []
  await updateQueueItemSchedule(record, { Days: days })
}

const handleScheduleTimeDraft = (record: QueueItemRecord, value: Dayjs | null) => {
  const time = formatTimeValue(value)
  pendingScheduleTimeById.value[record.id] = time
  record.scheduleTime = time
}

const commitScheduleTime = async (record: QueueItemRecord, value?: string) => {
  const hasDraft = Object.prototype.hasOwnProperty.call(pendingScheduleTimeById.value, record.id)
  if (value === undefined && !hasDraft) return

  const time = value || pendingScheduleTimeById.value[record.id] || '00:00'
  delete pendingScheduleTimeById.value[record.id]
  await updateQueueItemSchedule(record, { Time: time })
}

const handleScheduleTimeOpenChange = (record: QueueItemRecord, open: boolean) => {
  if (!open) {
    commitScheduleTime(record)
  }
}

const handleNextRunDraft = (record: QueueItemRecord, value: Dayjs | null) => {
  const nextRunAt = formatDateTimeValue(value)
  pendingNextRunAtById.value[record.id] = nextRunAt
  record.nextRunAt = nextRunAt
}

const commitNextRunAt = async (record: QueueItemRecord, value?: string) => {
  const hasDraft = Object.prototype.hasOwnProperty.call(pendingNextRunAtById.value, record.id)
  if (value === undefined && !hasDraft) return

  const nextRunAt = value || pendingNextRunAtById.value[record.id] || emptyDateTime
  delete pendingNextRunAtById.value[record.id]
  await updateQueueItemSchedule(record, { NextRunAt: nextRunAt })
}

const handleNextRunOpenChange = (record: QueueItemRecord, open: boolean) => {
  if (!open) {
    commitNextRunAt(record)
  }
}

// 计算属性 - 使用props传入的数据
const queueItems = ref(props.queueItems)

// 监听props变化
watch(
  () => props.queueItems,
  newQueueItems => {
    if (!isDraggingQueueItem.value) {
      queueItems.value = newQueueItems
    }
  },
  { deep: true }
)

// 加载脚本选项
const loadOptions = async () => {
  try {
    logger.info('开始加载脚本选项...')
    // 使用正确的API获取脚本下拉框选项
    const scriptsResponse = await Service.getScriptComboxApiInfoComboxScriptPost()
    logger.debug(`脚本API响应: ${JSON.stringify(scriptsResponse)}`)

    if (scriptsResponse.code === 200) {
      logger.debug(`脚本API响应数据: ${JSON.stringify(scriptsResponse.data)}`)
      // 直接使用接口返回的combox选项
      scriptOptions.value = scriptsResponse.data || []
      logger.debug(`处理后的脚本选项: ${JSON.stringify(scriptOptions.value)}`)
    } else {
      logger.error(`脚本API响应错误: ${JSON.stringify(scriptsResponse)}`)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载脚本选项失败: ${errorMsg}`)
  }
}

// 更新队列项脚本
const updateQueueItemScript = async (record: QueueItemRecord) => {
  if (!ensureEditable()) return

  try {
    const response = await Service.updateItemApiQueueItemUpdatePost({
      queueId: props.queueId,
      queueItemId: record.id,
      data: {
        Info: {
          ScriptId: record.script,
        },
      },
    })

    if (response.code === 200) {
      notifyCycleScheduleUpdated()
    } else {
      message.error('脚本更新失败: ' + (response.message || '未知错误'))
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`更新脚本失败: ${errorMsg}`)
    message.error(`更新脚本失败: ${errorMsg}`)
  }
}

const updateQueueItemSchedule = async (record: QueueItemRecord, patch: QueueItemSchedulePatch) => {
  if (!ensureEditable()) return

  try {
    const schedulePatch = { ...patch }
    const response = await Service.updateItemApiQueueItemUpdatePost({
      queueId: props.queueId,
      queueItemId: record.id,
      data: {
        Schedule: schedulePatch,
      },
    })

    if (response.code === 200) {
      applySchedulePatchToRecord(record, schedulePatch)
      notifyCycleScheduleUpdated()
    } else {
      message.error('循环配置保存失败: ' + (response.message || '未知错误'))
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`循环配置保存失败: ${errorMsg}`)
    message.error(`循环配置保存失败: ${errorMsg}`)
  }
}

// 添加队列项
const addQueueItem = async () => {
  if (!ensureEditable()) return

  try {
    loading.value = true

    // 直接创建队列项，默认ScriptId为null（未选择）
    const createResponse = await Service.addItemApiQueueItemAddPost({
      queueId: props.queueId,
    })

    if (createResponse.code === 200 && createResponse.queueItemId) {
      notifyCycleScheduleUpdated()
      emit('refresh')
    } else {
      message.error('任务添加失败: ' + (createResponse.message || '未知错误'))
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`添加任务失败: ${errorMsg}`)
    message.error(`添加任务失败: ${errorMsg}`)
  } finally {
    loading.value = false
  }
}

// 删除队列项
const deleteQueueItem = async (itemId: string) => {
  if (!ensureEditable()) return

  try {
    const response = await Service.deleteItemApiQueueItemDeletePost({
      queueId: props.queueId,
      queueItemId: itemId,
    })

    if (response.code === 200) {
      // 确保删除后刷新数据
      notifyCycleScheduleUpdated()
      emit('refresh')
    } else {
      message.error('删除队列项失败: ' + (response.message || '未知错误'))
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`删除队列项失败: ${errorMsg}`)
    message.error(`删除队列项失败: ${errorMsg}`)
  }
}

// 拖拽结束处理函数
const onDragEnd = async (evt: DragEndEvent) => {
  if (!ensureEditable()) return

  // 如果位置没有变化，直接返回
  if (evt.oldIndex === evt.newIndex) {
    return
  }

  isDraggingQueueItem.value = true

  try {
    loading.value = true

    // 构造排序后的ID列表
    const sortedIds = queueItems.value.map(item => item.id)

    // 调用排序API
    const response = await Service.reorderItemApiQueueItemOrderPost({
      queueId: props.queueId,
      indexList: sortedIds,
    })

    if (response.code === 200) {
      // 刷新数据以确保与服务器同步
      notifyCycleScheduleUpdated()
      emit('refresh')
    } else {
      message.error('更新任务顺序失败: ' + (response.message || '未知错误'))
      // 如果失败，刷新数据恢复原状态
      emit('refresh')
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`拖拽排序失败: ${errorMsg}`)
    message.error(`更新任务顺序失败: ${errorMsg}`)
    // 如果失败，刷新数据恢复原状态
    emit('refresh')
  } finally {
    loading.value = false
    nextTick(() => {
      isDraggingQueueItem.value = false
    })
  }
}

// 初始化
onMounted(() => {
  loadOptions()
})
</script>

<style scoped>
.queue-item-card {
  margin-bottom: 24px;
}

.queue-item-card :deep(.ant-card-head-title) {
  font-size: 18px;
  font-weight: 600;
}

/* 表格样式优化 */
.queue-table {
  width: 100% !important;
  max-width: 100% !important;
}

.queue-table :deep(.ant-table-wrapper) {
  width: 100% !important;
  max-width: 100% !important;
}

/* 禁用所有滚动条，让表格自动延伸 */
:deep(.ant-table-wrapper) {
  overflow: visible !important;
}

:deep(.ant-table-container) {
  overflow: visible !important;
  max-height: none !important;
  height: auto !important;
}

:deep(.ant-table-body) {
  overflow: visible !important;
  max-height: none !important;
  height: auto !important;
}

:deep(.ant-table-content) {
  overflow: visible !important;
  max-height: none !important;
  height: auto !important;
}

:deep(.ant-table-tbody) {
  overflow: visible !important;
}

:deep(.ant-table) {
  font-size: 14px;
  table-layout: auto;
  width: 100%;
  overflow: visible !important;
}

/* 列宽度控制 */
:deep(.ant-table-thead > tr > th:nth-child(1)) {
  width: 80px !important;
  min-width: 80px !important;
  max-width: 80px !important;
}

:deep(.ant-table-thead > tr > th:nth-child(2)) {
  width: auto !important;
  min-width: 120px !important;
}

:deep(.ant-table-thead > tr > th:nth-child(3)) {
  width: 180px !important;
  min-width: 180px !important;
  max-width: 180px !important;
}

:deep(.ant-table-tbody > tr > td:nth-child(1)) {
  width: 80px !important;
  min-width: 80px !important;
  max-width: 80px !important;
}

:deep(.ant-table-tbody > tr > td:nth-child(2)) {
  width: auto !important;
  min-width: 120px !important;
}

:deep(.ant-table-tbody > tr > td:nth-child(3)) {
  width: 180px !important;
  min-width: 180px !important;
  max-width: 180px !important;
}

/* 强制移除任何可能的滚动条 */
:deep(.ant-table-wrapper),
:deep(.ant-table-container),
:deep(.ant-table-body),
:deep(.ant-table-content),
:deep(.ant-table),
:deep(.ant-table-tbody) {
  scrollbar-width: none !important;
  /* Firefox */
  -ms-overflow-style: none !important;
  /* IE/Edge */
}

:deep(.ant-table-wrapper)::-webkit-scrollbar,
:deep(.ant-table-container)::-webkit-scrollbar,
:deep(.ant-table-body)::-webkit-scrollbar,
:deep(.ant-table-content)::-webkit-scrollbar,
:deep(.ant-table)::-webkit-scrollbar,
:deep(.ant-table-tbody)::-webkit-scrollbar {
  display: none !important;
  /* Chrome/Safari */
}

/* 表格行和列样式 */
:deep(.ant-table-tbody > tr > td) {
  padding: 8px 12px;
  border-bottom: 1px solid var(--ant-color-border);
}

:deep(.ant-table-thead > tr > th) {
  font-weight: 600;
  padding: 8px 12px;
  text-align: center;
  background-color: var(--ant-color-bg-container);
  border-bottom: 1px solid var(--ant-color-border);
}

/* 脚本名称列特殊处理 */
:deep(.ant-table-tbody > tr > td:nth-child(2)) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  word-break: break-all;
}

:deep(.ant-table-thead > tr > th:nth-child(2)) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 确保列内容正确显示 */
:deep(.ant-table-thead > tr > th) {
  text-align: center;
  vertical-align: middle;
}

:deep(.ant-table-tbody > tr > td) {
  text-align: center;
  vertical-align: middle;
}

:deep(.ant-table-cell) {
  text-align: center;
}

/* 表格整体布局优化 */
:deep(.ant-table-wrapper) {
  width: 100%;
  min-height: auto;
}

/* 确保表格不会被压缩 */
:deep(.ant-table-fixed-header) {
  scrollbar-width: none !important;
  -ms-overflow-style: none !important;
}

:deep(.ant-table-fixed-header)::-webkit-scrollbar {
  display: none !important;
}

/* 序号列样式 */
:deep(.ant-table-tbody > tr > td:first-child) {
  font-weight: 500;
  color: var(--ant-color-text-secondary);
}

/* 操作按钮布局 */
:deep(.ant-btn) {
  min-width: auto;
  height: 36px;
  padding: 0 12px;
  font-size: 14px;
  line-height: 1.5;
}

:deep(.ant-space) {
  gap: 6px !important;
}

:deep(.ant-space-item) {
  margin-right: 6px !important;
}

/* 操作列内容居中且不超出 */
:deep(.ant-table-tbody > tr > td:nth-child(3) .ant-space) {
  justify-content: center;
  width: 100%;
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
  background: var(--ant-color-bg-container);
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

/* 拖拽表格样式 */
.draggable-table-container {
  width: 100%;
  border: 1px solid var(--ant-color-border);
  border-radius: 6px;
  overflow: hidden;
}

.draggable-table-header {
  display: flex;
  background-color: var(--ant-color-fill-quaternary);
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
  width: 280px;
  min-width: 280px;
}

.script-cell-wide {
  flex: 1;
  width: auto;
  min-width: 320px;
}

.cycle-cell {
  flex: 1;
  min-width: 560px;
}

.actions-cell {
  width: 180px;
  min-width: 180px;
  max-width: 180px;
}

.draggable-container {
  min-height: 60px;
}

.draggable-row {
  display: flex;
  align-items: center;
  background: var(--ant-color-bg-container);
  border-bottom: 1px solid var(--ant-color-border);
  transition: all 0.2s ease;
  cursor: default;
}

.draggable-row:last-child {
  border-bottom: none;
}

.draggable-row:hover {
  background-color: var(--ant-color-fill-quaternary);
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
  width: 280px;
  min-width: 280px;
}

.row-cell.script-cell-wide {
  flex: 1;
  width: auto;
  min-width: 320px;
}

.row-cell.cycle-cell {
  flex: 1;
  min-width: 560px;
  justify-content: flex-start;
}

.row-cell.actions-cell {
  width: 180px;
  min-width: 180px;
  max-width: 180px;
}

.script-select {
  width: 100%;
  max-width: 260px;
}

.script-editor {
  display: flex;
  width: 100%;
  max-width: 260px;
  min-width: 0;
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
}

.script-enabled-control {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
}

.script-enabled-label {
  white-space: nowrap;
}

.cycle-panel {
  display: flex;
  width: 100%;
  min-width: 0;
  flex-direction: column;
  gap: 10px;
  padding: 4px 0;
}

.cycle-panel-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}

.cycle-next-row {
  color: var(--ant-color-text-secondary);
}

.cycle-mode-select {
  width: 112px;
}

.interval-input {
  width: 160px;
}

.anchor-select {
  width: 140px;
}

.schedule-time-picker {
  width: 112px;
}

.days-select {
  width: 300px;
}

.days-select :deep(.ant-select-selection-overflow) {
  flex-wrap: nowrap;
}

.days-select :deep(.ant-select-selection-overflow-item) {
  flex: 0 0 auto;
}

.weekday-compact-tag {
  margin-inline-end: 2px;
  padding-inline: 4px;
  line-height: 20px;
}

.weekday-compact-tag :deep(.ant-tag-close-icon) {
  margin-inline-start: 2px;
}

.next-run-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--ant-color-text-secondary);
}

.next-run-picker {
  width: 220px;
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
  padding: 40px 20px;
}

.empty-content {
  display: flex;
  justify-content: center;
}

.empty-image {
  max-width: 200px;
  height: auto;
  opacity: 0.9;
  filter: drop-shadow(0 8px 24px rgba(0, 0, 0, 0.1));
  transition: all 0.3s ease;
  position: relative;
  z-index: 1;
}

.empty-image:hover {
  transform: translateY(-4px);
  filter: drop-shadow(0 12px 32px rgba(0, 0, 0, 0.15));
}

/* 响应式设计 */
@media (max-width: 1200px) {
  .queue-items-grid {
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  }
}

@media (max-width: 768px) {
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
  .cycle-cell,
  .actions-cell {
    width: 100% !important;
    min-width: auto !important;
    max-width: none !important;
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
  min-height: 32px !important;
  line-height: 30px !important;
  box-shadow: none !important;
  text-align: center;
}

.script-select :deep(.ant-select-selection-item) {
  line-height: 30px !important;
  color: var(--ant-color-text) !important;
  font-weight: 500;
  padding: 0;
  margin: 0;
}

.script-select :deep(.ant-select-selection-placeholder) {
  line-height: 30px !important;
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
  height: 30px !important;
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
