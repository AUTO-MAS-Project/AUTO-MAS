<script setup lang="ts">
import { ref, reactive, onMounted, computed, watch } from 'vue'
import { message, Modal } from 'ant-design-vue'
import {
  QuestionCircleOutlined,
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  CheckCircleOutlined,
  ApiOutlined,
  RobotOutlined,
} from '@ant-design/icons-vue'
import { LLMService } from '@/api/services/LLMService'
import type { LLMProviderConfig } from '@/api/models/LLMProviderConfig'
import type { LLMGlobalSettings } from '@/api/models/LLMGlobalSettings'
import type { LLMProviderIndexItem } from '@/api/models/LLMProviderIndexItem'
import { getLogger } from '@/utils/logger'
import LLMUsageStats from './LLMUsageStats.vue'
import LLMUsageHistory from './LLMUsageHistory.vue'

const logger = getLogger('LLM设置')

// 预设提供商类型
type ProviderType = 'openai' | 'claude' | 'deepseek' | 'qwen' | 'mimo' | 'custom'

// 预设提供商配置
const presetProviders: Record<string, { name: string; base_url: string; model: string }> = {
  openai: { name: 'OpenAI', base_url: 'https://api.openai.com/v1', model: 'gpt-4o-mini' },
  claude: {
    name: 'Claude',
    base_url: 'https://api.anthropic.com/v1',
    model: 'claude-3-haiku-20240307',
  },
  deepseek: { name: 'DeepSeek', base_url: 'https://api.deepseek.com/v1', model: 'deepseek-chat' },
  qwen: {
    name: 'Qwen',
    base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    model: 'qwen-turbo',
  },
  mimo: { name: '小米 MiMo', base_url: 'https://api.xiaomimimo.com/v1', model: 'mimo-v2-flash' },
}

// 提供商类型选项
const providerTypeOptions = [
  { label: 'OpenAI', value: 'openai' },
  { label: 'Claude', value: 'claude' },
  { label: 'DeepSeek', value: 'deepseek' },
  { label: 'Qwen (通义千问)', value: 'qwen' },
  { label: '小米 MiMo', value: 'mimo' },
  { label: '自定义', value: 'custom' },
]

// 状态
const loading = ref(false)
const globalSettings = reactive<LLMGlobalSettings>({
  Enabled: false,
  ActiveProviderId: '',
  Timeout: 30,
  MaxRetries: 1,
  RateLimit: 10,
})
const providerIndex = ref<LLMProviderIndexItem[]>([])
const providerData = ref<Record<string, LLMProviderConfig>>({})
const serverPresetProviders = ref<Record<string, Record<string, string>>>({})

// 模态框状态
const modalVisible = ref(false)
const modalMode = ref<'add' | 'edit'>('add')
const editingProviderId = ref<string | null>(null)
const modalForm = reactive<{
  name: string
  type: ProviderType
  apiKey: string
  baseUrl: string
  model: string
  maxTokens: number
  temperature: number
}>({
  name: '',
  type: 'openai',
  apiKey: '',
  baseUrl: '',
  model: '',
  maxTokens: 2000,
  temperature: 0.3,
})

// 测试状态
const testingProviderId = ref<string | null>(null)

// 计算属性：是否为自定义类型
const isCustomType = computed(() => modalForm.type === 'custom')

// 计算属性：提供商列表
const providerList = computed(() => {
  return providerIndex.value.map(item => ({
    uid: item.uid,
    ...providerData.value[item.uid],
  }))
})

// 监听类型变化，自动填充预设值
watch(
  () => modalForm.type,
  newType => {
    if (newType !== 'custom' && modalMode.value === 'add') {
      const preset = serverPresetProviders.value[newType] || presetProviders[newType]
      if (preset) {
        modalForm.name = preset.name
        modalForm.baseUrl = preset.base_url
        modalForm.model = preset.model
      }
    }
  }
)

