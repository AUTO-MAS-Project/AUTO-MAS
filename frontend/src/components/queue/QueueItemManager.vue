<template>
  <a-card title="队列项" class="queue-item-card" :loading="loading">
    <template #extra>
      <a-space>
        <a-button type="primary" @click="addQueueItem" :loading="loading">
          <template #icon>
            <PlusOutlined />
          </template>
          添加队列项
        </a-button>
      </a-space>
    </template>

    <a-table
      :columns="queueColumns"
      :data-source="queueItems"
      :pagination="false"
      size="middle"
      :scroll="{ x: 600 }"
    >
      <template #emptyText>
        <span>暂无队列项</span>
      </template>
      <template #bodyCell="{ column, record, index }">
        <template v-if="column.key === 'index'"> 第{{ index + 1 }}个脚本 </template>
        <template v-else-if="column.key === 'script'">
          {{ getScriptName(record.script) }}
        </template>
        <template v-else-if="column.key === 'actions'">
          <a-space>
            <a-button size="small" @click="editQueueItem(record)">
              <EditOutlined />
              编辑
            </a-button>
            <a-popconfirm
              title="确定要删除这个队列项吗？"
              @confirm="deleteQueueItem(record.id)"
              ok-text="确定"
              cancel-text="取消"
            >
              <a-button size="small" danger>
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
      :title="editingQueueItem ? '编辑队列项' : '添加队列项'"
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
          />
        </a-form-item>
      </a-form>
    </a-modal>
  </a-card>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import type { FormInstance } from 'ant-design-vue'
import { message } from 'ant-design-vue'
import { DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons-vue'
import { Service } from '@/api'

// Props
interface Props {
  queueId: string
  queueItems: any[]
}

const props = defineProps<Props>()

// Emits
const emit = defineEmits<{
  refresh: []
}>()

// 响应式数据
const loading = ref(false)
const saving = ref(false)
const modalVisible = ref(false)
const editingQueueItem = ref<any>(null)

// 选项数据
const scriptOptions = ref<Array<{ label: string; value: string }>>([])

// 获取脚本名称
const getScriptName = (scriptId: string) => {
  if (!scriptId) return '未选择脚本'
  const script = scriptOptions.value.find(script => script.value === scriptId)
  return script?.label || '未知脚本'
}

// 表单引用和数据
const formRef = ref<FormInstance>()
const form = reactive({
  script: '',
})

// 表单验证规则
const rules = {
  script: [{ required: true, message: '请选择关联脚本', trigger: 'change' }],
}

// 表格列配置
const queueColumns = [
  {
    title: '序号',
    key: 'index',
    width: 150,
  },
  {
    title: '脚本名称',
    key: 'script',
    width: 200,
  },
  {
    title: '操作',
    key: 'actions',
    width: 150,
    fixed: 'right',
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
      // 数据已经是正确的格式，直接使用
      scriptOptions.value = scriptsResponse.data || []
      console.log('处理后的脚本选项:', scriptOptions.value)
    } else {
      console.error('脚本API响应错误:', scriptsResponse)
    }
  } catch (error) {
    console.error('加载脚本选项失败:', error)
  }
}

// 添加队列项
const addQueueItem = async () => {
  editingQueueItem.value = null
  Object.assign(form, {
    script: null,
  })

  // 确保在打开弹窗时加载脚本选项
  await loadOptions()
  modalVisible.value = true
}

// 编辑队列项
const editQueueItem = async (item: any) => {
  editingQueueItem.value = item
  Object.assign(form, {
    script: item.script || '',
  })

  // 确保在打开弹窗时加载脚本选项
  await loadOptions()
  modalVisible.value = true
}

// 保存队列项
const saveQueueItem = async () => {
  try {
    await formRef.value?.validate()
    saving.value = true

    if (editingQueueItem.value) {
      // 更新队列项 - 只保存脚本信息
      const response = await Service.updateItemApiQueueItemUpdatePost({
        queueId: props.queueId,
        queueItemId: editingQueueItem.value.id,
        data: {
          Info: {
            ScriptId: form.script,
          },
        },
      })

      if (response.code === 200) {
        message.success('队列项更新成功')
      } else {
        message.error('队列项更新失败: ' + (response.message || '未知错误'))
        return
      }
    } else {
      // 添加队列项 - 先创建，再更新
      // 1. 先创建队列项，只传queueId
      const createResponse = await Service.addItemApiQueueItemAddPost({
        queueId: props.queueId,
      })

      // 2. 用返回的queueItemId更新队列项数据
      if (createResponse.code === 200 && createResponse.queueItemId) {
        const updateResponse = await Service.updateItemApiQueueItemUpdatePost({
          queueId: props.queueId,
          queueItemId: createResponse.queueItemId,
          data: {
            Info: {
              ScriptId: form.script,
            },
          },
        })

        if (updateResponse.code === 200) {
          message.success('队列项添加成功')
        } else {
          message.error('队列项添加失败: ' + (updateResponse.message || '未知错误'))
          return
        }
      } else {
        message.error('创建队列项失败: ' + (createResponse.message || '未知错误'))
        return
      }
    }

    modalVisible.value = false
    emit('refresh')
  } catch (error) {
    console.error('保存队列项失败:', error)
    message.error('保存队列项失败: ' + (error?.message || '网络错误'))
  } finally {
    saving.value = false
  }
}

// 取消编辑
const cancelEdit = () => {
  modalVisible.value = false
  editingQueueItem.value = null
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
  } catch (error) {
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
</style>