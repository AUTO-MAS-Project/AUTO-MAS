<template>
  <a-card title="任务列表" class="queue-item-card">
    <template #extra>
      <a-space>
        <a-button type="primary" @click="addQueueItem" :loading="loading">
          <template #icon>
            <PlusOutlined />
          </template>
          添加任务
        </a-button>
      </a-space>
    </template>

    <a-table
      :columns="queueColumns"
      :data-source="queueItems"
      :pagination="false"
      size="middle"
      :scroll="{ x: false, y: false }"
      table-layout="auto"
      class="queue-table"
    >
      <template #emptyText>
        <span>暂无任务</span>
      </template>
      <template #bodyCell="{ column, record, index }">
        <template v-if="column.key === 'index'"> {{ index + 1 }} </template>
        <template v-else-if="column.key === 'script'">
          <a-select
            v-model:value="record.script"
            @change="updateQueueItemScript(record)"
            size="small"
            style="width: 200px"
            class="script-select"
            placeholder="请选择脚本"
            :options="scriptOptions"
            allow-clear
          />
        </template>
        <template v-else-if="column.key === 'actions'">
          <a-space>
            <a-popconfirm
              title="确定要删除这个任务吗？"
              @confirm="deleteQueueItem(record.id)"
              ok-text="确定"
              cancel-text="取消"
            >
              <a-button size="middle" danger>
                <DeleteOutlined />
                删除
              </a-button>
            </a-popconfirm>
          </a-space>
        </template>
      </template>
    </a-table>

    <!-- 队列项编辑弹窗 -->
    <a-modal
      v-model:open="modalVisible"
      :title="editingQueueItem ? '编辑任务' : '添加任务'"
      @ok="saveQueueItem"
      @cancel="cancelEdit"
      :confirm-loading="saving"
      width="600px"
    >
      <a-form ref="formRef" :model="form" :rules="rules" layout="vertical">
        <a-form-item label="关联脚本" name="script">
          <a-select
            v-model:value="form.script"
            placeholder="请选择关联脚本"
            allow-clear
            :options="scriptOptions"
            class="script-select"
          />
        </a-form-item>
      </a-form>
    </a-modal>
  </a-card>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons-vue'
import { Service } from '@/api'

// Props
interface Props {
  queueId: string
  queueItems: Array<{
    id: string
    script: string | null
  }>
}

const props = defineProps<Props>()

// Emits
const emit = defineEmits<{
  refresh: []
}>()

// 响应式数据
const loading = ref(false)

// 脚本选项类型定义
interface ScriptOption {
  label: string
  value: string | null
}

// 脚本选项
const scriptOptions = ref<ScriptOption[]>([])

// 表格列配置
const queueColumns = [
  {
    title: '序号',
    key: 'index',
    width: 80,
    align: 'center',
  },
  {
    title: '脚本任务',
    key: 'script',
    align: 'center',
    ellipsis: true,
  },
  {
    title: '操作',
    key: 'actions',
    width: 180,
    align: 'center',
  },
]

// 计算属性 - 使用props传入的数据
const queueItems = ref(props.queueItems)

// 监听props变化
watch(
  () => props.queueItems,
  newQueueItems => {
    queueItems.value = newQueueItems
  },
  { deep: true }
)

// 加载脚本选项
const loadOptions = async () => {
  try {
    console.log('开始加载脚本选项...')
    // 使用正确的API获取脚本下拉框选项
    const scriptsResponse = await Service.getScriptComboxApiInfoComboxScriptPost()
    console.log('脚本API响应:', scriptsResponse)

    if (scriptsResponse.code === 200) {
      console.log('脚本API响应数据:', scriptsResponse.data)
      // 直接使用接口返回的combox选项
      scriptOptions.value = scriptsResponse.data || []
      console.log('处理后的脚本选项:', scriptOptions.value)
    } else {
      console.error('脚本API响应错误:', scriptsResponse)
    }
  } catch (error) {
    console.error('加载脚本选项失败:', error)
  }
}

// 更新队列项脚本
const updateQueueItemScript = async (record: any) => {
  const oldScript = record.script
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
      message.success('脚本更新成功')
      // 不触发刷新，避免界面闪烁
    } else {
      // 回滚本地变更
      record.script = oldScript
      message.error('脚本更新失败: ' + (response.message || '未知错误'))
    }
  } catch (error: any) {
    // 发生异常时回滚
    record.script = oldScript
    console.error('更新脚本失败:', error)
    message.error('更新脚本失败: ' + (error?.message || '网络错误'))
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
      message.success('任务添加成功')
      // 只在添加成功后刷新，避免不必要的闪烁
      emit('refresh')
    } else {
      message.error('任务添加失败: ' + (createResponse.message || '未知错误'))
    }
  } catch (error: any) {
    console.error('添加任务失败:', error)
    message.error('添加任务失败: ' + (error?.message || '网络错误'))
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
      message.success('队列项删除成功')
      // 确保删除后刷新数据
      emit('refresh')
    } else {
      message.error('删除队列项失败: ' + (response.message || '未知错误'))
    }
  } catch (error: any) {
    console.error('删除队列项失败:', error)
    message.error('删除队列项失败: ' + (error?.message || '网络错误'))
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

/* 空状态样式 */
.empty-state {
  text-align: center;
  padding: 40px 0;
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
  font-size: 13px !important;
  min-height: 28px !important;
  line-height: 26px !important;
  box-shadow: none !important;
  text-align: center;
}

.script-select :deep(.ant-select-selection-item) {
  line-height: 26px !important;
  color: var(--ant-color-text) !important;
  font-size: 13px !important;
  font-weight: 500;
  padding: 0;
  margin: 0;
}

.script-select :deep(.ant-select-selection-placeholder) {
  line-height: 26px !important;
  color: var(--ant-color-text-placeholder) !important;
  font-size: 13px !important;
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
  font-size: 13px !important;
}

.script-select :deep(.ant-select-item-option-content) {
  font-size: 13px !important;
}
</style>