// 加载配置
const loadConfig = async () => {
  loading.value = true
  try {
    const res = await LLMService.getLLMConfigApiLlmConfigGetPost()
    if (res) {
      // 更新全局设置
      Object.assign(globalSettings, res.settings || {})
      // 更新提供商列表
      providerIndex.value = res.index || []
      providerData.value = res.data || {}
      // 保存服务器预设配置
      serverPresetProviders.value = res.preset_providers || {}
    }
  } catch (e) {
    logger.error('加载 LLM 配置失败', e)
    message.error('加载 LLM 配置失败')
  } finally {
    loading.value = false
  }
}

// 更新全局设置
const updateGlobalSettings = async (key: keyof LLMGlobalSettings, value: any) => {
  try {
    const res = await LLMService.updateLLMConfigApiLlmConfigUpdatePost({
      settings: { [key]: value },
    })
    if (res?.code === 200) {
      ;(globalSettings as any)[key] = value
      message.success('设置已保存')
    } else {
      message.error(res?.message || '保存失败')
    }
  } catch (e) {
    logger.error('更新 LLM 设置失败', e)
    message.error('更新设置失败')
  }
}

// 打开添加提供商模态框
const openAddModal = () => {
  modalMode.value = 'add'
  editingProviderId.value = null
  // 重置表单
  modalForm.name = presetProviders.openai.name
  modalForm.type = 'openai'
  modalForm.apiKey = ''
  modalForm.baseUrl = presetProviders.openai.base_url
  modalForm.model = presetProviders.openai.model
  modalForm.maxTokens = 2000
  modalForm.temperature = 0.3
  modalVisible.value = true
}

// 打开编辑提供商模态框
const openEditModal = (providerId: string) => {
  const provider = providerData.value[providerId]
  if (!provider) return

  modalMode.value = 'edit'
  editingProviderId.value = providerId
  modalForm.name = provider.Info?.Name || ''
  modalForm.type = (provider.Info?.Type as ProviderType) || 'custom'
  modalForm.apiKey = provider.Data?.ApiKey || ''
  modalForm.baseUrl = provider.Data?.BaseUrl || ''
  modalForm.model = provider.Data?.Model || ''
  modalForm.maxTokens = provider.Data?.MaxTokens || 2000
  modalForm.temperature = provider.Data?.Temperature || 0.3
  modalVisible.value = true
}

// 保存提供商
const saveProvider = async () => {
  if (!modalForm.apiKey.trim()) {
    message.warning('请输入 API 密钥')
    return
  }

  try {
    if (modalMode.value === 'add') {
      // 添加新提供商 - 使用 provider_type 和 api_key
      const res = await LLMService.addLLMProviderApiLlmProviderAddPost({
        provider_type: modalForm.type,
        api_key: modalForm.apiKey,
      })
      if (res?.code === 200 || res?.providerId) {
        // 如果是自定义类型或需要更新其他字段，再调用更新接口
        if (
          res.providerId &&
          (isCustomType.value || modalForm.name !== presetProviders[modalForm.type]?.name)
        ) {
          const providerConfig: LLMProviderConfig = {
            Info: {
              Name: modalForm.name,
              Type: modalForm.type,
              Active: false,
            },
            Data: {
              ApiKey: modalForm.apiKey,
              BaseUrl: modalForm.baseUrl,
              Model: modalForm.model,
              MaxTokens: modalForm.maxTokens,
              Temperature: modalForm.temperature,
            },
          }
          await LLMService.updateLLMProviderApiLlmProviderUpdatePost({
            providerId: res.providerId,
            data: providerConfig,
          })
        }
        message.success('提供商添加成功')
        modalVisible.value = false
        await loadConfig()
      } else {
        message.error(res?.message || '添加失败')
      }
    } else if (editingProviderId.value) {
      // 更新现有提供商
      const providerConfig: LLMProviderConfig = {
        Info: {
          Name: modalForm.name,
          Type: modalForm.type,
          Active: false,
        },
        Data: {
          ApiKey: modalForm.apiKey,
          BaseUrl: modalForm.baseUrl,
          Model: modalForm.model,
          MaxTokens: modalForm.maxTokens,
          Temperature: modalForm.temperature,
        },
      }
      const res = await LLMService.updateLLMProviderApiLlmProviderUpdatePost({
        providerId: editingProviderId.value,
        data: providerConfig,
      })
      if (res?.code === 200) {
        message.success('提供商更新成功')
        modalVisible.value = false
        await loadConfig()
      } else {
        message.error(res?.message || '更新失败')
      }
    }
  } catch (e) {
    logger.error('保存提供商失败', e)
    message.error('保存失败')
  }
}

