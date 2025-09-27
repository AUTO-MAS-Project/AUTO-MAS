<template>
  <div class="webhook-manager">
    <div class="webhook-header">
      <h3>自定义 Webhook 通知</h3>
      <a-button type="primary" @click="showAddModal" size="middle">
        <template #icon>
          <PlusOutlined />
        </template>
        添加 Webhook
      </a-button>
    </div>

    <!-- Webhook 列表 -->
    <div class="webhook-list" v-if="webhooks.length > 0">
      <div 
        v-for="webhook in webhooks" 
        :key="webhook.id" 
        class="webhook-item"
        :class="{ 'webhook-disabled': !webhook.enabled }"
      >
        <div class="webhook-info">
          <div class="webhook-name">
            <span class="name-text">{{ webhook.name }}</span>
            <a-tag :color="webhook.enabled ? 'green' : 'red'" size="small">
              {{ webhook.enabled ? '启用' : '禁用' }}
            </a-tag>
          </div>
          <div class="webhook-url">{{ webhook.url }}</div>
        </div>
        <div class="webhook-actions">
          <a-button type="text" size="small" @click="testWebhook(webhook)" :loading="testingWebhooks[webhook.id]">
            <template #icon>
              <PlayCircleOutlined />
            </template>
            测试
          </a-button>
          <a-button type="text" size="small" @click="editWebhook(webhook)">
            <template #icon>
              <EditOutlined />
            </template>
            编辑
          </a-button>
          <a-button type="text" size="small" danger @click="deleteWebhook(webhook)">
            <template #icon>
              <DeleteOutlined />
            </template>
            删除
          </a-button>
        </div>
      </div>
    </div>

    <div v-else class="empty-state">
      <div class="empty-icon">
        <ApiOutlined />
      </div>
      <div class="empty-text">暂无自定义 Webhook</div>
      <div class="empty-description">点击上方按钮添加您的第一个 Webhook</div>
    </div>

    <!-- 添加/编辑 Webhook 弹窗 -->
    <a-modal
      v-model:open="modalVisible"
      :title="isEditing ? '编辑 Webhook' : '添加 Webhook'"
      width="800px"
      :ok-text="isEditing ? '更新' : '添加'"
      @ok="handleSubmit"
      @cancel="handleCancel"
      :confirm-loading="submitting"
    >
      <a-form :model="formData" layout="vertical" ref="formRef">
        <!-- 模板选择放在最上面 -->
        <a-form-item label="选择模板">
          <a-select 
            v-model:value="selectedTemplate" 
            placeholder="选择预设模板或自定义"
            @change="applyTemplate"
            allow-clear
          >
            <a-select-option v-for="template in WEBHOOK_TEMPLATES" :key="template.name" :value="template.name">
              {{ template.name }} - {{ template.description }}
            </a-select-option>
          </a-select>
        </a-form-item>

        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="Webhook 名称" name="name" :rules="[{ required: true, message: '请输入 Webhook 名称' }]">
              <a-input v-model:value="formData.name" placeholder="请输入 Webhook 名称" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="请求方法" name="method">
              <a-select v-model:value="formData.method">
                <a-select-option value="POST">POST</a-select-option>
                <a-select-option value="GET">GET</a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
        </a-row>

        <a-form-item label="Webhook URL" name="url" :rules="[{ required: true, message: '请输入 Webhook URL' }]">
          <a-input v-model:value="formData.url" placeholder="https://your-webhook-url.com/api/notify" />
        </a-form-item>

        <a-form-item label="消息模板">
          <a-textarea 
            v-model:value="formData.template" 
            :rows="6"
            placeholder="请输入消息模板，支持变量: {title}, {content}, {datetime}, {date}, {time}"
          />
          <div class="template-help">
            <a-typography-text type="secondary" style="font-size: 12px;">
              支持的变量：
              <a-tag size="small" v-for="variable in TEMPLATE_VARIABLES" :key="variable.name">
                {{ variable.name }}
              </a-tag>
            </a-typography-text>
          </div>
        </a-form-item>

        <a-form-item label="自定义请求头 (可选)">
          <div class="headers-input">
            <div v-for="(header, index) in formData.headersList" :key="index" class="header-row">
              <a-input 
                v-model:value="header.key" 
                placeholder="Header 名称" 
                style="width: 40%; margin-right: 8px;"
              />
              <a-input 
                v-model:value="header.value" 
                placeholder="Header 值" 
                style="width: 40%; margin-right: 8px;"
              />
              <a-button type="text" danger @click="removeHeader(index)" size="small">
                <template #icon>
                  <DeleteOutlined />
                </template>
              </a-button>
            </div>
            <a-button type="dashed" @click="addHeader" size="small" style="width: 100%; margin-top: 8px;">
              <template #icon>
                <PlusOutlined />
              </template>
              添加请求头
            </a-button>
          </div>
        </a-form-item>

        <a-form-item>
          <a-checkbox v-model:checked="formData.enabled">启用此 Webhook</a-checkbox>
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'
import { message } from 'ant-design-vue'
import { 
  PlusOutlined, 
  EditOutlined, 
  DeleteOutlined, 
  PlayCircleOutlined,
  ApiOutlined
} from '@ant-design/icons-vue'
import type { CustomWebhook } from '@/types/settings'
import { WEBHOOK_TEMPLATES, TEMPLATE_VARIABLES } from '@/utils/webhookTemplates'
import { Service } from '@/api/services/Service'

