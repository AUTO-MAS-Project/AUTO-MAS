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
    <div class="webhook-list" v-if="displayWebhooks.length > 0">
      <div
        v-for="webhook in displayWebhooks"
        :key="webhook.uid"
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
          <a-switch
            v-model:checked="webhook.enabled"
            @change="toggleWebhookEnabled(webhook)"
            size="small"
            :checked-children="'启用'"
            :un-checked-children="'禁用'"
            class="webhook-switch"
          />
          <a-button
            type="text"
            size="small"
            @click="testWebhook(webhook)"
            :loading="testingWebhooks[webhook.uid]"
          >
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
            <a-select-option
              v-for="template in WEBHOOK_TEMPLATES"
              :key="template.name"
              :value="template.name"
            >
              {{ template.name }} - {{ template.description }}
            </a-select-option>
          </a-select>
        </a-form-item>

        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item
              label="Webhook 名称"
              name="name"
              :rules="[{ required: true, message: '请输入 Webhook 名称' }]"
            >
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

        <a-form-item
          label="Webhook URL"
          name="url"
          :rules="[{ required: true, message: '请输入 Webhook URL' }]"
        >
          <a-input
            v-model:value="formData.url"
            placeholder="https://your-webhook-url.com/api/notify"
          />
        </a-form-item>

        <a-form-item label="消息模板">
          <a-textarea
            v-model:value="formData.template"
            :rows="6"
            placeholder="请输入消息模板，支持变量: {title}, {content}, {datetime}, {date}, {time}"
          />
          <div class="template-help">
            <a-typography-text type="secondary" style="font-size: 12px">
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
                style="width: 40%; margin-right: 8px"
              />
              <a-input
                v-model:value="header.value"
                placeholder="Header 值"
                style="width: 40%; margin-right: 8px"
              />
              <a-button type="text" danger @click="removeHeader(index)" size="small">
                <template #icon>
                  <DeleteOutlined />
                </template>
              </a-button>
            </div>
            <a-button
              type="dashed"
              @click="addHeader"
              size="small"
              style="width: 100%; margin-top: 8px"
            >
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
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { message, Modal } from 'ant-design-vue'
import {
  ApiOutlined,
  DeleteOutlined,
  EditOutlined,
  PlayCircleOutlined,
  PlusOutlined,
} from '@ant-design/icons-vue'
import type { CustomWebhook } from '@/types/settings'
import { TEMPLATE_VARIABLES, WEBHOOK_TEMPLATES } from '@/utils/webhookTemplates'
import { Service } from '@/api/services/Service'

// 定义内部使用的Webhook类型
interface WebhookItem {
  uid: string
  name: string
  url: string
  template: string
  method: 'POST' | 'GET'
  enabled: boolean
  headers?: Record<string, string>
}

const props = defineProps<{
  webhooks?: CustomWebhook[]
  scriptId?: string | null
  userId?: string | null
  mode?: 'global' | 'user'
}>()

const emit = defineEmits<{
  'update:webhooks': [webhooks: CustomWebhook[]]
  change: []
}>()

// 响应式数据
const modalVisible = ref(false)
const isEditing = ref(false)
const submitting = ref(false)
const selectedTemplate = ref<string>()
const testingWebhooks = ref<Record<string, boolean>>({})
const formRef = ref()
const loading = ref(false)
const apiWebhooks = ref<WebhookItem[]>([])

// 表单数据
const formData = reactive({
  uid: '',
  name: '',
  url: '',
  template: '',
  method: 'POST' as 'POST' | 'GET',
  enabled: true,
  headersList: [] as Array<{ key: string; value: string }>,
})

// 计算属性 - 根据模式决定显示哪些webhooks
const displayWebhooks = computed(() => {
  if (props.mode === 'global' || (props.scriptId && props.userId)) {
    return apiWebhooks.value
  }
  // 兼容旧的本地模式
  return (props.webhooks || []).map(w => ({
    uid: w.id,
    name: w.name,
    url: w.url,
    template: w.template,
    method: w.method || 'POST',
    enabled: w.enabled,
    headers: w.headers,
  }))
})

// 计算属性 - 兼容旧的props
const webhooks = computed({
  get: () => props.webhooks || [],
  set: value => emit('update:webhooks', value),
})