// 删除提供商
const deleteProvider = (providerId: string) => {
  const provider = providerData.value[providerId]
  Modal.confirm({
    title: '确认删除',
    content: `确定要删除提供商 "${provider?.Info?.Name || '未命名'}" 吗？`,
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      try {
        const res = await LLMService.deleteLLMProviderApiLlmProviderDeletePost({
          providerId,
        })
        if (res?.code === 200) {
          message.success('提供商已删除')
          await loadConfig()
        } else {
          message.error(res?.message || '删除失败')
        }
      } catch (e) {
        logger.error('删除提供商失败', e)
        message.error('删除失败')
      }
    },
  })
}

// 切换激活提供商
const setActiveProvider = async (providerId: string) => {
  try {
    const res = await LLMService.updateLLMConfigApiLlmConfigUpdatePost({
      settings: { ActiveProviderId: providerId },
    })
    if (res?.code === 200) {
      globalSettings.ActiveProviderId = providerId
      message.success('已切换激活提供商')
      await loadConfig()
    } else {
      message.error(res?.message || '切换失败')
    }
  } catch (e) {
    logger.error('切换提供商失败', e)
    message.error('切换失败')
  }
}

// 测试提供商连接
const testProvider = async (providerId: string) => {
  testingProviderId.value = providerId
  try {
    const res = await LLMService.testLLMProviderApiLlmProviderTestPost({
      providerId,
    })
    if (res?.success) {
      message.success(`连接成功！响应时间: ${res.response_time?.toFixed(2)}s`)
    } else {
      message.error(res?.message || '连接测试失败')
    }
  } catch (e) {
    logger.error('测试提供商连接失败', e)
    message.error('连接测试失败')
  } finally {
    testingProviderId.value = null
  }
}

// 获取提供商类型标签
const getProviderTypeLabel = (type: string | null | undefined) => {
  const option = providerTypeOptions.find(o => o.value === type)
  return option?.label || type || '未知'
}

onMounted(() => {
  loadConfig()
})
</script>

