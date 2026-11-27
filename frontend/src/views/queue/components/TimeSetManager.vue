<template>
  <SectionCard
    variant="plain"
    :title="t('core.queue.time.cardTitle')"
    class="app-page-section time-set-card"
    :class="{ 'time-set-disabled': looksDisabled }"
    :inert="props.pending"
  >
    <template #actions>
      <a-button type="primary" :loading="loading" :disabled="looksDisabled" @click="addTimeSet">
        <template #icon>
          <PlusOutlined />
        </template>
        {{ t('core.queue.time.add') }}
      </a-button>
    </template>

    <DraggableTableShell
      v-model="timeSets"
      group="timeSets"
      item-key="id"
      :disabled="loading || readOnly"
      :busy="loading"
      :loading="props.pending"
      @end="onDragEnd"
    >
      <template #header>
        <div class="header-cell drag-cell"></div>
        <div class="header-cell index-cell">{{ t('core.queue.item.colIndex') }}</div>
        <div class="header-cell status-cell">{{ t('core.queue.time.colStatus') }}</div>
        <div class="header-cell days-cell">{{ t('core.queue.time.colDays') }}</div>
        <div class="header-cell time-cell">{{ t('core.queue.time.colTime') }}</div>
        <div class="header-cell actions-cell">{{ t('core.queue.item.colActions') }}</div>
      </template>

      <template #row="{ element: record, index }">
        <div class="row-cell drag-cell">
          <DragHandle :title="t('core.queue.item.dragSort')" />
        </div>
        <div class="row-cell index-cell">{{ index + 1 }}</div>
        <TimeSetRow
          :record="record"
          :disabled="loading || looksDisabled"
          @enabled="
            value => {
              record.enabled = value
              queued(record.id, () => updateTimeSetStatus(record, value))
            }
          "
          @days="
            value => {
              record.days = value
              queued(record.id, () => updateTimeSetDays(record))
            }
          "
          @time="value => queued(record.id, () => updateTimeSetTime(record, value))"
          @remove="deleteTimeSet(record.id)"
        />
      </template>
    </DraggableTableShell>
  </SectionCard>
</template>

<script setup lang="ts">
import TimeSetRow from './TimeSetRow.vue'
import DragHandle from '@/components/DragHandle.vue'
import DraggableTableShell from './DraggableTableShell.vue'
import { SectionCard } from '@/components/ui'
import { useI18n } from 'vue-i18n'
import { computed, ref, nextTick, watch } from 'vue'
import { message } from 'ant-design-vue'
import { PlusOutlined } from '@ant-design/icons-vue'
import dayjs, { type Dayjs } from 'dayjs'
import { Service } from '@/composables/useTimeSetApi'
import { parseConfigTime, serializeConfigTime } from '@/utils/configDateTime'
import { useInPlaceSaves } from '../useInPlaceSaves'

const { t } = useI18n()

const logger = window.electronAPI.getLogger('定时项管理')

// Props
interface Props {
  queueId: string
  timeSets: any[]
  disabled?: boolean
  /** 本队列数据还没读回（显示的是占位内容）：立即只读，但不改样式 */
  pending?: boolean
  /** 只读已持续一段时间：显示禁用样式 */
  dimmed?: boolean
}

const props = defineProps<Props>()

// Emits
const emit = defineEmits<{
  refresh: []
  saved: [
    queueId: string,
    timeSetId: string,
    change: { time?: string; enabled?: boolean; days?: DayOfWeek[] },
  ]
}>()

// 逻辑只读与禁用样式分开：快速切换队列时不闪灰
const readOnly = computed(() => props.disabled || props.pending)
const looksDisabled = computed(() => props.disabled || props.dimmed)

// 响应式数据
const loading = ref(false)
const isDraggingTimeSet = ref(false)

// 时间处理工具函数
const timeOffset = dayjs().utcOffset()
const parseTimeString = (value: string) => parseConfigTime(value, timeOffset)
const formatTimeValue = (value: Dayjs | string, original: string) =>
  serializeConfigTime(value, original, timeOffset)

// 星期排序工具函数
type DayOfWeek = 'Monday' | 'Tuesday' | 'Wednesday' | 'Thursday' | 'Friday' | 'Saturday' | 'Sunday'

const sortDays = (days: string[]): DayOfWeek[] => {
  const dayOrder: { [key: string]: number } = {
    Monday: 1,
    Tuesday: 2,
    Wednesday: 3,
    Thursday: 4,
    Friday: 5,
    Saturday: 6,
    Sunday: 7,
  }
  return [...days].sort((a, b) => dayOrder[a] - dayOrder[b]) as DayOfWeek[]
}

// 计算属性 - 使用props传入的数据
const timeSets = ref([...props.timeSets])

