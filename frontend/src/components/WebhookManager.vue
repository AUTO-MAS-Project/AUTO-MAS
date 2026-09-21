<template>
  <div class="webhook-manager" :class="{ compact }">
    <div v-if="!compact" class="webhook-header">
      <h3>{{ t('comp.customWebhooks') }}</h3>
      <a-button type="primary" size="middle" @click="showAddModal">
        <template #icon>
          <PlusOutlined />
        </template>
        {{ t('comp.addWebhook') }}
      </a-button>
    </div>

    <!-- Webhook 列表 -->
    <div v-if="displayWebhooks.length > 0" class="webhook-list">
      <div
        v-for="webhook in displayWebhooks"
        :key="webhook.uid"
        class="webhook-item"
        :class="{ 'webhook-disabled': !webhook.enabled, compact }"
      >
        <div class="webhook-info">
          <div class="webhook-name">
            <span class="name-text">{{ webhook.name }}</span>
            <a-tag v-if="!compact" :color="webhook.enabled ? 'green' : 'red'" size="small">
              {{ webhook.enabled ? '启用' : '禁用' }}
            </a-tag>
          </div>
          <div class="webhook-url" :title="webhook.url">{{ webhook.url }}</div>
        </div>
        <div class="webhook-actions" :class="{ compact }">
          <a-switch
            v-model:checked="webhook.enabled"
            size="small"
            :checked-children="compact ? undefined : '启用'"
            :un-checked-children="compact ? undefined : '禁用'"
            class="webhook-switch"
            @change="toggleWebhookEnabled(webhook)"
          />
          <template v-if="compact">
            <a-button
              type="text"
              size="small"
              :loading="testingWebhooks[webhook.uid]"
              @click="testWebhook(webhook)"
            >
              {{ t('comp.test') }}
            </a-button>
            <a-button type="text" size="small" @click="editWebhook(webhook)">
              {{ t('comp.edit') }}
            </a-button>
            <a-button type="text" size="small" danger @click="deleteWebhook(webhook)">
              {{ t('comp.delete') }}
            </a-button>
          </template>
          <template v-else>
            <a-button
              type="text"
              size="small"
              :loading="testingWebhooks[webhook.uid]"
              @click="testWebhook(webhook)"
            >
              <template #icon>
                <PlayCircleOutlined />
              </template>
              {{ t('comp.test') }}
            </a-button>
            <a-button type="text" size="small" @click="editWebhook(webhook)">
              <template #icon>
                <EditOutlined />
              </template>
              {{ t('comp.edit') }}
            </a-button>
            <a-button type="text" size="small" danger @click="deleteWebhook(webhook)">
              <template #icon>
                <DeleteOutlined />
              </template>
              {{ t('comp.delete') }}
            </a-button>
          </template>
        </div>
      </div>
    </div>

    <div v-else class="empty-state">
      <div class="empty-icon">
        <ApiOutlined />
      </div>
      <div class="empty-text">{{ t('comp.noCustomWebhooks') }}</div>
      <div v-if="!compact" class="empty-description">
        {{ t('comp.useButtonAboveAdd') }}
      </div>
    </div>

    <!-- 紧凑模式（通知配置弹窗里）添加按钮挪到底部虚线按钮 -->
    <a-button v-if="compact" type="dashed" class="add-hook" @click="showAddModal">
      <template #icon>
        <PlusOutlined />
      </template>
      {{ t('comp.addWebhook') }}
    </a-button>

    <!-- 添加/编辑 Webhook 弹窗 -->
    <a-modal
      v-model:open="modalVisible"
      :title="isEditing ? '编辑 Webhook' : '添加 Webhook'"
      :width="compact ? '560px' : '800px'"
      :get-container="getPopupContainer"
      :z-index="compact ? 1050 : undefined"
      :centered="compact"
      :body-style="
        compact ? { maxHeight: 'calc(100vh - 220px)', overflowY: 'auto' } : undefined
      "
      :ok-text="isEditing ? '更新' : '添加'"
      :confirm-loading="submitting"
      @ok="handleSubmit"
      @cancel="handleCancel"
    >
      <a-form ref="formRef" :model="formData" layout="vertical">
        <!-- 模板选择放在最上面 -->
        <a-form-item :label="t('comp.pickTemplate')">
          <a-select
            v-model:value="selectedTemplate"
            :placeholder="t('comp.pickPresetTemplateWrite')"
            :get-popup-container="getPopupContainer"
            allow-clear
            @change="applyTemplate"
          >
            <a-select-option
              v-for="template in WEBHOOK_TEMPLATES"
              :key="template.name"
              :value="template.name"
            >
              {{ template.name }} - {{ t(template.descriptionKey) }}
            </a-select-option>
          </a-select>
        </a-form-item>

        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item
              :label="t('comp.webhookName')"
              name="name"
              :rules="[{ required: true, message: '请输入 Webhook 名称' }]"
            >
              <a-input v-model:value="formData.name" :placeholder="t('comp.enterWebhookName')" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item :label="t('comp.method')" name="method">
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

        <a-form-item :label="t('comp.messageTemplate')">
          <a-textarea
            v-model:value="formData.template"
            :rows="6"
            :placeholder="t('comp.enterMessageTemplateVariables')"
          />
          <div class="template-help">
            <a-typography-text type="secondary" style="font-size: 12px">
              {{ t('comp.supportedVariables') }}
              <a-tag v-for="variable in TEMPLATE_VARIABLES" :key="variable.name" size="small">
                {{ variable.name }}
              </a-tag>
            </a-typography-text>
          </div>
        </a-form-item>

        <a-form-item :label="t('comp.customHeadersOptional')">
          <div class="headers-input">
            <div v-for="(header, index) in formData.headersList" :key="index" class="header-row">
              <a-input
                v-model:value="header.key"
                :placeholder="t('comp.headerName')"
                style="width: 40%; margin-right: 8px"
              />
              <a-input
                v-model:value="header.value"
                :placeholder="t('comp.headerValue')"
                style="width: 40%; margin-right: 8px"
              />
              <a-button type="text" danger size="small" @click="removeHeader(index)">
                <template #icon>
                  <DeleteOutlined />
                </template>
              </a-button>
            </div>
            <a-button
              type="dashed"
              size="small"
              style="width: 100%; margin-top: 8px"
              @click="addHeader"
            >
              <template #icon>
                <PlusOutlined />
              </template>
              {{ t('comp.addHeader') }}
            </a-button>
          </div>
        </a-form-item>

        <a-form-item>
          <a-checkbox v-model:checked="formData.enabled">{{
            t('comp.enableThisWebhook')
          }}</a-checkbox>
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { message, Modal } from 'ant-design-vue'
import {
  ApiOutlined,
  DeleteOutlined,
  EditOutlined,
  PlayCircleOutlined,
  PlusOutlined,
} from '@ant-design/icons-vue'
import { TEMPLATE_VARIABLES, WEBHOOK_TEMPLATES } from '@/utils/webhookTemplates'
import { Service } from '@/api/services/Service'

