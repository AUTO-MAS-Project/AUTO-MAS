<template>
  <a-card :title="t('queue.item.cardTitle')" class="queue-item-card">
    <template #extra>
      <a-space>
        <a-button type="primary" :loading="loading" :disabled="locked" @click="addQueueItem">
          <template #icon>
            <PlusOutlined />
          </template>
          {{ t('queue.item.add') }}
        </a-button>
      </a-space>
    </template>

    <!-- 使用vuedraggable替换a-table实现拖拽功能 -->
    <div class="draggable-table-container">
      <!-- 表头 -->
      <div class="draggable-table-header">
        <div class="header-cell drag-cell"></div>
        <div class="header-cell index-cell">{{ t('queue.item.colIndex') }}</div>
        <div class="header-cell script-cell">{{ t('queue.item.colScript') }}</div>
        <div v-if="showCycleConfig" class="header-cell cycle-cell">
          {{ t('queue.cycle.colConfig') }}
        </div>
        <div class="header-cell actions-cell">{{ t('queue.item.colActions') }}</div>
      </div>

      <!-- 拖拽内容区域 -->
      <draggable
        v-model="queueItems"
        group="queueItems"
        item-key="id"
        :animation="200"
        :disabled="loading || locked"
        ghost-class="ghost"
        chosen-class="chosen"
        drag-class="drag"
        handle=".drag-handle"
        class="draggable-container"
        @end="onDragEnd"
      >
        <template #item="{ element: record, index }">
          <div class="draggable-row" :class="{ 'row-dragging': loading }">
            <div class="row-cell drag-cell">
              <span
                class="drag-handle"
                :title="t('queue.item.dragSort')"
                :aria-label="t('queue.item.dragSort')"
              >
                <span class="drag-dots" aria-hidden="true"></span>
              </span>
            </div>
            <div class="row-cell index-cell">{{ index + 1 }}</div>
            <div class="row-cell script-cell">
              <a-select
                v-model:value="record.script"
                size="small"
                style="width: 200px"
                class="script-select"
                :placeholder="t('queue.item.selectScript')"
                :options="scriptOptions"
                :disabled="locked"
                allow-clear
                @change="updateQueueItemScript(record)"
              />
            </div>
            <div v-if="showCycleConfig" class="row-cell cycle-cell">
              <div class="cycle-panel">
                <div class="cycle-line">
                  <a-switch
                    v-model:checked="record.schedule.Enabled"
                    size="small"
                    @change="saveSchedule(record, { Enabled: record.schedule.Enabled })"
                  />
                  <a-select
                    v-model:value="record.schedule.Mode"
                    size="small"
                    style="width: 104px"
                    :disabled="!record.schedule.Enabled"
                    @change="saveSchedule(record, { Mode: record.schedule.Mode })"
                  >
                    <a-select-option value="fixed_time">
                      {{ t('queue.cycle.modeFixed') }}
                    </a-select-option>
                    <a-select-option value="interval">
                      {{ t('queue.cycle.modeInterval') }}
                    </a-select-option>
                  </a-select>

                  <template v-if="record.schedule.Mode === 'interval'">
                    <a-input-number
                      v-model:value="record.schedule.IntervalMinutes"
                      size="small"
                      style="width: 104px"
                      :min="1"
                      :max="10080"
                      :disabled="!record.schedule.Enabled"
                      :addon-after="t('queue.cycle.minuteUnit')"
                      @change="saveInterval(record)"
                    />
                    <a-select
                      v-model:value="record.schedule.IntervalAnchor"
                      size="small"
                      style="width: 128px"
                      :disabled="!record.schedule.Enabled"
                      @change="saveSchedule(record, { IntervalAnchor: record.schedule.IntervalAnchor })"
                    >
                      <a-select-option value="start">
                        {{ t('queue.cycle.anchorStart') }}
                      </a-select-option>
                      <a-select-option value="finish">
                        {{ t('queue.cycle.anchorFinish') }}
                      </a-select-option>
                    </a-select>
                  </template>
                  <template v-else>
                    <a-time-picker
                      v-model:value="record.scheduleTimeValue"
                      format="HH:mm"
                      size="small"
                      style="width: 104px"
                      :placeholder="t('queue.time.selectTime')"
                      :disabled="!record.schedule.Enabled"
                      @change="saveScheduleTime(record)"
                    />
                    <a-select
                      v-model:value="record.schedule.Days"
                      mode="multiple"
                      size="small"
                      style="min-width: 168px"
                      :placeholder="t('queue.time.selectDays')"
                      :disabled="!record.schedule.Enabled"
                      :max-tag-count="3"
                      @change="saveSchedule(record, { Days: record.schedule.Days })"
                    >
                      <a-select-option value="Monday">{{ t('queue.time.Monday') }}</a-select-option>
                      <a-select-option value="Tuesday">
                        {{ t('queue.time.Tuesday') }}
                      </a-select-option>
                      <a-select-option value="Wednesday">
                        {{ t('queue.time.Wednesday') }}
                      </a-select-option>
                      <a-select-option value="Thursday">
                        {{ t('queue.time.Thursday') }}
                      </a-select-option>
                      <a-select-option value="Friday">{{ t('queue.time.Friday') }}</a-select-option>
                      <a-select-option value="Saturday">
                        {{ t('queue.time.Saturday') }}
                      </a-select-option>
                      <a-select-option value="Sunday">{{ t('queue.time.Sunday') }}</a-select-option>
                    </a-select>
                  </template>
                </div>

                <div class="cycle-line cycle-next-line">
                  <span class="cycle-next-text">
                    {{ t('queue.cycle.nextRun') }}
                    {{ formatNextRun(record.schedule.NextRunAt) }}
                  </span>
                  <a-button
                    type="link"
                    size="small"
                    :disabled="!record.schedule.Enabled"
                    @click="runOnce(record)"
                  >
                    {{ t('queue.cycle.runOnce') }}
                  </a-button>
                </div>
              </div>
            </div>
            <div class="row-cell actions-cell">
              <a-space>
                <a-popconfirm
                  :title="t('queue.item.deleteConfirm')"
                  :ok-text="t('queue.ok')"
                  :cancel-text="t('queue.cancel')"
                  @confirm="deleteQueueItem(record.id)"
                >
                  <a-button size="middle" danger :disabled="locked">
                    <DeleteOutlined />
                    {{ t('queue.del') }}
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
          <img src="@/assets/NoData.png" :alt="t('queue.noData')" class="empty-image" />
        </div>
      </div>
    </div>
  </a-card>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { onMounted, ref, nextTick, watch } from 'vue'