// 处理时间数据，为每个项添加timeValue字段用于时间选择器
const processTimeSets = (rawTimeSets: any[]) => {
  return rawTimeSets.map(item => ({
    ...item,
    timeValue: parseTimeString(item.time),
    days: sortDays(item.days || []),
  }))
}

// 监听props变化；就地保存没结束时不整表替换（见 useInPlaceSaves）
const syncFromProps = () => {
  if (isDraggingTimeSet.value || saving.value) return
  timeSets.value = processTimeSets(props.timeSets)
}
const { saving, queued } = useInPlaceSaves(syncFromProps)
watch(() => props.timeSets, syncFromProps, { deep: true, immediate: true })

// 添加定时项
const addTimeSet = async () => {
  if (readOnly.value) return
  try {
    // 验证queueId是否存在
    if (!props.queueId || props.queueId.trim() === '') {
      message.error(t('core.queue.toast.queueIdEmpty'))
      return
    }

    loading.value = true

    // 创建定时项，使用后端默认值
    const createResponse = await Service.addTimeSetApiQueueTimeAddPost({
      queueId: props.queueId,
    })

    if (createResponse.code === 200 && createResponse.timeSetId) {
      emit('refresh')
    } else {
      message.error(
        t('core.queue.toast.createTimeFailed', {
          error: createResponse.message || t('core.queue.toast.unknownError'),
        })
      )
    }
  } catch (error: any) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`添加定时项失败: ${errorMsg}`)
    message.error(t('core.queue.toast.addTimeFailed', { error: errorMsg }))
  } finally {
    loading.value = false
  }
}

// 更新定时项时间
const updateTimeSetTime = async (
  timeSet: { id: string; time: string; timeValue?: Dayjs },
  value: Dayjs | string | null
) => {
  if (readOnly.value) return
  try {
    // 清空表示显示日期的午夜；控件的 null 不写入页面状态或配置请求。
    const timeValue =
      value === null
        ? parseTimeString(timeSet.time)?.startOf('day')
        : typeof value === 'string'
          ? parseTimeString(value)
          : value
    if (!timeValue?.isValid()) throw new Error(t('core.queue.time.selectTime'))

    // 普通编辑保留原小数秒，清空时归零；提交携带控件的显示偏移。
    const originalTime = value === null ? timeSet.time.replace(/\.\d+/, '') : timeSet.time
    const timeString = formatTimeValue(timeValue, originalTime)
    timeSet.timeValue = timeValue

    const queueId = props.queueId
    const response = await Service.updateTimeSetApiQueueTimeUpdatePost({
      queueId,
      timeSetId: timeSet.id,
      data: {
        Info: {
          Time: timeString,
        },
      },
    })

    if (response.code === 200) {
      // 更新本地显示的时间
      timeSet.time = timeString
      emit('saved', queueId, timeSet.id, { time: timeString })
    } else {
      message.error(
        t('core.queue.toast.timeUpdateFailed', {
          error: response.message || t('core.queue.toast.unknownError'),
        })
      )
      // 回滚时间值
      timeSet.timeValue = parseTimeString(timeSet.time)
    }
  } catch (error: any) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`更新时间失败: ${errorMsg}`)
    message.error(t('core.queue.toast.updateTimeFailed', { error: errorMsg }))
    // 回滚时间值
    timeSet.timeValue = parseTimeString(timeSet.time)
  }
}

// 更新定时项状态
// enabled 取操作当时的值：排队等到执行时，这一行可能已被再次拨动或被前一次失败回滚
const updateTimeSetStatus = async (timeSet: any, enabled: boolean) => {
  if (readOnly.value) return
  try {
    const queueId = props.queueId
    const response = await Service.updateTimeSetApiQueueTimeUpdatePost({
      queueId,
      timeSetId: timeSet.id,
      data: {
        Info: {
          Enabled: enabled,
        },
      },
    })

    if (response.code === 200) {
      // 状态更新成功，无需通知
      emit('saved', queueId, timeSet.id, { enabled })
    } else {
      message.error(
        t('core.queue.toast.statusUpdateFailed', {
          error: response.message || t('core.queue.toast.unknownError'),
        })
      )
      // 回滚状态（之后又拨过的不动）
      if (timeSet.enabled === enabled) timeSet.enabled = !enabled
    }
  } catch (error: any) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`更新状态失败: ${errorMsg}`)
    message.error(t('core.queue.toast.updateStatusFailed', { error: errorMsg }))
    // 回滚状态（之后又拨过的不动）
    if (timeSet.enabled === enabled) timeSet.enabled = !enabled
  }
}

