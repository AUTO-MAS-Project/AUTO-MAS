<template>
  <a-card :title="t('core.queue.item.cardTitle')" class="app-page-section queue-item-card">
    <template #extra>
      <a-space>
        <a-button type="primary" :loading="loading" :disabled="locked" @click="addQueueItem">
          <template #icon>
            <PlusOutlined />
          </template>
          {{ t('core.queue.item.add') }}
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
        <div class="header-cell index-cell">{{ t('core.queue.item.colIndex') }}</div>
        <div class="header-cell script-cell">{{ t('core.queue.item.colScript') }}</div>
        <div class="header-cell days-cell">
          {{ t('core.queue.item.colDays') }}
        </div>
        <div class="header-cell actions-cell">{{ t('core.queue.item.colActions') }}</div>
      </template>

      <template #row="{ element: record, index }">
        <div class="row-cell drag-cell">
          <DragHandle :title="t('core.queue.item.dragSort')" />
        </div>
        <div class="row-cell index-cell">{{ index + 1 }}</div>
        <div class="row-cell script-cell">
          <a-select
            v-model:value="record.script"
            size="small"
            style="width: 200px"
            class="script-select"
            :placeholder="t('core.queue.item.selectScript')"
            :options="scriptOptions"
            :disabled="locked"
            allow-clear
            @change="updateQueueItemScript(record)"
          />
        </div>
        <div class="row-cell days-cell">
          <QueueWeekdaysSelect
            v-model="record.schedule.Days"
            :disabled="locked"
            @change="saveDays(record)"
          />
        </div>
        <div class="row-cell actions-cell">
          <a-space>
            <QueueDeleteButton
              :title="t('core.queue.item.deleteConfirm')"
              :disabled="locked"
              :confirm="() => deleteQueueItem(record.id)"
            />
          </a-space>
        </div>
      </template>
    </DraggableTableShell>
  </a-card>
</template>

<script setup lang="ts">
import DragHandle from '@/components/DragHandle.vue'
import QueueDeleteButton from './QueueDeleteButton.vue'
import QueueWeekdaysSelect from './QueueWeekdaysSelect.vue'
import DraggableTableShell from './DraggableTableShell.vue'
import QueueWeekdaySelect from './QueueWeekdaySelect.vue'
import { useI18n } from 'vue-i18n'
import { onMounted, ref, nextTick, watch } from 'vue'
import { message } from 'ant-design-vue'
import { PlusOutlined } from '@ant-design/icons-vue'
import { Service } from '@/api'
import { queueApi } from '@/composables/useQueueApi'

const { t } = useI18n()

const logger = window.electronAPI.getLogger('队列项管理')

// Props
interface Props {
  queueId: string
  queueItems: any[]
  locked?: boolean
}

const props = withDefaults(defineProps<Props>(), {
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

const withSchedule = (items: any[]) =>
  items.map(item => ({ ...item, schedule: { Days: [], ...(item.schedule || {}) } }))
const queueItems = ref(withSchedule(props.queueItems))
watch(
  () => props.queueItems,
  items => {
    if (!isDraggingQueueItem.value) queueItems.value = withSchedule(items)
  },
  { deep: true }
)

// 保存队列项的执行星期。这里不 emit refresh：本地 record 已是最新值，
// 整表刷新反而会把用户正在编辑的输入顶掉。返回是否保存成功，供调用方
// 决定要不要把本地值当作“已确认”的基线（例如 savedIntervalMinutes）。
const saveSchedule = async (record: any, data: Record<string, any>): Promise<boolean> => {
  try {
    const response = await queueApi.updateSchedule(props.queueId, record.id, data)

    if (response.code !== 200) {
      message.error(
        t('core.queue.toast.scheduleUpdateFailed', {
          error: response.message || t('core.queue.toast.unknownError'),
        })
      )
      emit('refresh')
      return false
    }
    return true
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`更新循环调度失败: ${errorMsg}`)
    message.error(t('core.queue.toast.scheduleUpdateFailed', { error: errorMsg }))
    emit('refresh')
    return false
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
        t('core.queue.toast.scriptUpdateFailed', {
          error: response.message || t('core.queue.toast.unknownError'),
        })
      )
    }
  } catch (error: any) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`更新脚本失败: ${errorMsg}`)
    message.error(t('core.queue.toast.updateScriptFailed', { error: errorMsg }))
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
        t('core.queue.toast.addTaskFailed', {
          error: createResponse.message || t('core.queue.toast.unknownError'),
        })
      )
    }
  } catch (error: any) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`添加任务失败: ${errorMsg}`)
    message.error(t('core.queue.toast.addTaskFailed2', { error: errorMsg }))
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
        t('core.queue.toast.deleteItemFailed', {
          error: response.message || t('core.queue.toast.unknownError'),
        })
      )
    }
  } catch (error: any) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`删除队列项失败: ${errorMsg}`)
    message.error(t('core.queue.toast.deleteItemFailed', { error: errorMsg }))
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
        t('core.queue.toast.reorderFailed', {
          error: response.message || t('core.queue.toast.unknownError'),
        })
      )
      // 如果失败，刷新数据恢复原状态
      emit('refresh')
    }
  } catch (error: any) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`拖拽排序失败: ${errorMsg}`)
    message.error(t('core.queue.toast.reorderFailed', { error: errorMsg }))
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

.header-cell.days-cell,
.row-cell.days-cell {
  flex: 1 1 360px;
  min-width: 0;
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
