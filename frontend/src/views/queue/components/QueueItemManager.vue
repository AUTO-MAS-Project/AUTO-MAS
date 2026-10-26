<template>
  <a-card :title="t('queue.item.cardTitle')" class="queue-manager-card queue-item-card">
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

    <DraggableTableShell
      v-model="queueItems"
      group="queueItems"
      item-key="id"
      :disabled="loading || locked"
      :busy="loading"
      @end="onDragEnd"
    >
      <template #header>
        <div class="header-cell drag-cell"></div>
        <div class="header-cell index-cell">{{ t('queue.item.colIndex') }}</div>
        <div class="header-cell script-cell">{{ t('queue.item.colScript') }}</div>
        <div v-if="!showCycleConfig" class="header-cell days-cell">
          {{ t('queue.item.colDays') }}
        </div>
        <div v-if="showCycleConfig" class="header-cell cycle-cell">
          {{ t('queue.cycle.colConfig') }}
        </div>
        <div class="header-cell actions-cell">{{ t('queue.item.colActions') }}</div>
      </template>

      <template #row="{ element: record, index }">
        <div class="row-cell drag-cell">
          <DragHandle :title="t('queue.item.dragSort')" />
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
        <div v-if="!showCycleConfig" class="row-cell days-cell">
          <a-select
            v-model:value="record.schedule.Days"
            mode="multiple"
            size="small"
            style="width: 100%"
            class="days-select"
            :placeholder="t('queue.time.selectDays')"
            :disabled="locked"
            :max-tag-count="7"
            :bordered="false"
            @change="saveDays(record)"
          >
            <a-select-option value="Monday">{{ t('queue.time.Monday') }}</a-select-option>
            <a-select-option value="Tuesday">{{ t('queue.time.Tuesday') }}</a-select-option>
            <a-select-option value="Wednesday">{{ t('queue.time.Wednesday') }}</a-select-option>
            <a-select-option value="Thursday">{{ t('queue.time.Thursday') }}</a-select-option>
            <a-select-option value="Friday">{{ t('queue.time.Friday') }}</a-select-option>
            <a-select-option value="Saturday">{{ t('queue.time.Saturday') }}</a-select-option>
            <a-select-option value="Sunday">{{ t('queue.time.Sunday') }}</a-select-option>
          </a-select>
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
                  @blur="saveInterval(record)"
                  @press-enter="saveInterval(record)"
                />
                <a-select
                  v-model:value="record.schedule.IntervalAnchor"
                  size="small"
                  style="width: 150px"
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
                  :allow-clear="false"
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
                  @change="saveDays(record)"
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
      </template>
    </DraggableTableShell>
  </a-card>
</template>

<script setup lang="ts">
import DragHandle from '@/components/DragHandle.vue'
import DraggableTableShell from './DraggableTableShell.vue'
import { useI18n } from 'vue-i18n'
import { onMounted, ref, nextTick, watch } from 'vue'
import { message } from 'ant-design-vue'
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons-vue'
import { parseConfigTime, serializeConfigTime } from '@/utils/configDateTime'
import { formatBackendDateTime } from '@/utils/dateDisplay'
import dayjs, { type Dayjs } from 'dayjs'
import { Service } from '@/api'
import { queueApi } from '@/composables/useQueueApi'

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

// 控件使用固定显示偏移，保存完整日期时间，避免丢失 UTC 载荷的跨日关系。
const timeOffset = dayjs().utcOffset()
const parseTimeString = (value: string) => parseConfigTime(value, timeOffset)
const formatTimeValue = (value: Dayjs | string, original: string) =>
  serializeConfigTime(value, original, timeOffset)