// 更新定时项执行周期
const updateTimeSetDays = async (timeSet: any) => {
  if (readOnly.value) return
  try {
    // 对选中的日期按星期顺序排序
    const sortedDays = sortDays(timeSet.days || [])
    timeSet.days = sortedDays

    const queueId = props.queueId
    const response = await Service.updateTimeSetApiQueueTimeUpdatePost({
      queueId,
      timeSetId: timeSet.id,
      data: {
        Info: {
          Days: sortedDays,
        },
      },
    })

    if (response.code === 200) {
      // 周期更新成功，无需通知
      emit('saved', queueId, timeSet.id, { days: sortedDays })
    } else {
      message.error(
        t('core.queue.toast.daysUpdateFailed', {
          error: response.message || t('core.queue.toast.unknownError'),
        })
      )
    }
  } catch (error: any) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`更新执行周期失败: ${errorMsg}`)
    message.error(t('core.queue.toast.updateDaysFailed', { error: errorMsg }))
  }
}

// 删除定时项
const deleteTimeSet = async (timeSetId: string) => {
  if (readOnly.value) return
  try {
    const response = await Service.deleteTimeSetApiQueueTimeDeletePost({
      queueId: props.queueId,
      timeSetId,
    })

    if (response.code === 200) {
      // 确保删除后刷新数据
      emit('refresh')
    } else {
      message.error(
        t('core.queue.toast.deleteTimeFailed', {
          error: response.message || t('core.queue.toast.unknownError'),
        })
      )
    }
  } catch (error: any) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`删除定时项失败: ${errorMsg}`)
    message.error(t('core.queue.toast.deleteTimeFailed', { error: errorMsg }))
  }
}

// 拖拽结束处理函数
const onDragEnd = async (evt: any) => {
  // 如果位置没有变化，直接返回
  if (evt.oldIndex === evt.newIndex || readOnly.value) {
    return
  }

  isDraggingTimeSet.value = true

  try {
    loading.value = true

    // 构造排序后的ID列表
    const sortedIds = timeSets.value.map(item => item.id)

    // 调用排序API
    const response = await Service.reorderTimeSetApiQueueTimeOrderPost({
      queueId: props.queueId,
      indexList: sortedIds,
    })

    if (response.code === 200) {
      // 刷新数据以确保与服务器同步
      emit('refresh')
    } else {
      message.error(
        t('core.queue.toast.reorderTimeFailed', {
          error: response.message || t('core.queue.toast.unknownError'),
        })
      )
      // 如果失败，刷新数据恢复原状态
      emit('refresh')
    }
  } catch (error: any) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`拖拽排序失败: ${errorMsg}`)
    message.error(t('core.queue.toast.reorderTimeFailed', { error: errorMsg }))
    // 如果失败，刷新数据恢复原状态
    emit('refresh')
  } finally {
    loading.value = false
    nextTick(() => {
      isDraggingTimeSet.value = false
    })
  }
}
</script>

<style scoped src="./queueManager.css"></style>

<style scoped>
.time-set-disabled :deep(.drag-handle) {
  cursor: not-allowed;
  color: var(--ant-color-text-disabled);
}

.time-set-disabled :deep(.ant-picker-input > input) {
  color: var(--ant-color-text-disabled) !important;
}
.time-set-card :deep(.ant-btn) {
  padding: 0 12px;
}

.time-set-card :deep(.ant-space-item) {
  margin-right: 8px !important;
}

/* 时间选择器样式 */
:deep(.ant-picker) {
  background: transparent !important;
  border: none !important;
  padding: 0 6px !important;
  min-height: 28px !important;
  line-height: 26px !important;
  box-shadow: none !important;
  text-align: center;
  width: 80px !important;
}

:deep(.ant-picker-input > input) {
  text-align: center !important;
  font-weight: 600 !important;
  color: var(--ant-color-text) !important;
  background: transparent !important;
  border: none !important;
  padding: 0 !important;
  line-height: 26px !important;
}

:deep(.ant-picker:hover) {
  border: none !important;
  box-shadow: none !important;
  background: transparent !important;
}

:deep(.ant-picker:focus-within),
:deep(.ant-picker.ant-picker-focused) {
  border: none !important;
  box-shadow: none !important;
  background: transparent !important;
  outline: none !important;
}

:deep(.ant-picker-clear) {
  display: none !important;
}

:deep(.ant-picker-suffix) {
  right: 4px;
  color: var(--ant-color-text-tertiary);
  font-size: 10px;
}

:deep(.ant-picker-suffix:hover) {
  color: var(--ant-color-primary);
}

/* 时间选择器弹出面板滚动条样式优化 */
:deep(.ant-picker-time-panel) {
  border-radius: 8px;
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.12);
}

/* 时间选择器面板项目样式优化 */
:deep(.ant-picker-time-panel-cell) {
  transition: all 0.2s ease;
}

:deep(.ant-picker-time-panel-cell:hover) {
  background: var(--ant-color-fill-tertiary);
}

/* 拖拽表格业务列样式 */
.status-cell {
  width: 120px;
  min-width: 120px;
  max-width: 120px;
}

.days-cell {
  flex: 4;
  min-width: 0;
}

.time-cell {
  flex: 1;
  min-width: 120px;
  max-width: 200px;
}
</style>
