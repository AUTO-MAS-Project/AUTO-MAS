<template>
  <a-card title="定时列表" class="time-set-card">
    <template #extra>
      <a-space>
        <a-button
          type="primary"
          @click="addTimeSet"
          :loading="loading"
          :disabled="!props.queueId || props.queueId.trim() === ''"
        >
          <template #icon>
            <PlusOutlined />
          </template>
          添加定时
        </a-button>
      </a-space>
    </template>

    <!-- 使用vuedraggable替换a-table实现拖拽功能 -->
    <div class="draggable-table-container">
      <!-- 表头 -->
      <div class="draggable-table-header">
        <div class="header-cell index-cell">序号</div>
        <div class="header-cell status-cell">状态</div>
        <div class="header-cell time-cell">执行时间</div>
        <div class="header-cell actions-cell">操作</div>
      </div>

      <!-- 拖拽内容区域 -->
      <draggable
        v-model="timeSets"
        group="timeSets"
        item-key="id"
        :animation="200"
        :disabled="loading"
        ghost-class="ghost"
        chosen-class="chosen"
        drag-class="drag"
        @end="onDragEnd"
        class="draggable-container"
      >
        <template #item="{ element: record, index }">
          <div class="draggable-row" :class="{ 'row-dragging': loading }">
            <div class="row-cell index-cell">{{ index + 1 }}</div>
            <div class="row-cell status-cell">
              <a-select
                v-model:value="record.enabled"
                @change="updateTimeSetStatus(record)"
                size="small"
                style="width: 80px"
                class="status-select"
              >
                <a-select-option :value="true">启用</a-select-option>
                <a-select-option :value="false">禁用</a-select-option>
              </a-select>
            </div>
            <div class="row-cell time-cell">
              <a-time-picker
                v-model:value="record.timeValue"
                format="HH:mm"
                placeholder="请选择时间"
                size="small"
                @change="updateTimeSetTime(record)"
                :disabled="loading"
              />
            </div>
            <div class="row-cell actions-cell">
              <a-space>
                <a-popconfirm
                  title="确定要删除这个定时吗？"
                  @confirm="deleteTimeSet(record.id)"
                  ok-text="确定"
                  cancel-text="取消"
                >
                  <a-button size="middle" danger>
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
      <div v-if="timeSets.length === 0" class="empty-state">
        <div class="empty-content">
          <img src="../../../assets/NoData.png" alt="无数据" class="empty-image" />
        </div>
      </div>
    </div>
  </a-card>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons-vue'
import draggable from 'vuedraggable'
import { Service } from '@/api'
import dayjs from 'dayjs'

// Props
interface Props {
  queueId: string
  timeSets: any[]
}

const props = defineProps<Props>()

// Emits
const emit = defineEmits<{
  refresh: []
}>()

// 响应式数据
const loading = ref(false)

// 时间处理工具函数
const parseTimeString = (timeStr: string) => {
  if (!timeStr) return undefined
  try {
    const [hours, minutes] = timeStr.split(':').map(Number)
    if (isNaN(hours) || isNaN(minutes)) return undefined
    return dayjs().hour(hours).minute(minutes).second(0).millisecond(0)
  } catch {
    return undefined
  }
}

const formatTimeValue = (timeValue: any) => {
  if (!timeValue) return '00:00'
  try {
    if (dayjs.isDayjs(timeValue)) {
      return timeValue.format('HH:mm')
    }
    return dayjs(timeValue).format('HH:mm')
  } catch {
    return '00:00'
  }
}

// 表格列配置
const timeColumns = [
  {
    title: '序号',
    dataIndex: 'index',
    key: 'index',
    width: 80,
    align: 'center',
    customRender: ({ index }: { index: number }) => index + 1,
  },
  {
    title: '状态',
    dataIndex: 'enabled',
    key: 'enabled',
    width: 120,
    align: 'center',
  },
  {
    title: '执行时间',
    dataIndex: 'time',
    key: 'time',
    align: 'center',
    ellipsis: true,
  },
  {
    title: '操作',
    key: 'actions',
    width: 100,
    align: 'center',
  },
]