// 加载Webhook数据
const loadWebhooks = async () => {
  if (props.mode !== 'global' && !props.scriptId && !props.userId) {
    return // 本地模式不需要加载
  }

  loading.value = true
  try {
    const response = await Service.getWebhookApiSettingWebhookGetPost({
      scriptId: props.scriptId || null,
      userId: props.userId || null,
      webhookId: null,
    })

    if (response.code === 200) {
      // 转换API数据为内部格式
      apiWebhooks.value = response.index.map(item => {
        const webhookData = response.data[item.uid]
        return {
          uid: item.uid,
          name: webhookData.Info?.Name || '',
          url: webhookData.Data?.Url || '',
          template: webhookData.Data?.Template || '',
          method: (webhookData.Data?.Method || 'POST') as 'POST' | 'GET',
          enabled: webhookData.Info?.Enabled || false,
          headers: webhookData.Data?.Headers ? JSON.parse(webhookData.Data.Headers) : undefined,
        }
      })
    }
  } catch (error) {
    console.error('加载Webhook失败:', error)
    message.error('加载Webhook配置失败')
  } finally {
    loading.value = false
  }
}

// 显示添加弹窗
const showAddModal = async () => {
  isEditing.value = false
  // 先重置表单，确保清空之前的内容
  resetForm()

  if (props.mode === 'global' || (props.scriptId && props.userId)) {
    // API模式：先调用添加接口获取webhookId
    try {
      const response = await Service.addWebhookApiSettingWebhookAddPost()

      if (response.code === 200) {
        // 只使用返回的webhookId，其他字段使用空白默认值
        formData.uid = response.webhookId
        
        // 强制使用空白默认值，不管后端返回什么数据
        formData.name = ''
        formData.url = ''
        formData.template = ''
        formData.method = 'POST'
        formData.enabled = true
        formData.headersList = []
        
        console.log('创建新Webhook，ID:', response.webhookId)
      }
    } catch (error) {
      console.error('创建Webhook失败:', error)
      message.error('创建Webhook失败')
      return
    }
  }

  modalVisible.value = true
}

// 编辑 Webhook
const editWebhook = (webhook: WebhookItem) => {
  isEditing.value = true
  formData.uid = webhook.uid
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

// 切换 Webhook 启用状态
const toggleWebhookEnabled = async (webhook: WebhookItem) => {
  const newEnabled = webhook.enabled

  if (props.mode === 'global' || (props.scriptId && props.userId)) {
    // API模式：调用更新接口
    try {
      const headers = webhook.headers ? JSON.stringify(webhook.headers) : null
      await Service.updateWebhookApiSettingWebhookUpdatePost({
        scriptId: props.scriptId || null,
        userId: props.userId || null,
        webhookId: webhook.uid,
        data: {
          Info: {
            Name: webhook.name,
            Enabled: newEnabled,
          },
          Data: {
            Url: webhook.url,
            Template: webhook.template,
            Method: webhook.method,
            Headers: headers,
          },
        },
      })

      // 重新加载最新数据
      await loadWebhooks()
      message.success(`Webhook "${webhook.name}" 已${newEnabled ? '启用' : '禁用'}`)
    } catch (error) {
      console.error('更新Webhook状态失败:', error)
      message.error('更新Webhook状态失败')
      // 恢复原状态
      webhook.enabled = !newEnabled
    }
  } else {
    // 本地模式：更新本地数据
    const newWebhooks = webhooks.value.map(w =>
      w.id === webhook.uid ? { ...w, enabled: newEnabled } : w
    )
    webhooks.value = newWebhooks
    emit('change')
    message.success(`Webhook "${webhook.name}" 已${newEnabled ? '启用' : '禁用'}`)
  }
}

// 删除 Webhook
const deleteWebhook = (webhook: WebhookItem) => {
  // 添加二次确认
  Modal.confirm({
    title: '确认删除',
    content: `确定要删除 Webhook "${webhook.name}" 吗？此操作不可撤销。`,
    okText: '确认删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      if (props.mode === 'global' || (props.scriptId && props.userId)) {
        // API模式：调用删除接口
        try {
          await Service.deleteWebhookApiSettingWebhookDeletePost({
            scriptId: props.scriptId || null,
            userId: props.userId || null,
            webhookId: webhook.uid,
          })

          // 重新加载最新数据
          await loadWebhooks()
          message.success('Webhook 删除成功')
        } catch (error) {
          console.error('删除Webhook失败:', error)
          message.error('删除Webhook失败')
        }
      } else {
        // 本地模式：更新本地数据
        const newWebhooks = webhooks.value.filter(w => w.id !== webhook.uid)
        webhooks.value = newWebhooks
        emit('change')
        message.success('Webhook 删除成功')
      }
    },
  })
}