<template>
  <div class="tab-content">
    <!-- LLM 功能开关 -->
    <div class="form-section">
      <div class="section-header">
        <h3>
          <RobotOutlined />
          LLM 智能判定
        </h3>
      </div>
      <p class="section-description">
        启用 LLM
        智能判定后，系统将在传统判定逻辑即将判定任务失败时，调用大语言模型分析日志内容，提供更准确的任务状态判定。
      </p>
      <a-row :gutter="24" style="margin-top: 16px">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">启用 LLM 判定</span>
              <a-tooltip title="开启后将使用 AI 辅助判断任务完成状态">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="globalSettings.Enabled"
              size="large"
              style="width: 100%"
              @change="(value: any) => updateGlobalSettings('Enabled', value)"
            >
              <a-select-option :value="true">启用</a-select-option>
              <a-select-option :value="false">禁用</a-select-option>
            </a-select>
          </div>
        </a-col>
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">API 超时时间</span>
              <a-tooltip title="LLM API 调用的超时时间（秒）">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-input-number
              :value="globalSettings.Timeout"
              :min="5"
              :max="120"
              size="large"
              style="width: 100%"
              addon-after="秒"
              @change="(value: any) => updateGlobalSettings('Timeout', value)"
            />
          </div>
        </a-col>
      </a-row>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">最大重试次数</span>
              <a-tooltip title="API 调用失败时的重试次数">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-input-number
              :value="globalSettings.MaxRetries"
              :min="0"
              :max="3"
              size="large"
              style="width: 100%"
              addon-after="次"
              @change="(value: any) => updateGlobalSettings('MaxRetries', value)"
            />
          </div>
        </a-col>
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">速率限制</span>
              <a-tooltip title="每分钟最大 API 请求数">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-input-number
              :value="globalSettings.RateLimit"
              :min="1"
              :max="60"
              size="large"
              style="width: 100%"
              addon-after="次/分钟"
              @change="(value: any) => updateGlobalSettings('RateLimit', value)"
            />
          </div>
        </a-col>
      </a-row>
    </div>

    <!-- 提供商管理 -->
    <div class="form-section">
      <div class="section-header">
        <h3>
          <ApiOutlined />
          LLM 提供商
        </h3>
        <a-button
          type="primary"
          size="small"
          class="section-update-button primary-style"
          @click="openAddModal"
        >
          <PlusOutlined />
          添加提供商
        </a-button>
      </div>
      <p class="section-description">
        配置 LLM 服务提供商，支持 OpenAI、Claude、DeepSeek、Qwen、小米 MiMo
        等预设提供商，也支持自定义中转站。
      </p>

      <!-- 提供商列表 -->
      <div v-if="providerList.length > 0" class="provider-list">
        <div
          v-for="provider in providerList"
          :key="provider.uid"
          class="provider-card"
          :class="{ active: globalSettings.ActiveProviderId === provider.uid }"
        >
          <div class="provider-header">
            <div class="provider-info">
              <span class="provider-name">{{ provider.Info?.Name || '未命名' }}</span>
              <a-tag
                :color="globalSettings.ActiveProviderId === provider.uid ? 'success' : 'default'"
              >
                {{ getProviderTypeLabel(provider.Info?.Type) }}
              </a-tag>
              <a-tag v-if="globalSettings.ActiveProviderId === provider.uid" color="green">
                <CheckCircleOutlined />
                当前使用
              </a-tag>
            </div>
            <div class="provider-actions">
              <a-button
                v-if="globalSettings.ActiveProviderId !== provider.uid"
                type="link"
                size="small"
                @click="setActiveProvider(provider.uid)"
              >
                设为激活
              </a-button>
              <a-button
                type="link"
                size="small"
                :loading="testingProviderId === provider.uid"
                @click="testProvider(provider.uid)"
              >
                测试连接
              </a-button>
              <a-button type="link" size="small" @click="openEditModal(provider.uid)">
                <EditOutlined />
                编辑
              </a-button>
              <a-button
                type="link"
                size="small"
                danger
                :disabled="globalSettings.ActiveProviderId === provider.uid"
                @click="deleteProvider(provider.uid)"
              >
                <DeleteOutlined />
                删除
              </a-button>
            </div>
          </div>
          <div class="provider-details">
            <span class="detail-item">
              <span class="detail-label">模型:</span>
              <span class="detail-value">{{ provider.Data?.Model || '-' }}</span>
            </span>
            <span class="detail-item">
              <span class="detail-label">最大 Token:</span>
              <span class="detail-value">{{ provider.Data?.MaxTokens || '-' }}</span>
            </span>
            <span class="detail-item">
              <span class="detail-label">Temperature:</span>
              <span class="detail-value">{{ provider.Data?.Temperature || '-' }}</span>
            </span>
          </div>
        </div>
      </div>

      <!-- 空状态 -->
      <a-empty v-else description="暂无提供商配置" class="empty-state">
        <a-button type="primary" @click="openAddModal">
          <PlusOutlined />
          添加第一个提供商
        </a-button>
      </a-empty>
    </div>

    <!-- 添加/编辑提供商模态框 -->
    <a-modal
      v-model:open="modalVisible"
      :title="modalMode === 'add' ? '添加 LLM 提供商' : '编辑 LLM 提供商'"
      :width="600"
      @ok="saveProvider"
    >
      <a-form layout="vertical" class="provider-form">
        <a-form-item label="提供商类型" required>
          <a-select v-model:value="modalForm.type" :options="providerTypeOptions" size="large" />
        </a-form-item>

        <a-form-item label="提供商名称" required>
          <a-input v-model:value="modalForm.name" placeholder="请输入提供商名称" size="large" />
        </a-form-item>

        <a-form-item label="API 密钥" required>
          <a-input-password
            v-model:value="modalForm.apiKey"
            placeholder="请输入 API 密钥"
            size="large"
          />
        </a-form-item>

        <a-form-item label="Base URL" :required="isCustomType">
          <a-input
            v-model:value="modalForm.baseUrl"
            placeholder="请输入 API Base URL"
            size="large"
            :disabled="!isCustomType"
          />
          <template #extra>
            <span v-if="!isCustomType" class="form-extra-text"> 预设提供商使用默认 Base URL </span>
          </template>
        </a-form-item>

        <a-form-item label="模型名称">
          <a-input v-model:value="modalForm.model" placeholder="请输入模型名称" size="large" />
        </a-form-item>

        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="最大 Token 数">
              <a-input-number
                v-model:value="modalForm.maxTokens"
                :min="100"
                :max="32000"
                size="large"
                style="width: 100%"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="Temperature">
              <a-input-number
                v-model:value="modalForm.temperature"
                :min="0"
                :max="2"
                :step="0.1"
                size="large"
                style="width: 100%"
              />
            </a-form-item>
          </a-col>
        </a-row>
      </a-form>
    </a-modal>

    <!-- Token 使用统计 -->
    <div class="form-section">
      <LLMUsageStats />
    </div>

    <!-- Token 使用历史 -->
    <div class="form-section">
      <LLMUsageHistory />
    </div>
  </div>