const { t } = useI18n()

const logger = window.electronAPI.getLogger('Webhook管理器')

// update/test 接口的载荷形状：开关切换、提交保存、测试三处写入共用
const toWebhookPayload = (
  name: string,
  url: string,
  template: string,
  method: 'POST' | 'GET',
  enabled: boolean,
  headers: string | null
) => ({
  Info: { Name: name, Enabled: enabled },
  Data: { Url: url, Template: template, Method: method, Headers: headers },
})

// 定义Webhook类型（兼容旧props用）
interface CustomWebhook {
  id: string
  name: string
  url: string
  template: string
  enabled: boolean
  headers?: Record<string, string>
  method?: 'POST' | 'GET'
}

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

const props = withDefaults(
  defineProps<{
    webhooks?: CustomWebhook[]
    scriptId?: string | null
    userId?: string | null
    mode?: 'global' | 'user'
    /** 紧凑排版：不渲染自带标题与右上角添加按钮，条目两行 + 文字链接操作 */
    compact?: boolean
    /** 弹窗挂载容器；通知配置弹窗场景传其 wrap 节点，默认挂 body（12 个用户编辑页不变） */
    getPopupContainer?: () => HTMLElement
  }>(),
  {
    webhooks: undefined,
    scriptId: null,
    userId: null,
    // mode 显式默认 undefined：保持与既有调用点的 undefined 语义一致
    mode: undefined,
    compact: false,
    getPopupContainer: undefined,
  }
)