// 计算属性 - 使用props传入的数据
const timeSets = ref([...props.timeSets])

// 处理时间数据，为每个项添加timeValue字段用于时间选择器
const processTimeSets = (rawTimeSets: any[]) => {
  return rawTimeSets.map(item => ({
    ...item,
    timeValue: parseTimeString(item.time),
  }))
}

// 监听props变化
watch(
  () => props.timeSets,
  newTimeSets => {
    timeSets.value = processTimeSets(newTimeSets)
  },
  { deep: true, immediate: true }
)

// 添加定时项
const addTimeSet = async () => {
  try {
    // 验证queueId是否存在
    if (!props.queueId || props.queueId.trim() === '') {
      message.error('队列ID为空，无法添加定时')
      return
    }

    loading.value = true

    // 先创建，再设置默认值
    const createResponse = await Service.addTimeSetApiQueueTimeAddPost({
      queueId: props.queueId,
    })

    if (createResponse.code === 200 && createResponse.timeSetId) {
      const updateResponse = await Service.updateTimeSetApiQueueTimeUpdatePost({
        queueId: props.queueId,
        timeSetId: createResponse.timeSetId,
        data: {
          Info: {
            Enabled: false, // 默认禁用
            Time: '00:00', // 默认00:00
          },
        },
      })

      if (updateResponse.code === 200) {
        message.success('定时项添加成功')
        emit('refresh')
      } else {
        message.error('定时项添加失败: ' + (updateResponse.message || '未知错误'))
      }
    } else {
      message.error('创建定时项失败: ' + (createResponse.message || '未知错误'))
    }
  } catch (error: any) {
    console.error('添加定时项失败:', error)
    message.error('添加定时项失败: ' + (error?.message || '网络错误'))
  } finally {
    loading.value = false
  }
}