// 测试 Webhook
const testWebhook = async (webhook: WebhookItem) => {
  testingWebhooks.value[webhook.uid] = true

  try {
    const headersJson = webhook.headers ? JSON.stringify(webhook.headers) : null

    const response = await Service.testWebhookApiSettingWebhookTestPost({
      scriptId: props.mode === 'global' ? null : props.scriptId || null,
      userId: props.mode === 'global' ? null : props.userId || null,
      data: {
        Info: {
          Name: webhook.name,
          Enabled: webhook.enabled,
        },
        Data: {
          Url: webhook.url,
          Template: webhook.template,
          Method: webhook.method,
          Headers: headersJson,
        },
      },
    })

    if (response.code === 200) {
      message.success(`Webhook "${webhook.name}" 测试成功`)
    } else {
      message.error(`Webhook 测试失败: ${response.message || '未知错误'}`)
    }
  } catch (error: any) {
    console.error('Webhook测试错误:', error)
    message.error(
      `Webhook 测试失败: ${error.response?.data?.message || error.message || '网络错误'}`
    )
  } finally {
    testingWebhooks.value[webhook.uid] = false
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
      formData.headersList = Object.entries(template.headers).map(([key, value]) => ({
        key,
        value,
      }))
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
  formData.uid = ''
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

    if (props.mode === 'global' || (props.scriptId && props.userId)) {
      // API模式：调用更新接口
      try {
        const headersJson = Object.keys(headers).length > 0 ? JSON.stringify(headers) : null

        await Service.updateWebhookApiSettingWebhookUpdatePost({
          scriptId: props.scriptId || null,
          userId: props.userId || null,
          webhookId: formData.uid,
          data: {
            Info: {
              Name: formData.name,
              Enabled: formData.enabled,
            },
            Data: {
              Url: formData.url,
              Template: formData.template,
              Method: formData.method,
              Headers: headersJson,
            },
          },
        })

        // 重新加载最新数据
        await loadWebhooks()
        
        if (isEditing.value) {
          message.success('Webhook 更新成功')
        } else {
          message.success('Webhook 添加成功')
        }

        modalVisible.value = false
        // 延迟重置表单，确保弹窗完全关闭后再重置
        setTimeout(() => {
          resetForm()
        }, 100)
      } catch (error) {
        console.error('保存Webhook失败:', error)
        message.error('保存Webhook失败')
      }
    } else {
      // 本地模式：更新本地数据
      const webhookData: CustomWebhook = {
        id: formData.uid || `webhook_${Date.now()}`,
        name: formData.name,
        url: formData.url,
        template: formData.template,
        method: formData.method,
        enabled: formData.enabled,
        headers: Object.keys(headers).length > 0 ? headers : undefined,
      }

      let newWebhooks: CustomWebhook[]

      if (isEditing.value) {
        // 更新现有 Webhook
        newWebhooks = webhooks.value.map(w => (w.id === webhookData.id ? webhookData : w))
        message.success('Webhook 更新成功')
      } else {
        // 添加新 Webhook
        newWebhooks = [...webhooks.value, webhookData]
        message.success('Webhook 添加成功')
      }

      webhooks.value = newWebhooks
      emit('change')
      modalVisible.value = false
      // 延迟重置表单，确保弹窗完全关闭后再重置
      setTimeout(() => {
        resetForm()
      }, 100)
    }
  } catch (error) {
    console.error('表单验证失败:', error)
  } finally {
    submitting.value = false
  }
}

// 取消操作
const handleCancel = () => {
  modalVisible.value = false
  // 延迟重置表单，确保弹窗完全关闭后再重置
  setTimeout(() => {
    resetForm()
  }, 100)
}

// 组件挂载时加载数据
onMounted(() => {
  loadWebhooks()
})

// 监听props变化，重新加载数据
watch(
  [() => props.scriptId, () => props.userId, () => props.mode],
  () => {
    loadWebhooks()
  },
  { deep: true }
)
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
  align-items: center;
}

.webhook-switch {
  margin-right: 8px;
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