const emit = defineEmits<{
  'update:webhooks': [webhooks: CustomWebhook[]]
  change: []
  /** 列表重载后透传条目，供宿主（通知卡片摘要）使用 */
  listed: [webhooks: WebhookItem[]]
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
    let response

    if (props.mode === 'global') {
      // 全局模式：使用setting接口
      response = await Service.getWebhookApiSettingWebhookGetPost({
        scriptId: null,
        userId: null,
        webhookId: null,
      })
    } else {
      // 用户模式：使用scripts接口
      response = await Service.getWebhookApiScriptsWebhookGetPost({
        scriptId: props.scriptId || null,
        userId: props.userId || null,
        webhookId: null,
      })
    }

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
      emit('listed', apiWebhooks.value)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载Webhook失败: ${errorMsg}`)
    message.error(t('comp.couldNotLoadWebhook'))
  } finally {
    loading.value = false
  }
}

// 显示添加弹窗
const showAddModal = () => {
  isEditing.value = false
  // 先重置表单，确保清空之前的内容。
  // 记录延迟到确认提交时才创建：取消（点遮罩/Esc）不产生任何空记录。
  resetForm()
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

      if (props.mode === 'global') {
        // 全局模式：使用setting接口
        await Service.updateWebhookApiSettingWebhookUpdatePost({
          scriptId: null,
          userId: null,
          webhookId: webhook.uid,
          data: toWebhookPayload(
            webhook.name,
            webhook.url,
            webhook.template,
            webhook.method,
            newEnabled,
            headers
          ),
        })
      } else {
        // 用户模式：使用scripts接口
        await Service.updateWebhookApiScriptsWebhookUpdatePost({
          scriptId: props.scriptId || null,
          userId: props.userId || null,
          webhookId: webhook.uid,
          data: toWebhookPayload(
            webhook.name,
            webhook.url,
            webhook.template,
            webhook.method,
            newEnabled,
            headers
          ),
        })
      }

      // 重新加载最新数据
      await loadWebhooks()
      message.success(t('comp.webhookP0P1', { p0: webhook.name, p1: newEnabled ? '启用' : '禁用' }))
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`更新Webhook状态失败: ${errorMsg}`)
      message.error(t('comp.couldNotUpdateWebhook'))
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
    message.success(t('comp.webhookP0P1', { p0: webhook.name, p1: newEnabled ? '启用' : '禁用' }))
  }
}

// 删除 Webhook
const deleteWebhook = (webhook: WebhookItem) => {
  // 添加二次确认
  Modal.confirm({
    title: t('comp.confirmDeletion'),
    content: `确定要删除 Webhook "${webhook.name}" 吗？此操作不可撤销。`,
    okText: t('comp.confirmDeletion'),
    okType: 'danger',
    cancelText: t('comp.cancel'),
    // 确认框挂 body（z 950：在渠道配置弹窗 900 之上、标题栏 1000 之下）——
    // 挂进弹窗 wrap 会按普通流布局排到 wrap 顶部，被标题栏盖住不可见
    zIndex: props.compact ? 950 : undefined,
    centered: props.compact,
    async onOk() {
      if (props.mode === 'global' || (props.scriptId && props.userId)) {
        // API模式：调用删除接口
        try {
          if (props.mode === 'global') {
            // 全局模式：使用setting接口
            await Service.deleteWebhookApiSettingWebhookDeletePost({
              scriptId: null,
              userId: null,
              webhookId: webhook.uid,
            })
          } else {
            // 用户模式：使用scripts接口
            await Service.deleteWebhookApiScriptsWebhookDeletePost({
              scriptId: props.scriptId || null,
              userId: props.userId || null,
              webhookId: webhook.uid,
            })
          }

          // 重新加载最新数据
          await loadWebhooks()
          message.success(t('comp.webhookDeleted'))
        } catch (error) {
          const errorMsg = error instanceof Error ? error.message : String(error)
          logger.error(`删除Webhook失败: ${errorMsg}`)
          message.error(t('comp.couldNotDeleteWebhook'))
        }
      } else {
        // 本地模式：更新本地数据
        const newWebhooks = webhooks.value.filter(w => w.id !== webhook.uid)
        webhooks.value = newWebhooks
        emit('change')
        message.success(t('comp.webhookDeleted'))
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
      data: toWebhookPayload(
        webhook.name,
        webhook.url,
        webhook.template,
        webhook.method,
        webhook.enabled,
        headersJson
      ),
    })

    if (response.code === 200) {
      message.success(t('comp.webhookP0TestedSuccessfully', { p0: webhook.name }))
    } else {
      message.error(t('comp.webhookTestFailedP0', { p0: response.message || '未知错误' }))
    }
  } catch (error: any) {
    const errorMsg =
      error.response?.data?.message || (error instanceof Error ? error.message : '网络错误')
    logger.error(`Webhook测试错误: ${errorMsg}`)
    message.error(t('comp.webhookTestFailedP0', { p0: errorMsg }))
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
      // API模式：新增时先创建记录拿到 uid，再写入表单内容
      try {
        if (!isEditing.value) {
          const addResponse =
            props.mode === 'global'
              ? await Service.addWebhookApiSettingWebhookAddPost()
              : await Service.addWebhookApiScriptsWebhookAddPost({
                  scriptId: props.scriptId || null,
                  userId: props.userId || null,
                })
          if (addResponse.code !== 200) {
            throw new Error(addResponse.message || '')
          }
          formData.uid = addResponse.webhookId
          logger.info(`创建新Webhook，ID: ${addResponse.webhookId}`)
        }

        const headersJson = Object.keys(headers).length > 0 ? JSON.stringify(headers) : null

        if (props.mode === 'global') {
          // 全局模式：使用setting接口
          await Service.updateWebhookApiSettingWebhookUpdatePost({
            scriptId: null,
            userId: null,
            webhookId: formData.uid,
            data: toWebhookPayload(
              formData.name,
              formData.url,
              formData.template,
              formData.method,
              formData.enabled,
              headersJson
            ),
          })
        } else {
          // 用户模式：使用scripts接口
          await Service.updateWebhookApiScriptsWebhookUpdatePost({
            scriptId: props.scriptId || null,
            userId: props.userId || null,
            webhookId: formData.uid,
            data: toWebhookPayload(
              formData.name,
              formData.url,
              formData.template,
              formData.method,
              formData.enabled,
              headersJson
            ),
          })
        }

        // 重新加载最新数据
        await loadWebhooks()

        if (isEditing.value) {
          message.success(t('comp.webhookUpdated'))
        } else {
          message.success(t('comp.webhookAdded'))
        }

        modalVisible.value = false
        // 延迟重置表单，确保弹窗完全关闭后再重置
        setTimeout(() => {
          resetForm()
        }, 100)
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error)
        logger.error(`保存Webhook失败: ${errorMsg}`)
        message.error(t('comp.couldNotSaveWebhook'))
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
        message.success(t('comp.webhookUpdated'))
      } else {
        // 添加新 Webhook
        newWebhooks = [...webhooks.value, webhookData]
        message.success(t('comp.webhookAdded'))
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
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`表单验证失败: ${errorMsg}`)
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
watch([() => props.scriptId, () => props.userId, () => props.mode], () => {
  loadWebhooks()
})
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

.webhook-manager.compact {
  margin-top: 0;
}

/* 紧凑模式（通知配置弹窗里）：URL 截断不折行，操作收成一行文字链接 */
.webhook-item.compact {
  padding: 10px 12px;
}

.webhook-item.compact .webhook-name {
  margin-bottom: 2px;
}

.webhook-item.compact .webhook-url {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  word-break: normal;
}

.webhook-actions.compact .webhook-switch {
  order: 2;
  margin-right: 0;
  margin-left: 4px;
}

.webhook-actions.compact .ant-btn {
  padding-inline: 6px;
}

.add-hook {
  width: 100%;
  margin-top: 12px;
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