const props = defineProps<{
  webhooks: CustomWebhook[]
}>()

const emit = defineEmits<{
  'update:webhooks': [webhooks: CustomWebhook[]]
  'change': []
}>()

// 响应式数据
const modalVisible = ref(false)
const isEditing = ref(false)
const submitting = ref(false)
const selectedTemplate = ref<string>()
const testingWebhooks = ref<Record<string, boolean>>({})
const formRef = ref()

// 表单数据
const formData = reactive({
  id: '',
  name: '',
  url: '',
  template: '',
  method: 'POST' as 'POST' | 'GET',
  enabled: true,
  headersList: [] as Array<{ key: string; value: string }>
})

// 计算属性
const webhooks = computed({
  get: () => props.webhooks || [],
  set: (value) => emit('update:webhooks', value)
})

// 监听 webhooks 变化
watch(() => props.webhooks, (newWebhooks) => {
  // 可以在这里处理 webhooks 变化的逻辑
}, { deep: true })

// 显示添加弹窗
const showAddModal = () => {
  isEditing.value = false
  resetForm()
  modalVisible.value = true
}

// 编辑 Webhook
const editWebhook = (webhook: CustomWebhook) => {
  isEditing.value = true
  formData.id = webhook.id
  formData.name = webhook.name
  formData.url = webhook.url
  formData.template = webhook.template
  formData.method = webhook.method || 'POST'
  formData.enabled = webhook.enabled
  
  // 转换 headers 为列表格式
  formData.headersList = webhook.headers 
    ? Object.entries(webhook.headers).map(([key, value]) => ({ key, value }))
    : []
  
  modalVisible.value = true
}

// 删除 Webhook
const deleteWebhook = (webhook: CustomWebhook) => {
  const newWebhooks = webhooks.value.filter(w => w.id !== webhook.id)
  webhooks.value = newWebhooks
  emit('change')
  message.success('Webhook 删除成功')
}

// 测试 Webhook
const testWebhook = async (webhook: CustomWebhook) => {
  testingWebhooks.value[webhook.id] = true
  
  try {
    const response = await Service.testWebhookApiSettingWebhookTestPost({
      id: webhook.id,
      name: webhook.name,
      url: webhook.url,
      template: webhook.template,
      method: webhook.method || 'POST',
      enabled: webhook.enabled,
      headers: webhook.headers || {}
    })
    
    if (response.code === 200) {
      message.success(`Webhook "${webhook.name}" 测试成功`)
    } else {
      message.error(`Webhook 测试失败: ${response.message || '未知错误'}`)
    }
  } catch (error: any) {
    console.error('Webhook测试错误:', error)
    message.error(`Webhook 测试失败: ${error.response?.data?.message || error.message || '网络错误'}`)
  } finally {
    testingWebhooks.value[webhook.id] = false
  }
}

