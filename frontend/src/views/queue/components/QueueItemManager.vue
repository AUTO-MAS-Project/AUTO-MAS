<template>
  <SectionCard
    variant="plain"
    :title="t('core.queue.item.cardTitle')"
    class="app-page-section queue-item-card"
    :inert="pending"
  >
    <template #actions>
      <a-button type="primary" :loading="loading" :disabled="looksDisabled" @click="addQueueItem">
        <template #icon>
          <PlusOutlined />
        </template>
        {{ t('core.queue.item.add') }}
      </a-button>
    </template>

    <DraggableTableShell
      v-model="queueItems"
      group="queueItems"
      item-key="id"
      :disabled="loading || readOnly"
      :busy="loading"
      :loading="pending"
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
            style="width: 100%"
            class="script-select"
            :placeholder="t('core.queue.item.selectScript')"
            :options="scriptOptions"
            :disabled="looksDisabled"
            allow-clear
            @change="updateQueueItemScript(record)"
          />
        </div>
        <div class="row-cell days-cell">
          <QueueWeekdaysSelect
            v-model="record.schedule.Days"
            :disabled="looksDisabled"
            @change="saveDays(record)"
          />
        </div>
        <div class="row-cell actions-cell">
          <a-space>
            <QueueDeleteButton
              :title="t('core.queue.item.deleteConfirm')"
              :disabled="looksDisabled"
              :confirm="() => deleteQueueItem(record.id)"
            />
          </a-space>
        </div>
      </template>
    </DraggableTableShell>
  </SectionCard>
</template>

<script setup lang="ts">
import DragHandle from '@/components/DragHandle.vue'
import QueueDeleteButton from './QueueDeleteButton.vue'
import QueueWeekdaysSelect from './QueueWeekdaysSelect.vue'
import DraggableTableShell from './DraggableTableShell.vue'
import { SectionCard } from '@/components/ui'
import { useI18n } from 'vue-i18n'
import { computed, onMounted, ref, nextTick, watch } from 'vue'
import { message } from 'ant-design-vue'
import { PlusOutlined } from '@ant-design/icons-vue'
import { Service } from '@/api'
import { queueApi } from '@/composables/useQueueApi'
import { sharedScriptOptions } from './queueScriptOptions'

const { t } = useI18n()

const logger = window.electronAPI.getLogger('队列项管理')

// Props
interface Props {
  queueId: string
  queueItems: any[]
  locked?: boolean
  /** 本队列数据还没读回（显示的是占位内容）：立即只读，但不改样式 */
  pending?: boolean
  /** 只读已持续一段时间：显示禁用样式 */
  dimmed?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  locked: false,
  pending: false,
  dimmed: false,
})

// Emits
const emit = defineEmits<{
  refresh: []
  saved: [queueId: string, queueItemId: string, schedule: Record<string, any>]
}>()

// 逻辑只读与禁用样式分开：快速切换队列时不闪灰
const readOnly = computed(() => props.locked || props.pending)
const looksDisabled = computed(() => props.locked || props.dimmed)

// 响应式数据
const loading = ref(false)
const isDraggingQueueItem = ref(false)

// 选项数据：切换队列会重挂载本组件，沿用上次读到的选项，避免下拉框先显示原始脚本 ID
const scriptOptions = sharedScriptOptions

const withSchedule = (items: any[]) =>
  items.map(item => ({ ...item, schedule: { Days: [], ...(item.schedule || {}) } }))
const queueItems = ref(withSchedule(props.queueItems))
// 就地保存在途的条数。保存成功后父层会把新值回写到 props，触发下面的整表替换；
// 这时如果另一条编辑的请求还没返回，它在本地的新值会被 props 里的旧值顶掉。
// 所以在途时先不替换，全部返回后再整表同步一次（在途期间跳过的刷新也在这时补上）。
const inPlaceSaves = ref(0)
const syncFromProps = () => {
  if (isDraggingQueueItem.value || inPlaceSaves.value > 0) return
  queueItems.value = withSchedule(props.queueItems)
}
watch(() => props.queueItems, syncFromProps, { deep: true })
watch(inPlaceSaves, syncFromProps)

// 保存队列项的执行星期。这里不 emit refresh：本地 record 已是最新值，
// 整表刷新反而会把用户正在编辑的输入顶掉。返回是否保存成功，供调用方
// 决定要不要把本地值当作“已确认”的基线（例如 savedIntervalMinutes）。
const saveSchedule = async (record: any, data: Record<string, any>): Promise<boolean> => {
  if (readOnly.value) return false
  const queueId = props.queueId
  inPlaceSaves.value++
  try {
    const response = await queueApi.updateSchedule(queueId, record.id, data)

    if (response.code !== 200) {
      message.error(
        t('core.queue.toast.scheduleUpdateFailed', {
          error: response.message || t('core.queue.toast.unknownError'),
        })
      )
      emit('refresh')
      return false
    }
    emit('saved', queueId, record.id, data)
    return true
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`更新循环调度失败: ${errorMsg}`)
    message.error(t('core.queue.toast.scheduleUpdateFailed', { error: errorMsg }))
    emit('refresh')
    return false
  } finally {
    // 与上面的 emit 在同一段同步代码里递减：最后一条返回时，随后才执行的监听器看到的已是 0
    inPlaceSaves.value--
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
  if (readOnly.value) return
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
  if (readOnly.value) return
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
  if (readOnly.value) return
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
  if (evt.oldIndex === evt.newIndex || readOnly.value) {
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

/* 拖拽表格业务列样式 */
.script-cell {
  flex: 3 1 320px;
  min-width: 240px;
}

.header-cell.days-cell,
.row-cell.days-cell {
  flex: 2 1 240px;
  min-width: 0;
}

/* 响应式设计：窄屏行转为纵向排列，flex-basis 会变成高度基准，改为按内容撑开 */
@media (max-width: 768px) {
  .row-cell.script-cell,
  .row-cell.days-cell {
    flex: 0 0 auto;
  }
}

/* 标签样式 */
:deep(.ant-tag) {
  margin: 0;
  border-radius: 4px;
}

/* 脚本下拉框样式 */
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