</template>

<style scoped>
.section-description {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--ant-color-text-secondary);
  line-height: 1.6;
}

/* Provider list styles */
.provider-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 16px;
}

.provider-card {
  background: var(--ant-color-bg-container);
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  padding: 16px;
  transition: all 0.2s ease;
}

.provider-card:hover {
  border-color: var(--ant-color-primary);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.provider-card.active {
  border-color: var(--ant-color-success);
  background: var(--ant-color-success-bg);
}

.provider-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.provider-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.provider-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.provider-actions {
  display: flex;
  gap: 4px;
}

.provider-details {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
}

.detail-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
}

.detail-label {
  color: var(--ant-color-text-secondary);
}

.detail-value {
  color: var(--ant-color-text);
  font-family: monospace;
}

/* Empty state */
.empty-state {
  margin: 32px 0;
  padding: 24px;
  background: var(--ant-color-bg-container);
  border: 1px dashed var(--ant-color-border);
  border-radius: 8px;
}

/* Modal form */
.provider-form {
  padding: 8px 0;
}

.form-extra-text {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

/* Section header styles */
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.section-header h3 {
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-header .section-update-button.primary-style {
  height: 32px;
  padding: 4px 12px;
  font-size: 14px;
  font-weight: 500;
  border-radius: 4px;
  box-shadow: 0 2px 8px rgba(22, 119, 255, 0.18);
  transition:
    transform 0.16s ease,
    box-shadow 0.16s ease;
  background: linear-gradient(
    135deg,
    var(--ant-color-primary),
    var(--ant-color-primary-hover)
  ) !important;
  border: 1px solid var(--ant-color-primary) !important;
  color: #fff !important;
  display: flex;
  align-items: center;
  gap: 4px;
}

.section-header .section-update-button.primary-style:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(22, 119, 255, 0.22);
}

/* Responsive */
@media (max-width: 640px) {
  .section-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .provider-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .provider-actions {
    flex-wrap: wrap;
  }

  .provider-details {
    flex-direction: column;
    gap: 8px;
  }
}
</style>