// 应用模板
const applyTemplate = (templateName: string) => {
  if (!templateName) {
    // 清空模板时不做任何操作
    return
  }
  
  const template = WEBHOOK_TEMPLATES.find(t => t.name === templateName)
  if (template) {
    // 强制清空所有内容再应用新模板
    formData.name = ''
    formData.url = template.example || ''
    formData.template = template.template
    formData.method = template.method
    formData.headersList = []
    
    // 设置默认请求头
    if (template.headers) {
      formData.headersList = Object.entries(template.headers).map(([key, value]) => ({ key, value }))
    }
  }
}

// 添加请求头
const addHeader = () => {
  formData.headersList.push({ key: '', value: '' })
}

// 删除请求头
const removeHeader = (index: number) => {
  formData.headersList.splice(index, 1)
}

// 重置表单
const resetForm = () => {
  formData.id = ''
  formData.name = ''
  formData.url = ''
  formData.template = ''
  formData.method = 'POST'
  formData.enabled = true
  formData.headersList = []
  selectedTemplate.value = undefined
}

// 提交表单
const handleSubmit = async () => {
  try {
    await formRef.value.validate()
    submitting.value = true
    
    // 转换 headersList 为 headers 对象
    const headers: Record<string, string> = {}
    formData.headersList.forEach(header => {
      if (header.key && header.value) {
        headers[header.key] = header.value
      }
    })
    
    const webhookData: CustomWebhook = {
      id: formData.id || `webhook_${Date.now()}`,
      name: formData.name,
      url: formData.url,
      template: formData.template,
      method: formData.method,
      enabled: formData.enabled,
      headers: Object.keys(headers).length > 0 ? headers : undefined
    }
    
    let newWebhooks: CustomWebhook[]
    
    if (isEditing.value) {
      // 更新现有 Webhook
      newWebhooks = webhooks.value.map(w => 
        w.id === webhookData.id ? webhookData : w
      )
      message.success('Webhook 更新成功')
    } else {
      // 添加新 Webhook
      newWebhooks = [...webhooks.value, webhookData]
      message.success('Webhook 添加成功')
    }
    
    webhooks.value = newWebhooks
    emit('change')
    modalVisible.value = false
    
  } catch (error) {
    console.error('表单验证失败:', error)
  } finally {
    submitting.value = false
  }
}

// 取消操作
const handleCancel = () => {
  modalVisible.value = false
  resetForm()
}
</script>

<style scoped>
.webhook-manager {
  margin-top: 16px;
}

.webhook-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.webhook-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.webhook-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.webhook-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
  transition: all 0.2s ease;
}

.webhook-item:hover {
  border-color: var(--ant-color-primary);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.webhook-item.webhook-disabled {
  opacity: 0.6;
  background: var(--ant-color-bg-layout);
}

.webhook-info {
  flex: 1;
  min-width: 0;
}

.webhook-name {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.name-text {
  font-weight: 500;
  font-size: 14px;
}

.webhook-url {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
  word-break: break-all;
}

.webhook-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

.empty-state {
  text-align: center;
  padding: 48px 24px;
  color: var(--ant-color-text-secondary);
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
  opacity: 0.5;
}

.empty-text {
  font-size: 16px;
  margin-bottom: 8px;
}

.empty-description {
  font-size: 14px;
}

.template-help {
  margin-top: 8px;
}

.headers-input {
  border: 1px solid var(--ant-color-border);
  border-radius: 6px;
  padding: 12px;
  background: var(--ant-color-bg-layout);
}

.header-row {
  display: flex;
  align-items: center;
  margin-bottom: 8px;
}

.header-row:last-child {
  margin-bottom: 0;
}

/* 深色模式适配 */
@media (prefers-color-scheme: dark) {
  .webhook-item {
    border-color: var(--ant-color-border-secondary);
  }
  
  .webhook-item.webhook-disabled {
    background: var(--ant-color-bg-base);
  }
  
  .headers-input {
    background: var(--ant-color-bg-base);
    border-color: var(--ant-color-border-secondary);
  }
}

/* 响应式设计 */
@media (max-width: 768px) {
  .webhook-item {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }
  
  .webhook-actions {
    width: 100%;
    justify-content: flex-end;
  }
  
  .webhook-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }
}
</style>