import { message } from 'ant-design-vue'
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons-vue'
import draggable from 'vuedraggable'
import dayjs from 'dayjs'
import { Service } from '@/api'

const { t } = useI18n()
const logger = window.electronAPI.getLogger('队列项管理')

// Props
interface Props {
  queueId: string
  queueItems: any[]
  showCycleConfig?: boolean
  // 队列正在循环运行：增删、排序、换脚本会被后端拦下，循环周期仍可改
  locked?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  showCycleConfig: false,
  locked: false,
})

// Emits
const emit = defineEmits<{
  refresh: []
}>()

// 响应式数据
const loading = ref(false)
const isDraggingQueueItem = ref(false)

// 选项数据
const scriptOptions = ref<Array<{ label: string; value: string | null }>>([])

// 表格列配置
const _queueColumns = [
  {
    title: t('queue.item.colIndex'),
    key: 'index',
    width: 80,
    align: 'center',
  },
  {
    title: t('queue.item.colScript'),
    key: 'script',
    align: 'center',
    ellipsis: true,
  },
  {
    title: t('queue.item.colActions'),
    key: 'actions',
    width: 100,
    align: 'center',
  },
]

// 后端 NextRunAt 的空值哨兵，表示「尚未推算」；见 app/utils/constants.py
const CYCLE_EMPTY_TIME = '2000-01-01 00:00:00'

// 循环调度的默认值，与后端 QueueItem 的配置项保持一致
const CYCLE_SCHEDULE_DEFAULTS = {
  Enabled: true,
  Mode: 'fixed_time',
  Days: ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'],
  Time: '00:00',
  IntervalMinutes: 480,
  IntervalAnchor: 'start',
  NextRunAt: CYCLE_EMPTY_TIME,
}

// 补齐循环配置并派生时间选择器需要的 dayjs 值
const withCycleSchedule = (items: any[]) =>
  items.map(item => {
    const schedule = { ...CYCLE_SCHEDULE_DEFAULTS, ...(item.schedule || {}) }
    return { ...item, schedule, scheduleTimeValue: parseTimeString(schedule.Time) }
  })

// 计算属性 - 使用props传入的数据
const queueItems = ref(withCycleSchedule(props.queueItems))

// 监听props变化
watch(
  () => props.queueItems,
  newQueueItems => {
    if (!isDraggingQueueItem.value) {
      queueItems.value = withCycleSchedule(newQueueItems)
    }
  },
  { deep: true }
)

// 时间字符串 "HH:mm" 与时间选择器的 dayjs 值互转
const parseTimeString = (timeString: string) => {
  const [hours = 0, minutes = 0] = String(timeString || '00:00').split(':').map(Number)
  return dayjs().hour(hours).minute(minutes).second(0).millisecond(0)
}

const formatTimeValue = (timeValue: any) => {
  if (!timeValue) return '00:00'
  return dayjs.isDayjs(timeValue) ? timeValue.format('HH:mm') : dayjs(timeValue).format('HH:mm')
}