// 更新定时项时间
const updateTimeSetTime = async (timeSet: any) => {
  try {
    const timeString = formatTimeValue(timeSet.timeValue)

    const response = await Service.updateTimeSetApiQueueTimeUpdatePost({
      queueId: props.queueId,
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
      message.success('时间更新成功')
    } else {
      message.error('时间更新失败: ' + (response.message || '未知错误'))
      // 回滚时间值
      timeSet.timeValue = parseTimeString(timeSet.time)
    }
  } catch (error: any) {
    console.error('更新时间失败:', error)
    message.error('更新时间失败: ' + (error?.message || '网络错误'))
    // 回滚时间值
    timeSet.timeValue = parseTimeString(timeSet.time)
  }
}

// 更新定时项状态
const updateTimeSetStatus = async (timeSet: any) => {
  try {
    const response = await Service.updateTimeSetApiQueueTimeUpdatePost({
      queueId: props.queueId,
      timeSetId: timeSet.id,
      data: {
        Info: {
          Enabled: timeSet.enabled,
        },
      },
    })

    if (response.code === 200) {
      message.success('状态更新成功')
    } else {
      message.error('状态更新失败: ' + (response.message || '未知错误'))
      // 回滚状态
      timeSet.enabled = !timeSet.enabled
    }
  } catch (error: any) {
    console.error('更新状态失败:', error)
    message.error('更新状态失败: ' + (error?.message || '网络错误'))
    // 回滚状态
    timeSet.enabled = !timeSet.enabled
  }
}

// 删除定时项
const deleteTimeSet = async (timeSetId: string) => {
  try {
    const response = await Service.deleteTimeSetApiQueueTimeDeletePost({
      queueId: props.queueId,
      timeSetId,
    })

    if (response.code === 200) {
      message.success('定时项删除成功')
      // 确保删除后刷新数据
      emit('refresh')
    } else {
      message.error('删除定时项失败: ' + (response.message || '未知错误'))
    }
  } catch (error: any) {
    console.error('删除定时项失败:', error)
    message.error('删除定时项失败: ' + (error?.message || '网络错误'))
  }
}

// 拖拽结束处理函数
const onDragEnd = async (evt: any) => {
  // 如果位置没有变化，直接返回
  if (evt.oldIndex === evt.newIndex) {
    return
  }

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
      message.success('定时顺序已更新')
      // 刷新数据以确保与服务器同步
      emit('refresh')
    } else {
      message.error('更新定时顺序失败: ' + (response.message || '未知错误'))
      // 如果失败，刷新数据恢复原状态
      emit('refresh')
    }
  } catch (error: any) {
    console.error('拖拽排序失败:', error)
    message.error('更新定时顺序失败: ' + (error?.message || '网络错误'))
    // 如果失败，刷新数据恢复原状态
    emit('refresh')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.time-set-card {
  margin-bottom: 24px;
}

.time-set-card :deep(.ant-card-head-title) {
  font-size: 18px;
  font-weight: 600;
}

/* 表格样式优化 */
.time-set-table {
  width: 100% !important;
  max-width: 100% !important;
}

.time-set-table :deep(.ant-table-wrapper) {
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

/* 强制移除任何可能的滚动条 */
:deep(.ant-table-wrapper),
:deep(.ant-table-container),
:deep(.ant-table-body),
:deep(.ant-table-content),
:deep(.ant-table),
:deep(.ant-table-tbody) {
  scrollbar-width: none !important; /* Firefox */
  -ms-overflow-style: none !important; /* IE/Edge */
}

:deep(.ant-table-wrapper)::-webkit-scrollbar,
:deep(.ant-table-container)::-webkit-scrollbar,
:deep(.ant-table-body)::-webkit-scrollbar,
:deep(.ant-table-content)::-webkit-scrollbar,
:deep(.ant-table)::-webkit-scrollbar,
:deep(.ant-table-tbody)::-webkit-scrollbar {
  display: none !important; /* Chrome/Safari */
}

/* 列宽度控制 */
:deep(.ant-table-thead > tr > th:nth-child(1)) {
  width: 80px !important;
  min-width: 80px !important;
  max-width: 80px !important;
}

:deep(.ant-table-thead > tr > th:nth-child(2)) {
  width: 120px !important;
  min-width: 120px !important;
  max-width: 120px !important;
}

:deep(.ant-table-thead > tr > th:nth-child(3)) {
  width: auto !important;
  min-width: 100px !important;
}

:deep(.ant-table-thead > tr > th:nth-child(4)) {
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
  width: 120px !important;
  min-width: 120px !important;
  max-width: 120px !important;
}

:deep(.ant-table-tbody > tr > td:nth-child(3)) {
  width: auto !important;
  min-width: 100px !important;
}

:deep(.ant-table-tbody > tr > td:nth-child(4)) {
  width: 180px !important;
  min-width: 180px !important;
  max-width: 180px !important;
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
:deep(.ant-table-tbody > tr > td:nth-child(4) .ant-space) {
  justify-content: center;
  width: 100%;
}

/* 按钮图标样式调整 */
:deep(.ant-btn .anticon) {
  font-size: 14px;
}

/* 序号列样式 */
:deep(.ant-table-tbody > tr > td:first-child) {
  font-weight: 500;
  color: var(--ant-color-text-secondary);
}

/* 隐藏所有滚动条 */
:deep(.ant-table-container)::-webkit-scrollbar,
:deep(.ant-table-tbody)::-webkit-scrollbar,
:deep(.ant-table-content)::-webkit-scrollbar,
:deep(.ant-table-body)::-webkit-scrollbar {
  display: none !important;
  width: 0 !important;
  height: 0 !important;
}

/* 确保列宽度固定 */
:deep(.ant-table-thead > tr > th) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

:deep(.ant-table-tbody > tr > td) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
  padding: 0 12px;
}

:deep(.ant-space-item) {
  margin-right: 8px !important;
}

/* 时间选择器样式 */
:deep(.ant-picker) {
  width: 100%;
}

/* 开关样式 */
:deep(.ant-switch) {
  margin: 0;
}

/* 状态下拉框样式 - 使用与Plans.vue相同的config-select样式 */
.status-select :deep(.ant-select-selector) {
  background: transparent !important;
  border: none !important;
  padding: 0 6px !important;
  min-height: 28px !important;
  line-height: 26px !important;
  box-shadow: none !important;
  text-align: center;
}

.status-select :deep(.ant-select-selection-item) {
  line-height: 26px !important;
  color: var(--ant-color-text) !important;
  font-weight: 500;
  padding: 0;
  margin: 0;
}

.status-select :deep(.ant-select-selection-placeholder) {
  line-height: 26px !important;
  color: var(--ant-color-text-placeholder) !important;
  padding: 0;
  margin: 0;
}

.status-select :deep(.ant-select-clear) {
  display: none !important;
}

.status-select :deep(.ant-select-selection-search) {
  margin: 0 !important;
  padding: 0;
}

.status-select :deep(.ant-select-selection-search-input) {
  padding: 0 !important;
  margin: 0 !important;
  height: 26px !important;
}

.status-select:hover :deep(.ant-select-selector) {
  border: none !important;
  box-shadow: none !important;
  background: transparent !important;
}

.status-select:focus-within :deep(.ant-select-selector),
.status-select.ant-select-focused :deep(.ant-select-selector) {
  border: none !important;
  box-shadow: none !important;
  background: transparent !important;
  outline: none !important;
}

.status-select :deep(.ant-select-selector):focus,
.status-select :deep(.ant-select-selector):focus-within {
  border: none !important;
  box-shadow: none !important;
  background: transparent !important;
  outline: none !important;
  cursor: default !important;
}

/* 隐藏下拉箭头或调整样式 */
.status-select :deep(.ant-select-arrow) {
  right: 4px;
  color: var(--ant-color-text-tertiary);
  font-size: 10px;
}

.status-select :deep(.ant-select-arrow:hover) {
  color: var(--ant-color-primary);
}

/* 自定义下拉框样式 - 增加下拉菜单宽度 */
.status-select :deep(.ant-select-dropdown) {
  min-width: 100px !important;
  max-width: 150px !important;
}

.status-select :deep(.ant-select-item) {
  padding: 8px 12px !important;
}

.status-select :deep(.ant-select-item-option-content) {
}

/* 时间显示样式 */
.time-display {
  font-weight: 600;
  color: var(--ant-color-text);
  padding: 4px 8px;
  border-radius: 4px;
  display: inline-block;
  min-width: 60px;
  text-align: center;
}

/* 时间选择器样式 - 与状态下拉框保持一致 */
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

/* Firefox 滚动条样式 - 时间选择器 */
:deep(.ant-picker-time-panel-column) {
  scrollbar-width: thin;
  scrollbar-color: #d9d9d9 #f5f5f5;
}

.dark :deep(.ant-picker-time-panel-column) {
  scrollbar-width: thin;
  scrollbar-color: var(--ant-color-border) var(--ant-color-bg-layout);
}

/* 浅色主题滚动条样式 - 时间选择器 */
:deep(.ant-picker-time-panel-column)::-webkit-scrollbar {
  width: 8px;
}

:deep(.ant-picker-time-panel-column)::-webkit-scrollbar-track {
  background: #f5f5f5;
  border-radius: 4px;
}

:deep(.ant-picker-time-panel-column)::-webkit-scrollbar-thumb {
  background: #d9d9d9;
  border-radius: 4px;
  transition: background 0.2s ease;
}

:deep(.ant-picker-time-panel-column)::-webkit-scrollbar-thumb:hover {
  background: #bfbfbf;
}

/* 深色主题滚动条样式 - 时间选择器 */
.dark :deep(.ant-picker-time-panel-column)::-webkit-scrollbar {
  width: 8px;
}

.dark :deep(.ant-picker-time-panel-column)::-webkit-scrollbar-track {
  background: var(--ant-color-bg-layout);
  border-radius: 4px;
}

.dark :deep(.ant-picker-time-panel-column)::-webkit-scrollbar-thumb {
  background: var(--ant-color-border);
  border-radius: 4px;
  transition: background 0.2s ease;
}

.dark :deep(.ant-picker-time-panel-column)::-webkit-scrollbar-thumb:hover {
  background: var(--ant-color-text-tertiary);
}

/* 时间选择器面板项目样式优化 */
:deep(.ant-picker-time-panel-cell) {
  transition: all 0.2s ease;
}

:deep(.ant-picker-time-panel-cell:hover) {
  background: var(--ant-color-fill-tertiary);
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

.status-cell {
  width: 120px;
  min-width: 120px;
  max-width: 120px;
}

.time-cell {
  flex: 1;
  min-width: 100px;
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
  cursor: move;
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

.row-cell.status-cell {
  width: 120px;
  min-width: 120px;
  max-width: 120px;
}

.row-cell.time-cell {
  flex: 1;
  min-width: 100px;
}

.row-cell.actions-cell {
  width: 180px;
  min-width: 180px;
  max-width: 180px;
}

/* 拖拽状态样式 */
.ghost {
  opacity: 0.5;
  background: var(--ant-color-primary-bg);
  border: 2px dashed var(--ant-color-primary);
}

.chosen {
  background: var(--ant-color-primary-bg-hover);
  transform: scale(1.02);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.drag {
  transform: rotate(5deg);
  opacity: 0.8;
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
@media (max-width: 768px) {
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
  .status-cell,
  .time-cell,
  .actions-cell {
    width: 100% !important;
    min-width: auto !important;
    max-width: none !important;
  }
}

/* 深色主题滚动条样式 - 时间选择器 */
.dark :deep(.ant-picker-time-panel-column)::-webkit-scrollbar {
  width: 8px;
}

.dark :deep(.ant-picker-time-panel-column)::-webkit-scrollbar-track {
  background: var(--ant-color-bg-layout);
  border-radius: 4px;
}

.dark :deep(.ant-picker-time-panel-column)::-webkit-scrollbar-thumb {
  background: var(--ant-color-border);
  border-radius: 4px;
  transition: background 0.2s ease;
}

.dark :deep(.ant-picker-time-panel-column)::-webkit-scrollbar-thumb:hover {
  background: var(--ant-color-text-tertiary);
}

/* 时间选择器面板项目样式优化 */
:deep(.ant-picker-time-panel-cell) {
  transition: all 0.2s ease;
}

:deep(.ant-picker-time-panel-cell:hover) {
  background: var(--ant-color-fill-tertiary);
}
</style>

<!-- 全局样式 - 用于时间选择器弹出面板 -->
<style>
/* 全局时间选择器面板滚动条样式 - 浅色主题 */
.ant-picker-dropdown .ant-picker-time-panel-column::-webkit-scrollbar {
  width: 8px;
}

.ant-picker-dropdown .ant-picker-time-panel-column::-webkit-scrollbar-track {
  background: #f5f5f5;
  border-radius: 4px;
}

.ant-picker-dropdown .ant-picker-time-panel-column::-webkit-scrollbar-thumb {
  background: #d9d9d9;
  border-radius: 4px;
  transition: background 0.2s ease;
}

.ant-picker-dropdown .ant-picker-time-panel-column::-webkit-scrollbar-thumb:hover {
  background: #bfbfbf;
}

/* 全局时间选择器面板滚动条样式 - 深色主题 */
:root.dark .ant-picker-dropdown .ant-picker-time-panel-column::-webkit-scrollbar {
  width: 8px;
}

:root.dark .ant-picker-dropdown .ant-picker-time-panel-column::-webkit-scrollbar-track {
  background: #000000;
  border-radius: 4px;
}

:root.dark .ant-picker-dropdown .ant-picker-time-panel-column::-webkit-scrollbar-thumb {
  background: #424242;
  border-radius: 4px;
  transition: background 0.2s ease;
}

:root.dark .ant-picker-dropdown .ant-picker-time-panel-column::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.45);
}

/* 另一种深色模式选择器 */
[data-theme='dark'] .ant-picker-dropdown .ant-picker-time-panel-column::-webkit-scrollbar {
  width: 8px;
}

[data-theme='dark'] .ant-picker-dropdown .ant-picker-time-panel-column::-webkit-scrollbar-track {
  background: #000000;
  border-radius: 4px;
}

[data-theme='dark'] .ant-picker-dropdown .ant-picker-time-panel-column::-webkit-scrollbar-thumb {
  background: #424242;
  border-radius: 4px;
  transition: background 0.2s ease;
}

[data-theme='dark'] .ant-picker-dropdown .ant-picker-time-panel-column::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.45);
}
</style>