// 补齐循环配置并派生时间选择器需要的 dayjs 值。
// savedIntervalMinutes 记录“上次成功保存”的间隔分钟数，用于校验失败时回填，
// 而不是硬编码默认值 480。
const withCycleSchedule = (items: any[]) =>
  items.map(item => {
    const schedule = { ...CYCLE_SCHEDULE_DEFAULTS, ...(item.schedule || {}) }
    return {
      ...item,
      schedule,
      scheduleTimeValue: parseTimeString(schedule.Time),
      savedIntervalMinutes: schedule.IntervalMinutes,
    }
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

// 空值哨兵表示还没推算过，展示成「待排期」而不是 2000 年
const formatNextRun = (nextRunAt: string) =>
  !nextRunAt || parseTimeString(nextRunAt)?.format('YYYY-MM-DD HH:mm:ss') === CYCLE_EMPTY_TIME
    ? t('queue.cycle.notScheduled')
    : formatBackendDateTime(nextRunAt)

// 保存循环调度配置。这里不 emit refresh：本地 record 已是最新值，
// 整表刷新反而会把用户正在编辑的输入顶掉。返回是否保存成功，供调用方
// 决定要不要把本地值当作“已确认”的基线（例如 savedIntervalMinutes）。
const saveSchedule = async (record: any, data: Record<string, any>): Promise<boolean> => {
  try {
    const response = await queueApi.updateSchedule(props.queueId, record.id, data)

    if (response.code !== 200) {
      message.error(
        t('queue.toast.scheduleUpdateFailed', {
          error: response.message || t('queue.toast.unknownError'),
        })
      )
      emit('refresh')
      return false
    }
    return true
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`更新循环调度失败: ${errorMsg}`)
    message.error(t('queue.toast.scheduleUpdateFailed', { error: errorMsg }))
    emit('refresh')
    return false
  }
}

// 失焦/回车才保存，而不是每次键入都存盘（InputNumber 的 change 事件逐字符触发）。
// 校验失败（非 1..10080 的整数，含清空后的 null）时回填上次成功保存的值，不发请求；
// 值未变化时同样不发请求。
const saveInterval = async (record: any) => {
  const minutes = Number(record.schedule.IntervalMinutes)
  const isValid = Number.isInteger(minutes) && minutes >= 1 && minutes <= 10080

  if (!isValid) {
    record.schedule.IntervalMinutes = record.savedIntervalMinutes
    return
  }

  if (minutes === record.savedIntervalMinutes) {
    record.schedule.IntervalMinutes = minutes
    return
  }

  record.schedule.IntervalMinutes = minutes
  const success = await saveSchedule(record, { IntervalMinutes: minutes })
  if (success) {
    record.savedIntervalMinutes = minutes
  }
}

// 周几按星期顺序存盘，和定时列表保持一致
const DAY_ORDER = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

const saveDays = async (record: any) => {
  const days = [...(record.schedule.Days || [])].sort(
    (a: string, b: string) => DAY_ORDER.indexOf(a) - DAY_ORDER.indexOf(b)
  )
  record.schedule.Days = days
  await saveSchedule(record, { Days: days })
}

const saveScheduleTime = async (record: any) => {
  const timeString = formatTimeValue(record.scheduleTimeValue, record.schedule.Time)
  record.schedule.Time = timeString
  await saveSchedule(record, { Time: timeString })
}

// 把下次运行时间提到当前，循环下一轮就会挑中它
const runOnce = async (record: any) => {
  const nextRunAt = dayjs().toISOString()
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

    const response = await queueApi.updateItem({
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
    const createResponse = await queueApi.addItem({
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
    const response = await queueApi.deleteItem({
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
    const response = await queueApi.reorderItems({
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

<style scoped src="./queueManager.css"></style>

<style scoped>
.queue-item-card :deep(.ant-btn) {
  padding: 0 8px;
}

.queue-item-card :deep(.ant-space-item) {
  margin-right: 6px !important;
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

/* 拖拽表格业务列样式 */
.script-cell {
  flex: 1;
  min-width: 200px;
}

.header-cell.cycle-cell,
.row-cell.cycle-cell {
  flex: 1 1 520px;
  min-width: 0;
}

.header-cell.days-cell,
.row-cell.days-cell {
  flex: 1 1 360px;
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