// 空值哨兵表示还没推算过，展示成「待排期」而不是 2000 年
const formatNextRun = (nextRunAt: string) =>
  !nextRunAt || nextRunAt === CYCLE_EMPTY_TIME ? t('queue.cycle.notScheduled') : nextRunAt

// 保存循环调度配置。这里不 emit refresh：本地 record 已是最新值，
// 整表刷新反而会把用户正在编辑的输入顶掉。
const saveSchedule = async (record: any, data: Record<string, any>) => {
  try {
    const response = await Service.updateItemApiQueueItemUpdatePost({
      queueId: props.queueId,
      queueItemId: record.id,
      data: { Schedule: data },
    })

    if (response.code !== 200) {
      message.error(
        t('queue.toast.scheduleUpdateFailed', {
          error: response.message || t('queue.toast.unknownError'),
        })
      )
      emit('refresh')
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`更新循环调度失败: ${errorMsg}`)
    message.error(t('queue.toast.scheduleUpdateFailed', { error: errorMsg }))
    emit('refresh')
  }
}

const saveInterval = async (record: any) => {
  const minutes = Number(record.schedule.IntervalMinutes)
  if (!Number.isFinite(minutes) || minutes < 1) {
    record.schedule.IntervalMinutes = CYCLE_SCHEDULE_DEFAULTS.IntervalMinutes
    return
  }
  await saveSchedule(record, { IntervalMinutes: minutes })
}

const saveScheduleTime = async (record: any) => {
  const timeString = formatTimeValue(record.scheduleTimeValue)
  record.schedule.Time = timeString
  await saveSchedule(record, { Time: timeString })
}

// 把下次运行时间提到当前，循环下一轮就会挑中它
const runOnce = async (record: any) => {
  const nextRunAt = dayjs().format('YYYY-MM-DD HH:mm:ss')
  record.schedule.NextRunAt = nextRunAt
  await saveSchedule(record, { NextRunAt: nextRunAt })
}

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
const updateQueueItemScript = async (record: any) => {
  try {
    loading.value = true

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
      emit('refresh')
    } else {
      message.error(
        t('queue.toast.scriptUpdateFailed', {
          error: response.message || t('queue.toast.unknownError'),
        })
      )
    }
  } catch (error: any) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`更新脚本失败: ${errorMsg}`)
    message.error(t('queue.toast.updateScriptFailed', { error: errorMsg }))
  } finally {
    loading.value = false
  }
}

// 添加队列项
const addQueueItem = async () => {
  try {
    loading.value = true

    // 直接创建队列项，默认ScriptId为null（未选择）
    const createResponse = await Service.addItemApiQueueItemAddPost({
      queueId: props.queueId,
    })

    if (createResponse.code === 200 && createResponse.queueItemId) {
      emit('refresh')
    } else {
      message.error(
        t('queue.toast.addTaskFailed', {
          error: createResponse.message || t('queue.toast.unknownError'),
        })
      )
    }
  } catch (error: any) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`添加任务失败: ${errorMsg}`)
    message.error(t('queue.toast.addTaskFailed2', { error: errorMsg }))
  } finally {
    loading.value = false
  }
}

// 删除队列项
const deleteQueueItem = async (itemId: string) => {
  try {
    const response = await Service.deleteItemApiQueueItemDeletePost({
      queueId: props.queueId,
      queueItemId: itemId,
    })

    if (response.code === 200) {
      // 确保删除后刷新数据
      emit('refresh')
    } else {
      message.error(
        t('queue.toast.deleteItemFailed', {
          error: response.message || t('queue.toast.unknownError'),
        })
      )
    }
  } catch (error: any) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`删除队列项失败: ${errorMsg}`)
    message.error(t('queue.toast.deleteItemFailed', { error: errorMsg }))
  }
}

// 拖拽结束处理函数
const onDragEnd = async (evt: any) => {
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
      emit('refresh')
    } else {
      message.error(
        t('queue.toast.reorderFailed', { error: response.message || t('queue.toast.unknownError') })
      )
      // 如果失败，刷新数据恢复原状态
      emit('refresh')
    }
  } catch (error: any) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`拖拽排序失败: ${errorMsg}`)
    message.error(t('queue.toast.reorderFailed', { error: errorMsg }))
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
  flex: 1;
  min-width: 200px;
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

.header-cell.cycle-cell,
.row-cell.cycle-cell {
  flex: 1 1 520px;
  min-width: 0;
}

.cycle-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

.cycle-line {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.cycle-next-line {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.cycle-next-text {
  font-variant-numeric: tabular-nums;
}

.row-cell.script-cell {
  flex: 1;
  min-width: 200px;
}

.row-cell.actions-cell {
  width: 120px;
  min-width: 120px;
  max-width: 120px;
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
