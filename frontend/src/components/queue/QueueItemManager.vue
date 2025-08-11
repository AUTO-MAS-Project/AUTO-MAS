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
        <a-button @click="refreshData" :loading="loading">
          <template #icon>
            <ReloadOutlined />
          </template>
          刷新
        </a-button>
      </a-space>
    </template>

    <div class="queue-items-grid">
      <div
        v-for="item in queueItems"
        :key="item.id"
        class="queue-item-card-item"
      >
        <div class="item-header">
          <div class="item-name">{{ item.name || `项目 ${item.id}` }}</div>
          <a-dropdown>
            <a-button size="small" type="text">
              <MoreOutlined />
            </a-button>
            <template #overlay>
              <a-menu>
                <a-menu-item @click="editQueueItem(item)">
                  <EditOutlined />
                  编辑
                </a-menu-item>
                <a-menu-item @click="deleteQueueItem(item.id)" danger>
                  <DeleteOutlined />
                  删除
                </a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>
        </div>
        <div class="item-content">
          <div class="item-info">
            <div class="info-row">
              <span class="label">状态：</span>
              <a-tag :color="getStatusColor(item.status)">
                {{ getStatusText(item.status) }}
              </a-tag>
            </div>
            <div class="info-row" v-if="item.script">
              <span class="label">脚本：</span>
              <span class="value">{{ item.script }}</span>
            </div>
            <div class="info-row" v-if="item.plan">
              <span class="label">计划：</span>
              <span class="value">{{ item.plan }}</span>
            </div>
            <div class="info-row" v-if="item.description">
              <span class="label">描述：</span>
              <span class="value">{{ item.description }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="!queueItems.length && !loading" class="empty-state">
      <a-empty description="暂无队列项数据" />
    </div>

    <!-- 队列项编辑弹窗 -->
    <a-modal
      v-model:open="modalVisible"
      :title="editingQueueItem ? '编辑队列项' : '添加队列项'"
      @ok="saveQueueItem"
      @cancel="cancelEdit"
      :confirm-loading="saving"
      width="600px"
    >
      <a-form
        ref="formRef"
        :model="form"
        :rules="rules"
        layout="vertical"
      >
        <a-form-item label="项目名称" name="name">
          <a-input v-model:value="form.name" placeholder="请输入项目名称" />
        </a-form-item>
        <a-form-item label="关联脚本" name="script">
          <a-select 
            v-model:value="form.script" 
            placeholder="请选择关联脚本"
            allow-clear
            :options="scriptOptions"
          />
        </a-form-item>
        <a-form-item label="关联计划" name="plan">
          <a-select 
            v-model:value="form.plan" 
            placeholder="请选择关联计划"
            allow-clear
            :options="planOptions"
          />
        </a-form-item>
        <a-form-item label="状态" name="status">
          <a-select v-model:value="form.status" placeholder="请选择状态">
            <a-select-option value="active">激活</a-select-option>
            <a-select-option value="inactive">未激活</a-select-option>
            <a-select-option value="pending">等待中</a-select-option>
            <a-select-option value="running">运行中</a-select-option>
            <a-select-option value="completed">已完成</a-select-option>
            <a-select-option value="failed">失败</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="描述" name="description">
          <a-textarea 
            v-model:value="form.description" 
            placeholder="请输入队列项描述（可选）"
            :rows="3"
          />
        </a-form-item>
      </a-form>
    </a-modal>
  </a-card>
</template>

<script setup lang="ts">
import { ref, reactive, watch, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import {
  PlusOutlined,
  ReloadOutlined,
  EditOutlined,
  DeleteOutlined,
  MoreOutlined
} from '@ant-design/icons-vue'
import { Service } from '@/api'
import type { FormInstance } from 'ant-design-vue'

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
const planOptions = ref<Array<{ label: string; value: string }>>([])

// 表单引用和数据
const formRef = ref<FormInstance>()
const form = reactive({
  name: '',
  script: '',
  plan: '',
  status: 'active',
  description: ''
})

// 表单验证规则
const rules = {
  name: [{ required: true, message: '请输入项目名称', trigger: 'blur' }],
  status: [{ required: true, message: '请选择状态', trigger: 'change' }]
}

// 计算属性 - 使用props传入的数据
const queueItems = ref(props.queueItems)

// 监听props变化
watch(() => props.queueItems, (newQueueItems) => {
  queueItems.value = newQueueItems
}, { deep: true })

// 获取状态文本
const getStatusText = (status: string) => {
  const statusMap: Record<string, string> = {
    active: '激活',
    inactive: '未激活',
    pending: '等待中',
    running: '运行中',
    completed: '已完成',
    failed: '失败'
  }
  return statusMap[status] || status
}

// 获取状态颜色
const getStatusColor = (status: string) => {
  const colorMap: Record<string, string> = {
    active: 'green',
    inactive: 'default',
    pending: 'orange',
    running: 'blue',
    completed: 'cyan',
    failed: 'red'
  }
  return colorMap[status] || 'default'
}

// 加载脚本和计划选项
const loadOptions = async () => {
  try {
    // 加载脚本选项
    const scriptsResponse = await Service.getScriptsApiScriptsGetPost({})
    if (scriptsResponse.code === 200) {
      scriptOptions.value = scriptsResponse.index.map((item: any) => ({
        label: Object.values(item)[0] as string,
        value: Object.keys(item)[0]
      }))
    }

    // 加载计划选项
    const plansResponse = await Service.getPlanApiPlanGetPost({})
    if (plansResponse.code === 200) {
      planOptions.value = plansResponse.index.map((item: any) => ({
        label: Object.values(item)[0] as string,
        value: Object.keys(item)[0]
      }))
    }
  } catch (error) {
    console.error('加载选项失败:', error)
  }
}

// 刷新数据
const refreshData = () => {
  emit('refresh')
}

// 添加队列项
const addQueueItem = () => {
  editingQueueItem.value = null
  Object.assign(form, {
    name: '',
    script: '',
    plan: '',
    status: 'active',
    description: ''
  })
  modalVisible.value = true
}

// 编辑队列项
const editQueueItem = (item: any) => {
  editingQueueItem.value = item
  Object.assign(form, {
    name: item.name || '',
    script: item.script || '',
    plan: item.plan || '',
    status: item.status || 'active',
    description: item.description || ''
  })
  modalVisible.value = true
}

// 保存队列项
const saveQueueItem = async () => {
  try {
    await formRef.value?.validate()
    saving.value = true
    
    if (editingQueueItem.value) {
      // 更新队列项 - 根据API文档格式
      const response = await Service.updateItemApiQueueItemUpdatePost({
        queueId: props.queueId,
        queueItemId: editingQueueItem.value.id,
        data: {
          Info: {
            name: form.name,
            script: form.script,
            plan: form.plan,
            status: form.status,
            description: form.description
          }
        }
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
        queueId: props.queueId
      })
      
      // 2. 用返回的queueItemId更新队列项数据
      if (createResponse.code === 200 && createResponse.queueItemId) {
        const updateResponse = await Service.updateItemApiQueueItemUpdatePost({
          queueId: props.queueId,
          queueItemId: createResponse.queueItemId,
          data: {
            Info: {
              name: form.name,
              script: form.script,
              plan: form.plan,
              status: form.status,
              description: form.description
            }
          }
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
      queueItemId: itemId 
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

/* 队列项网格样式 */
.queue-items-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}

.queue-item-card-item {
  background: var(--ant-color-bg-container);
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  padding: 16px;
  transition: all 0.2s ease;
}

.queue-item-card-item:hover {
  border-color: var(--ant-color-primary);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.item-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.item-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--ant-color-text);
  flex: 1;
  min-width: 0;
  word-break: break-all;
}

.item-content {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.item-info {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.info-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}

.label {
  color: var(--ant-color-text-secondary);
  min-width: 50px;
  flex-shrink: 0;
}

.value {
  color: var(--ant-color-text);
  flex: 1;
  min-width: 0;
  word-break: break-all;
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