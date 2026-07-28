<template>
  <!-- SRC配置遮罩层 -->
  <div v-if="showSRCConfigMask" class="maa-config-mask">
    <div class="mask-content">
      <div class="mask-icon">
        <SettingOutlined :style="{ fontSize: '48px', color: '#722ed1' }" />
      </div>
      <h2 class="mask-title">正在进行SRC配置</h2>
      <p class="mask-description">
        当前正在配置SRC脚本，请在SRC配置界面完成相关设置。
        <br />
        配置完成后，请点击"保存配置"按钮来解除页面锁定。
      </p>
      <div class="mask-actions">
        <a-button
          v-if="currentConfigScript"
          type="primary"
          size="large"
          @click="handleSaveSRCConfig(currentConfigScript)"
        >
          保存配置
        </a-button>
      </div>
    </div>
  </div>

  <div v-if="showMaaEndConfigMask" class="maa-config-mask">
    <div class="mask-content">
      <div class="mask-icon">
        <SettingOutlined :style="{ fontSize: '48px', color: 'var(--ant-color-primary)' }" />
      </div>
      <h2 class="mask-title">正在进行 MaaEnd 配置</h2>
      <p class="mask-description">
        当前正在配置 MaaEnd 脚本，请在 MaaEnd 配置界面完成相关设置。
        <br />
        配置完成后，点击“保存配置”解除页面锁定。
      </p>
      <div class="mask-actions">
        <a-button
          v-if="currentConfigScript"
          type="primary"
          size="large"
          @click="handleSaveMaaEndConfig(currentConfigScript)"
        >
          保存配置
        </a-button>
      </div>
    </div>
  </div>

  <!-- 主要内容 -->
  <div class="scripts-header">
    <div class="header-left">
      <h1 class="page-title">脚本管理</h1>
    </div>
    <div class="header-actions">
      <a-space size="middle">
        <a-tooltip title="收起所有脚本的用户列表">
          <a-button size="large" :disabled="scripts.length === 0" @click="handleCollapseAll">
            <template #icon>
              <UpOutlined />
            </template>
            一键收起
          </a-button>
        </a-tooltip>
        <a-tooltip title="展开所有脚本的用户列表">
          <a-button size="large" :disabled="scripts.length === 0" @click="handleExpandAll">
            <template #icon>
              <DownOutlined />
            </template>
            一键展开
          </a-button>
        </a-tooltip>
        <a-button
          type="primary"
          size="large"
          class="link"
          :disabled="availableScriptTypes.length === 0"
          @click="handleAddScript"
        >
          <template #icon>
            <PlusOutlined />
          </template>
          新建脚本
        </a-button>
      </a-space>
    </div>
  </div>

  <!-- 空状态 -->
  <!-- 增加 loadedOnce 条件，避免初始渲染时闪烁 -->
  <a-alert
    v-if="scriptListError"
    class="script-list-error"
    type="error"
    show-icon
    message="脚本列表加载失败"
    :description="scriptListError"
  >
    <template #action>
      <a-button size="small" type="primary" @click="loadScripts">
        <template #icon>
          <ReloadOutlined />
        </template>
        重试
      </a-button>
    </template>
  </a-alert>

  <div
    v-if="!scriptListError && !addLoading && loadedOnce && scripts.length === 0"
    class="empty-state"
  >
    <div class="empty-content">
      <div class="empty-image-container">
        <img src="@/assets/NoData.png" alt="暂无数据" class="empty-image" />
      </div>
      <div class="empty-text-content">
        <h3 class="empty-title">暂无脚本</h3>
        <p class="empty-description">您还没有创建任何脚本</p>
      </div>
    </div>
  </div>

  <ScriptTable
    v-if="scripts.length > 0 || !scriptListError"
    ref="scriptTableRef"
    :scripts="scripts"
    :active-connections="activeConnections"
    :copying-script-id="copyingScriptId"
    :all-plans-data="allPlansData"
    @edit="handleEditScript"
    @copy="handleCopyScript"
    @delete="handleDeleteScript"
    @add-user="handleAddUser"
    @edit-user="handleEditUser"
    @delete-user="handleDeleteUser"
    @start-src-config="handleStartSRCConfig"
    @save-src-config="handleSaveSRCConfig"
    @start-maa-end-config="handleStartMaaEndConfig"
    @save-maa-end-config="handleSaveMaaEndConfig"
    @toggle-user-status="handleToggleUserStatus"
    @pass-check-user="handlePassCheckUser"
  />

  <ScriptCreateDialog
    v-model:open="scriptCreateVisible"
    :templates="templates"
    :submitting="addLoading || templateLoading"
    :template-loading="templateLoading"
    :template-error="templateError"
    :type-options="scriptCreateTypeOptions"
    @request-templates="loadTemplates"
    @submit="handleSubmitScriptCreate"
  />

  <!-- 创建方式选择弹窗 -->
  <a-modal
    v-model:open="createModeSelectVisible"
    title="选择创建方式"
    :confirm-loading="addLoading"
    class="create-mode-modal"
    width="600px"
    ok-text="确定"
    cancel-text="取消"
    :ok-button-props="{ disabled: selectedTypeUnavailable }"
    @ok="handleConfirmCreateMode"
    @cancel="createModeSelectVisible = false"
  >
    <div class="mode-selection">
      <a-radio-group v-model:value="selectedCreateMode" class="mode-radio-group">
        <a-radio-button value="copy" class="mode-option">
          <div class="mode-content">
            <div class="mode-icon">
              <FileTextOutlined />
            </div>
            <div class="mode-info">
              <div class="mode-title">复制已有脚本</div>
              <div class="mode-description">从现有脚本复制配置，快速创建相似脚本</div>
            </div>
          </div>
        </a-radio-button>
        <a-radio-button value="new" class="mode-option">
          <div class="mode-content">
            <div class="mode-icon">
              <PlusOutlined />
            </div>
            <div class="mode-info">
              <div class="mode-title">创建全新脚本</div>
              <div class="mode-description">从头开始创建一个全新的脚本实例</div>
            </div>
          </div>
        </a-radio-button>
      </a-radio-group>
    </div>
  </a-modal>

  <!-- 脚本选择弹窗 -->
  <a-modal
    v-model:open="scriptSelectVisible"
    title="选择要复制的脚本"
    :confirm-loading="addLoading"
    class="script-select-modal"
    width="800px"
    ok-text="确定复制"
    cancel-text="返回"
    :ok-button-props="{ disabled: !selectedScriptId }"
    @ok="handleConfirmScriptSelect"
    @cancel="
      () => {
        scriptSelectVisible = false
        createModeSelectVisible = true
      }
    "
  >
    <div class="script-selection">
      <div v-if="scripts.length === 0" class="no-scripts">
        <p>暂无可用脚本</p>
      </div>
      <div v-else class="scripts-list">
        <div
          v-for="script in scripts"
          :key="script.id"
          :class="[
            'script-item',
            { selected: selectedScriptId === script.id, unavailable: script.available === false },
          ]"
          @click="script.available === false ? undefined : (selectedScriptId = script.id)"
        >
          <div class="script-item-content">
            <div class="script-icon">
              <img
                :src="getScriptIcon(script.type, script.iconUrl)"
                :alt="script.type"
                class="type-icon"
                @error="event => handleScriptIconError(event, script.type)"
              />
            </div>
            <div class="script-info">
              <div class="script-name">{{ script.name }}</div>
              <div class="script-meta">
                <span class="script-type">{{ getScriptDisplayLabel(script) }}</span>
                <span v-if="script.available === false" class="script-type script-unavailable">
                  未启用
                </span>
                <span class="script-users">
                  <UserOutlined />
                  {{ script.users?.length || 0 }} 个用户
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </a-modal>

  <!-- 脚本类型选择弹窗 -->
  <a-modal
    v-model:open="typeSelectVisible"
    title="选择脚本类型"
    :confirm-loading="addLoading"
    class="type-select-modal"
    width="500px"
    ok-text="确定"
    cancel-text="取消"
    @ok="handleConfirmAddScript"
    @cancel="typeSelectVisible = false"
  >
    <div class="type-selection">
      <a-radio-group v-model:value="selectedType" class="type-radio-group">
        <a-radio-button
          v-for="descriptor in availableScriptTypes"
          :key="descriptor.type_key"
          :value="descriptor.type_key"
          class="type-option"
          :disabled="descriptor.available === false"
        >
          <div class="type-content">
            <div class="type-logo-container">
              <img
                :src="getScriptIcon(descriptor.type_key, descriptor.icon_url)"
                :alt="descriptor.type_key"
                class="type-logo"
                @error="event => handleScriptIconError(event, descriptor.type_key)"
              />
            </div>
            <div class="type-info">
              <div class="type-title">
                <span>{{ descriptor.display_name }}</span>
                <a-tag
                  :color="getScriptTypeTagColor(descriptor.type_key, descriptor.theme_color)"
                  class="type-tag"
                >
                  {{ descriptor.type_key }}
                </a-tag>
              </div>
              <div class="type-description">
                {{
                  descriptor.available === false
                    ? descriptor.unavailable_reason || '当前插件未生效'
                    : `支持模式：${descriptor.supported_modes.join(' / ') || '未声明'}`
                }}
              </div>
            </div>
          </div>
        </a-radio-button>
      </a-radio-group>
    </div>
  </a-modal>

  <!-- 通用脚本创建方式选择弹窗 -->
  <a-modal
    v-model:open="generalModeSelectVisible"
    title="选择创建方式"
    :confirm-loading="addLoading"
    class="general-mode-modal"
    width="600px"
    ok-text="确定"
    cancel-text="返回"
    @ok="handleConfirmGeneralMode"
    @cancel="generalModeSelectVisible = false"
  >
    <div class="mode-selection">
      <a-radio-group v-model:value="selectedGeneralMode" class="mode-radio-group">
        <a-radio-button value="template" class="mode-option">
          <div class="mode-content">
            <div class="mode-icon">
              <FileTextOutlined />
            </div>
            <div class="mode-info">
              <div class="mode-title">从模板创建</div>
              <div class="mode-description">选择现有的配置模板快速创建脚本</div>
            </div>
          </div>
        </a-radio-button>
        <a-radio-button value="custom" class="mode-option">
          <div class="mode-content">
            <div class="mode-icon">
              <SettingOutlined />
            </div>
            <div class="mode-info">
              <div class="mode-title">自定义配置</div>
              <div class="mode-description">从空白配置开始，完全自定义脚本设置</div>
            </div>
          </div>
        </a-radio-button>
      </a-radio-group>
    </div>
  </a-modal>

  <!-- 模板选择弹窗 -->
  <a-modal
    v-model:open="templateSelectVisible"
    title="选择配置模板"
    :confirm-loading="templateLoading"
    class="template-select-modal"
    width="1000px"
    ok-text="使用此模板"
    cancel-text="返回"
    :ok-button-props="{ disabled: !selectedTemplate }"
    @ok="handleConfirmTemplate"
    @cancel="handleCancelTemplate"
  >
    <div class="template-selection">
      <a-spin :spinning="templateLoading">
        <div v-if="templates.length === 0 && !templateLoading" class="no-templates">
          <div class="no-templates-content">
            <FileSearchOutlined class="no-templates-icon" />
            <h3>暂无可用模板</h3>
            <p>当前没有找到任何配置模板，请稍后再试或联系管理员</p>
          </div>
        </div>
        <div v-else class="templates-container">
          <div class="templates-header">
            <div class="templates-count">
              <span class="count-badge">{{ filteredTemplates.length }}</span>
              <span class="count-text">个可用模板</span>
            </div>
            <div class="search-container">
              <a-input
                v-model:value="searchKeyword"
                placeholder="搜索模板名称、作者或描述..."
                allow-clear
                class="template-search"
              >
                <template #prefix>
                  <FileSearchOutlined />
                </template>
              </a-input>
            </div>
          </div>
          <div class="templates-list">
            <div v-if="filteredTemplates.length === 0" class="no-search-results">
              <FileSearchOutlined class="no-results-icon" />
              <p>未找到匹配的模板</p>
              <p class="no-results-tip">请尝试其他关键词</p>
            </div>
            <div
              v-for="template in filteredTemplates"
              :key="template.configName"
              :class="[
                'template-item',
                { selected: selectedTemplate?.configName === template.configName },
              ]"
              @click="selectedTemplate = template"
            >
              <div class="template-content">
                <div class="template-header">
                  <div class="template-info">
                    <h3 class="template-name">{{ template.configName }}</h3>
                    <div class="template-meta">
                      <span class="template-author">
                        <UserOutlined />
                        {{ template.author || '未知作者' }}
                      </span>
                      <span class="template-time">
                        <ClockCircleOutlined />
                        {{ template.createTime || '未知时间' }}
                      </span>
                    </div>
                  </div>
                  <!--                  <div class="template-selector">-->
                  <!--                    <a-radio :checked="selectedTemplate?.configName === template.configName" />-->
                  <!--                  </div>-->
                </div>

                <!-- eslint-disable vue/no-v-html -- MarkdownIt has raw HTML disabled, so template descriptions are escaped. -->
                <div
                  class="template-description"
                  v-html="parseMarkdown(template.description)"
                ></div>
                <!-- eslint-enable vue/no-v-html -->
              </div>
            </div>
          </div>
        </div>
      </a-spin>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  ClockCircleOutlined,
  DownOutlined,
  FileSearchOutlined,
  FileTextOutlined,
  PlusOutlined,
  ReloadOutlined,
  SettingOutlined,
  UpOutlined,
  UserOutlined,
} from '@ant-design/icons-vue'
import ScriptTable from '@/components/ScriptTable.vue'
import ScriptCreateDialog from '@/views/scripts/components/ScriptCreateDialog.vue'
import type { MaaFWScriptConfig, Script, ScriptType, User } from '@/types/script'
import type { ScriptTypeDescriptor } from '@/types/scriptRegistry'
import {
  createScriptTypeOptions,
  type ScriptCreateRequest,
} from '@/views/scripts/components/scriptCreateFlow'
import { useScriptRegistryApi } from '@/composables/useScriptRegistryApi'
import { useWebSocket } from '@/composables/useWebSocket'
import {
  WS_ID_PLUGIN_SYSTEM,
  WS_PLUGIN_SNAPSHOT_UPDATED,
  WS_TASK_COMPLETED,
  WS_TASK_NOTICE,
} from '@/services/websocket/types'
import { useTemplateApi, type WebConfigTemplate } from '@/composables/useTemplateApi'
import { usePlanApi } from '@/composables/usePlanApi'
import { Service } from '@/api/services/Service'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import {
  descriptorMapFromList,
  getScriptEditPath,
  getScriptIcon,
  getScriptTypeTagColor,
  getUserCreatePath,
  getUserEditPath,
  handleScriptIconError,
  normalizeScriptRecord,
} from '@/utils/scriptRegistry'
import MarkdownIt from 'markdown-it'
const logger = window.electronAPI.getLogger('脚本管理')

const router = useRouter()
const registryApi = useScriptRegistryApi()
const { subscribe, unsubscribe } = useWebSocket()
const { getWebConfigTemplates, importScriptFromWeb, error: templateError } = useTemplateApi()
const { getPlans } = usePlanApi()

// 初始化markdown解析器
const md = new MarkdownIt({
  html: false,
  linkify: true,
  typographer: true,
})

const scripts = ref<Script[]>([])
const scriptTableRef = ref<InstanceType<typeof ScriptTable> | null>(null)
const scriptTypeDescriptors = ref<ScriptTypeDescriptor[]>([])
const scriptListError = ref<string | null>(null)
// 增加：标记是否已经完成过一次脚本列表加载（成功或失败都算一次）
const loadedOnce = ref(false)
// 所有计划表数据 (planId -> planData)
const allPlansData = ref<Record<string, Record<string, any>>>({})
const scriptCreateVisible = ref(false)
const copyingScriptId = ref<string | null>(null)
const createModeSelectVisible = ref(false) // 创建方式选择弹窗（复制已有 vs 创建新脚本）
const scriptSelectVisible = ref(false) // 脚本列表选择弹窗
const typeSelectVisible = ref(false)
const generalModeSelectVisible = ref(false)
const templateSelectVisible = ref(false)
const selectedCreateMode = ref('new') // 'copy' or 'new'
const selectedScriptId = ref<string | null>(null) // 选中要复制的脚本ID
const selectedType = ref<ScriptType>('')
const selectedGeneralMode = ref('template')
const selectedTemplate = ref<WebConfigTemplate | null>(null)
const templates = ref<WebConfigTemplate[]>([])
const addLoading = ref(false)
const templateLoading = ref(false)
const searchKeyword = ref('')
const showSRCConfigMask = ref(false) // 控制SRC配置遮罩层的显示
const showMaaEndConfigMask = ref(false) // 控制MaaEnd配置遮罩层的显示
const currentConfigScript = ref<Script | null>(null) // 当前正在配置的脚本

interface ActiveConfigConnection {
  subscriptionIds: string[]
  taskId: string
  timeoutId?: number
}

// WebSocket连接管理
const activeConnections = ref<Map<string, ActiveConfigConnection>>(new Map())
let pluginSystemSubscriptionId: string | null = null

const releaseActiveConnection = (scriptId: string): boolean => {
  const connection = activeConnections.value.get(scriptId)
  if (!connection) return false

  for (const subscriptionId of connection.subscriptionIds) {
    unsubscribe(subscriptionId)
  }
  if (connection.timeoutId !== undefined) {
    window.clearTimeout(connection.timeoutId)
  }
  activeConnections.value.delete(scriptId)
  return true
}

const getMaaFWProjectLabel = (script: Script) => {
  const config = script.config as Partial<MaaFWScriptConfig> | undefined
  return config?.Info?.ProjectLabel?.trim() || 'MaaFW'
}

const getScriptDisplayLabel = (script: Script) => {
  if (script.type === 'MaaFW') return getMaaFWProjectLabel(script)
  return script.displayName || script.type
}

// 解析模板描述的markdown
const parseMarkdown = (text: string) => {
  if (!text) return '暂无描述信息'
  return md.render(text)
}

// 过滤模板
const filteredTemplates = computed(() => {
  if (!searchKeyword.value.trim()) {
    return templates.value
  }

  const keyword = searchKeyword.value.toLowerCase()
  return templates.value.filter(
    template =>
      template.configName.toLowerCase().includes(keyword) ||
      (template.author && template.author.toLowerCase().includes(keyword)) ||
      (template.description && template.description.toLowerCase().includes(keyword))
  )
})

const availableScriptTypes = computed(() => scriptTypeDescriptors.value)
const creatableScriptTypes = computed(() =>
  scriptTypeDescriptors.value.filter(descriptor => descriptor.available !== false)
)
const selectedTypeDescriptor = computed(() =>
  scriptTypeDescriptors.value.find(descriptor => descriptor.type_key === selectedType.value)
)
const selectedTypeUnavailable = computed(() => selectedTypeDescriptor.value?.available === false)
const scriptCreateTypeOptions = computed(() => createScriptTypeOptions(availableScriptTypes.value))

const isScriptAvailable = (script: Script) => script.available !== false

const canEditScript = (script: Script) => script.providerAvailable ?? isScriptAvailable(script)

const ensureScriptAvailable = (script: Script) => {
  if (isScriptAvailable(script)) {
    return true
  }
  message.warning(script.unavailableReason || `脚本类型 ${script.type} 当前未启用，暂时不能操作`)
  return false
}

onMounted(() => {
  pluginSystemSubscriptionId = subscribe(
    { id: WS_ID_PLUGIN_SYSTEM, type: WS_PLUGIN_SNAPSHOT_UPDATED },
    () => void loadScripts()
  )
  loadScripts()
  loadCurrentPlan()
})

onUnmounted(() => {
  if (pluginSystemSubscriptionId) unsubscribe(pluginSystemSubscriptionId)
  for (const scriptId of [...activeConnections.value.keys()]) {
    releaseActiveConnection(scriptId)
  }
})

const loadScripts = async () => {
  try {
    scriptListError.value = null
    const descriptors = await registryApi.getScriptTypes()
    scriptTypeDescriptors.value = descriptors
    if (!selectedType.value && descriptors.length > 0) {
      selectedType.value = descriptors.find(item => item.available !== false)?.type_key || ''
    }
    const descriptorMap = descriptorMapFromList(descriptors)
    const scriptRecords = await registryApi.getScripts()
    const userRecords = await Promise.all(
      scriptRecords.map(record => registryApi.getUsers(record.id))
    )

    scripts.value = scriptRecords.map((record, index) =>
      normalizeScriptRecord(record, descriptorMap, userRecords[index] || [])
    )
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    scriptListError.value = errorMsg
    logger.error(`加载脚本列表失败: ${errorMsg}`)
    message.error(`加载脚本列表失败: ${errorMsg}`)
  } finally {
    // 首次加载结束（不论成功失败）后置位，避免初始闪烁
    loadedOnce.value = true
  }
}

// 加载所有计划表数据
const loadCurrentPlan = async () => {
  try {
    const response = await getPlans()
    if (response.data) {
      // 加载所有计划表数据
      allPlansData.value = response.data
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载计划表数据失败: ${errorMsg}`)
    // 不显示错误消息，因为计划表数据是可选的
  }
}

const handleCollapseAll = () => {
  scriptTableRef.value?.collapseAllUsers()
}

const handleExpandAll = () => {
  scriptTableRef.value?.expandAllUsers()
}

const handleAddScript = () => {
  scriptCreateVisible.value = true
}

const navigateToCreatedScript = (result: { id: string; type: string; editor_kind: string }) => {
  if (result.type === 'MaaFW' || result.type === 'M9A') {
    router.push(`/scripts/${result.id}/setup/maafw`)
    return
  }
  router.push(
    getScriptEditPath({ id: result.id, type: result.type, editorKind: result.editor_kind })
  )
}

const handleSubmitScriptCreate = async (request: ScriptCreateRequest) => {
  addLoading.value = true
  try {
    const result = await registryApi.addScript(request.kind === 'new' ? request.type : 'General')

    if (request.kind === 'general-template') {
      const imported = await importScriptFromWeb(result.id, request.template.downloadUrl)
      if (!imported) return
      message.success(`已根据模板「${request.template.configName}」创建脚本`)
    }

    scriptCreateVisible.value = false
    navigateToCreatedScript(result)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`添加脚本失败: ${errorMsg}`)
    message.error(`添加脚本失败: ${errorMsg}`)
  } finally {
    addLoading.value = false
  }
}

const handleCopyScript = async (script: Script) => {
  if (!ensureScriptAvailable(script)) return

  addLoading.value = true
  copyingScriptId.value = script.id
  try {
    await registryApi.addScript(script.type, script.id)
    await loadScripts()
    message.success(`已复制脚本「${script.name}」`)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`复制脚本失败: ${errorMsg}`)
    message.error(`复制脚本失败: ${errorMsg}`)
  } finally {
    addLoading.value = false
    copyingScriptId.value = null
  }
}

const handleConfirmCreateMode = () => {
  if (selectedCreateMode.value === 'copy') {
    // 复制已有脚本 - 打开脚本选择弹窗
    createModeSelectVisible.value = false
    selectedScriptId.value = null
    scriptSelectVisible.value = true
  } else {
    // 创建新脚本 - 进入类型选择
    createModeSelectVisible.value = false
    selectedType.value = creatableScriptTypes.value[0]?.type_key || 'MAA'
    typeSelectVisible.value = true
  }
}

const handleConfirmScriptSelect = async () => {
  if (!selectedScriptId.value) {
    message.warning('请先选择一个脚本')
    return
  }

  // 获取选中的脚本信息
  const selectedScript = scripts.value.find(s => s.id === selectedScriptId.value)
  if (!selectedScript) {
    message.error('所选脚本不存在')
    return
  }

  if (!ensureScriptAvailable(selectedScript)) {
    return
  }

  addLoading.value = true
  try {
    const result = await registryApi.addScript(selectedScript.type, selectedScriptId.value)
    scriptSelectVisible.value = false
    router.push(
      getScriptEditPath({ id: result.id, type: result.type, editorKind: result.editor_kind })
    )
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`复制脚本失败: ${errorMsg}`)
  } finally {
    addLoading.value = false
  }
}

const handleConfirmAddScript = async () => {
  if (selectedTypeUnavailable.value) {
    message.warning(selectedTypeDescriptor.value?.unavailable_reason || '当前脚本类型不可用')
    return
  }
  if (selectedType.value === 'General') {
    // 如果选择通用脚本，进入创建方式选择
    typeSelectVisible.value = false
    generalModeSelectVisible.value = true
    return
  }

  // MAA和SRC脚本直接创建
  addLoading.value = true
  try {
    const result = await registryApi.addScript(selectedType.value)
    typeSelectVisible.value = false
    // MaaFW / M9A 新建脚本进入引导流程，其余类型直接进入编辑页
    if (result.type === 'MaaFW' || result.type === 'M9A') {
      router.push(`/scripts/${result.id}/setup/maafw`)
    } else {
      router.push(
        getScriptEditPath({ id: result.id, type: result.type, editorKind: result.editor_kind })
      )
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`添加脚本失败: ${errorMsg}`)
  } finally {
    addLoading.value = false
  }
}

const handleConfirmGeneralMode = async () => {
  if (selectedGeneralMode.value === 'template') {
    // 加载模板列表并打开模板选择弹窗
    await loadTemplates()
    generalModeSelectVisible.value = false
    templateSelectVisible.value = true
  } else {
    // 自定义配置 - 直接创建通用脚本
    generalModeSelectVisible.value = false
    addLoading.value = true
    try {
      const result = await registryApi.addScript('General')
      router.push(
        getScriptEditPath({ id: result.id, type: result.type, editorKind: result.editor_kind })
      )
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`添加脚本失败: ${errorMsg}`)
    } finally {
      addLoading.value = false
    }
  }
}

const loadTemplates = async () => {
  templateLoading.value = true
  try {
    templates.value = await getWebConfigTemplates()
    selectedTemplate.value = null
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载模板列表失败: ${errorMsg}`)
  } finally {
    templateLoading.value = false
  }
}

const handleConfirmTemplate = async () => {
  if (!selectedTemplate.value) {
    message.warning('请先选择一个模板')
    return
  }

  templateLoading.value = true
  try {
    // 1. 先创建通用脚本
    const createResult = await registryApi.addScript('General')

    // 2. 使用模板URL导入配置
    const importResult = await importScriptFromWeb(
      createResult.id,
      selectedTemplate.value.downloadUrl
    )

    if (importResult) {
      message.success(`已根据模板 "${selectedTemplate.value.configName}" 创建脚本`)
      templateSelectVisible.value = false
      selectedTemplate.value = null

      // 刷新脚本列表
      await loadScripts()

      // 跳转到编辑页面，不传递state数据，让编辑页面从API重新加载最新配置
      router.push(
        getScriptEditPath({
          id: createResult.id,
          type: createResult.type,
          editorKind: createResult.editor_kind,
        })
      )
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`使用模板创建脚本失败: ${errorMsg}`)
    message.error(`使用模板创建脚本失败: ${errorMsg}`)
  } finally {
    templateLoading.value = false
  }
}

const handleCancelTemplate = () => {
  templateSelectVisible.value = false
  selectedTemplate.value = null
  // 返回到创建方式选择
  generalModeSelectVisible.value = true
}

const handleEditScript = (script: Script) => {
  if (!canEditScript(script)) {
    ensureScriptAvailable(script)
    return
  }
  router.push(getScriptEditPath(script))
}

const handleDeleteScript = async (script: Script) => {
  try {
    await registryApi.deleteScript(script.id)
    await loadScripts()
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`删除脚本失败: ${errorMsg}`)
  }
}

const handleAddUser = (script: Script) => {
  if (!ensureScriptAvailable(script)) {
    return
  }
  router.push(getUserCreatePath(script))
}

const handleEditUser = (user: User) => {
  // 从用户数据中找到对应的脚本
  const script = scripts.value.find(s => s.users.some(u => u.id === user.id))
  if (script) {
    if (!ensureScriptAvailable(script)) {
      return
    }
    router.push(getUserEditPath(script, user))
  } else {
    message.error('找不到对应的脚本')
  }
}

const handleDeleteUser = async (user: User) => {
  // 从用户数据中找到对应的脚本
  const script = scripts.value.find(s => s.users.some(u => u.id === user.id))
  if (!script) {
    message.error('找不到对应的脚本')
    return
  }
  if (!ensureScriptAvailable(script)) {
    return
  }

  try {
    await registryApi.deleteUser(script.id, user.id)
    const userIndex = script.users.findIndex(u => u.id === user.id)
    if (userIndex > -1) {
      script.users.splice(userIndex, 1)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`删除用户失败: ${errorMsg}`)
  }
}

const handleStartSRCConfig = async (script: Script) => {
  if (!ensureScriptAvailable(script)) {
    return
  }
  try {
    // 检查是否已有连接
    const existingConnection = activeConnections.value.get(script.id)
    if (existingConnection) {
      message.warning('该脚本已在配置中，请先保存配置')
      return
    }

    // 调用启动配置任务API
    const response = await Service.addTaskApiDispatchStartPost({
      taskId: script.id,
      mode: TaskCreateIn.mode.SCRIPT_CONFIG,
    })

    if (response.code === 200) {
      // 显示遮罩层
      showSRCConfigMask.value = true
      currentConfigScript.value = script

      // 订阅WebSocket消息
      const subscriptionIds = [
        // 处理任务提示中的错误消息（不取消订阅，等待任务结束消息）
        subscribe({ id: response.taskId, type: WS_TASK_NOTICE }, wsMessage => {
          const data = wsMessage.data
          if (data.level === 'error') {
            const errorMsg = data.message
            logger.error(`脚本 ${script.name} 配置异常: ${errorMsg}`)
            message.error(`SRC配置失败: ${errorMsg}`)
          }
        }),
        // 处理任务结束消息
        subscribe({ id: response.taskId, type: WS_TASK_COMPLETED }, wsMessage => {
          const data = wsMessage.data
          logger.info(`脚本 ${script.name} 配置任务已结束`)
          // 根据结果显示不同消息
          const result = data.result
          if (result && !result.includes('异常') && !result.includes('错误')) {
            message.success(`${script.name} 配置已完成`)
          }
          // 清理连接
          releaseActiveConnection(script.id)
          showSRCConfigMask.value = false
          currentConfigScript.value = null
        }),
      ]

      // 记录连接和subscriptionIds
      const connection: ActiveConfigConnection = {
        subscriptionIds,
        taskId: response.taskId,
      }
      activeConnections.value.set(script.id, connection)
      message.success(`已启动 ${script.name} 的SRC配置`)

      // 设置自动断开连接的定时器（30分钟后）
      connection.timeoutId = window.setTimeout(
        () => {
          if (!releaseActiveConnection(script.id)) return
          // 超时时隐藏遮罩
          showSRCConfigMask.value = false
          currentConfigScript.value = null
          message.info(`${script.name} 配置会话已超时断开`)
        },
        30 * 60 * 1000
      )
    } else {
      message.error(response.message || '启动SRC配置失败')
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`启动SRC配置失败: ${errorMsg}`)
    message.error(`启动SRC配置失败: ${errorMsg}`)
  }
}

const handleSaveSRCConfig = async (script: Script) => {
  try {
    const connection = activeConnections.value.get(script.id)
    if (!connection) {
      message.error('未找到活动的配置会话')
      return
    }

    // 调用停止配置任务API
    const response = await Service.stopTaskApiDispatchStopPost({
      taskId: connection.taskId,
    })

    if (response.code === 200) {
      releaseActiveConnection(script.id)

      // 隐藏遮罩
      showSRCConfigMask.value = false
      currentConfigScript.value = null

      message.success(`${script.name} 的配置已保存`)
    } else {
      message.error(response.message || '保存配置失败')
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存SRC配置失败: ${errorMsg}`)
    message.error(`保存SRC配置失败: ${errorMsg}`)
  }
}

const handleStartMaaEndConfig = async (script: Script) => {
  if (!ensureScriptAvailable(script)) {
    return
  }
  try {
    const existingConnection = activeConnections.value.get(script.id)
    if (existingConnection) {
      message.warning('该脚本已在配置中，请先保存当前配置')
      return
    }

    const response = await Service.addTaskApiDispatchStartPost({
      taskId: script.id,
      mode: TaskCreateIn.mode.SCRIPT_CONFIG,
    })

    if (response.code === 200) {
      showMaaEndConfigMask.value = true
      currentConfigScript.value = script

      const subscriptionIds = [
        subscribe({ id: response.taskId, type: WS_TASK_NOTICE }, wsMessage => {
          const data = wsMessage.data
          if (data.level === 'error') {
            const errorMsg = data.message
            logger.error(`脚本 ${script.name} 配置异常: ${errorMsg}`)
            message.error(`MaaEnd 配置失败: ${errorMsg}`)
          }
        }),
        subscribe({ id: response.taskId, type: WS_TASK_COMPLETED }, () => {
          releaseActiveConnection(script.id)
          showMaaEndConfigMask.value = false
          currentConfigScript.value = null
        }),
      ]

      const connection: ActiveConfigConnection = {
        subscriptionIds,
        taskId: response.taskId,
      }
      activeConnections.value.set(script.id, connection)
      message.success(`已启动 ${script.name} 的 MaaEnd 配置`)

      connection.timeoutId = window.setTimeout(
        () => {
          if (!releaseActiveConnection(script.id)) return
          showMaaEndConfigMask.value = false
          currentConfigScript.value = null
          message.info(`${script.name} 配置会话已超时断开`)
        },
        30 * 60 * 1000
      )
    } else {
      message.error(response.message || '启动 MaaEnd 配置失败')
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`启动 MaaEnd 配置失败: ${errorMsg}`)
    message.error(`启动 MaaEnd 配置失败: ${errorMsg}`)
  }
}

const handleSaveMaaEndConfig = async (script: Script) => {
  try {
    const connection = activeConnections.value.get(script.id)
    if (!connection) {
      message.error('未找到活动的配置会话')
      return
    }

    const response = await Service.stopTaskApiDispatchStopPost({
      taskId: connection.taskId,
    })

    if (response.code === 200) {
      releaseActiveConnection(script.id)
      showMaaEndConfigMask.value = false
      currentConfigScript.value = null
      message.success(`${script.name} 的配置已保存`)
    } else {
      message.error(response.message || '保存配置失败')
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存 MaaEnd 配置失败: ${errorMsg}`)
    message.error(`保存 MaaEnd 配置失败: ${errorMsg}`)
  }
}

const handleToggleUserStatus = async (user: User) => {
  try {
    // 找到该用户对应的脚本
    const script = scripts.value.find(s => s.users.some(u => u.id === user.id))
    if (!script) {
      message.error('找不到对应的脚本')
      return
    }
    if (!ensureScriptAvailable(script)) {
      return
    }
    const newStatus = !user.Info.Status

    // 调用 updateUser API
    await registryApi.updateUser(script.id, user.id, {
      Info: {
        Status: newStatus,
      },
    })
    message.success('用户状态更新成功')
    user.Info.Status = newStatus
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`更新用户状态失败: ${errorMsg}`)
    message.error(`更新用户状态失败: ${errorMsg}`)
  }
}

const handlePassCheckUser = async (user: User) => {
  try {
    // 找到该用户对应的脚本
    const script = scripts.value.find(s => s.users.some(u => u.id === user.id))
    if (!script) {
      message.error('找不到对应的脚本')
      return
    }
    if (!ensureScriptAvailable(script)) {
      return
    }

    // 调用 updateUser API，更新 Data.IfPassCheck 为 true
    await registryApi.updateUser(script.id, user.id, {
      Data: {
        IfPassCheck: true,
      },
    })
    message.success('已标记为「通过人工排查」')
    await loadScripts()
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`更新人工排查状态失败: ${errorMsg}`)
    message.error(`更新人工排查状态失败: ${errorMsg}`)
  }
}
</script>

<style scoped>
.maa-config-mask {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}

.mask-content {
  background: var(--ant-color-bg-elevated);
  border-radius: 8px;
  padding: 24px;
  max-width: 480px;
  width: 100%;
  text-align: center;
  box-shadow:
    0 6px 16px 0 rgba(0, 0, 0, 0.08),
    0 3px 6px -4px rgba(0, 0, 0, 0.12),
    0 9px 28px 8px rgba(0, 0, 0, 0.05);
  border: 1px solid var(--ant-color-border);
}

.mask-icon {
  margin-bottom: 16px;
}

.mask-title {
  font-size: 18px;
  font-weight: 600;
  margin: 0 0 8px;
  color: var(--ant-color-text);
}

.mask-description {
  font-size: 14px;
  color: var(--ant-color-text-secondary);
  margin: 0 0 24px;
  line-height: 1.5;
}

.mask-actions {
  display: flex;
  justify-content: center;
}

.link {
  display: inline-flex;
  align-items: center;
}

.link .anticon {
  margin-right: 8px;
}

.loading-container {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}

.script-list-error {
  margin-bottom: 16px;
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: calc(100vh - 200px);
  text-align: center;
}

.empty-image-container {
  margin-bottom: 16px;
}

.empty-image {
  max-width: 100%;
  height: auto;
}

.empty-title {
  font-size: 18px;
  font-weight: 500;
  margin: 0;
  color: var(--ant-color-text);
}

.empty-description {
  font-size: 14px;
  color: var(--ant-color-text-secondary);
  margin: 0;
}

.scripts-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 24px;
  padding: 0 4px;
}

.header-left {
  flex: 1;
  min-width: 0;
}

.header-actions {
  flex-shrink: 0;
  margin-left: 16px;
}

@media (max-width: 768px) {
  .page-title {
    font-size: 24px;
  }

  .scripts-header {
    padding: 0 2px;
  }

  .header-actions {
    margin-left: 8px;
  }
}

.page-title {
  margin: 0 0 8px 0;
  font-size: 32px;
  font-weight: 700;
  color: var(--ant-color-text);
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.type-select-modal,
.general-mode-modal,
.template-select-modal {
  text-align: left;
}

.type-select-modal :deep(.ant-modal-header),
.general-mode-modal :deep(.ant-modal-header),
.template-select-modal :deep(.ant-modal-header) {
  border-bottom: 2px solid var(--ant-color-border-secondary);
  padding: 20px 24px;
}

.type-select-modal :deep(.ant-modal-title),
.general-mode-modal :deep(.ant-modal-title),
.template-select-modal :deep(.ant-modal-title) {
  font-size: 18px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.type-select-modal :deep(.ant-modal-body),
.general-mode-modal :deep(.ant-modal-body),
.template-select-modal :deep(.ant-modal-body) {
  padding: 24px;
}

.type-select-modal :deep(.ant-modal-footer),
.general-mode-modal :deep(.ant-modal-footer),
.template-select-modal :deep(.ant-modal-footer) {
  padding: 16px 24px;
  border-top: 1px solid var(--ant-color-border-secondary);
}

.type-selection,
.mode-selection,
.template-selection {
  margin-top: 16px;
}

.type-radio-group,
.mode-radio-group {
  display: flex;
  flex-direction: column;
}

/* Hide the small separator (::before) AntD injects between button wrappers */
.type-radio-group :deep(.ant-radio-button-wrapper:not(:first-child)::before) {
  display: none !important;
}

.type-option,
.mode-option {
  height: auto;
  display: flex;
  align-items: center;
  padding: 16px;
  border: 2px solid var(--ant-color-border);
  border-radius: 12px;
  margin-bottom: 12px;
  cursor: pointer;
  background: var(--ant-color-bg-container);
  position: relative;
  overflow: hidden;
}

.type-option:hover,
.mode-option:hover {
  border-color: var(--ant-color-primary);
}

.type-option:deep(.ant-radio-button-input:checked + .ant-radio-button-wrapper),
.mode-option:deep(.ant-radio-button-input:checked + .ant-radio-button-wrapper) {
  border-color: var(--ant-color-primary) !important;
  background: var(--ant-color-primary-bg) !important;
}

/* 选中状态样式 */
.type-radio-group :deep(.ant-radio-button-wrapper-checked) {
  border-color: var(--ant-color-primary) !important;
  background: var(--ant-color-primary-bg) !important;
}

.mode-radio-group :deep(.ant-radio-button-wrapper-checked) {
  border-color: var(--ant-color-primary) !important;
  background: var(--ant-color-primary-bg) !important;
}

/* 选中状态的文字颜色增强 */
.type-radio-group :deep(.ant-radio-button-wrapper-checked) .type-title {
  color: var(--ant-color-primary);
  font-weight: 600;
}

.mode-radio-group :deep(.ant-radio-button-wrapper-checked) .mode-title {
  color: var(--ant-color-primary);
  font-weight: 600;
}

.type-content,
.mode-content {
  display: flex;
  align-items: center;
  width: 100%;
}

.type-logo-container,
.mode-icon {
  width: 48px;
  height: 48px;
  margin-right: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  background: var(--ant-color-primary-bg);
  flex-shrink: 0;
}

.type-logo {
  width: 32px;
  height: 32px;
}

.mode-icon {
  font-size: 24px;
  color: var(--ant-color-primary);
}

.type-info,
.mode-info {
  flex: 1;
}

.type-title,
.mode-title {
  font-size: 16px;
  font-weight: 500;
  margin: 0 0 6px;
  color: var(--ant-color-text);
}

.type-title {
  display: flex;
  min-width: 0;
  gap: 8px;
  align-items: center;
}

.type-tag {
  flex: 0 0 auto;
  margin-inline-end: 0;
}

.type-description,
.mode-description {
  font-size: 13px;
  color: var(--ant-color-text-secondary);
  margin: 0;
  line-height: 1.4;
}

.templates-container {
  margin-top: 16px;
}

.templates-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.templates-count {
  display: flex;
  align-items: center;
  font-size: 14px;
  color: var(--ant-color-text);
}

.count-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  border-radius: 10px;
  background: var(--ant-color-primary);
  color: #fff;
  font-size: 12px;
  font-weight: 500;
  margin-right: 8px;
}

.count-text {
  font-size: 14px;
  color: var(--ant-color-text-secondary);
}

.search-container {
  flex: 1;
  max-width: 300px;
  margin-left: 16px;
}

.template-search {
  width: 100%;
}

.templates-list {
  max-height: 400px;
  overflow-y: auto;
  border: 1px solid var(--ant-color-border);
  border-radius: 6px;
  background: var(--ant-color-bg-container);
}

.template-item {
  padding: 16px;
  border-bottom: 1px solid var(--ant-color-border);
  cursor: pointer;
  background: var(--ant-color-bg-container);
  position: relative;
  border-left: 3px solid transparent;
}

.template-item:last-child {
  border-bottom: none;
}

.template-item:hover {
  border-left-color: var(--ant-color-primary-hover);
}

.template-item.selected {
  background: var(--ant-color-primary-bg);
  border-left-color: var(--ant-color-primary);
}

.template-item.selected .template-name {
  color: var(--ant-color-primary);
  font-weight: 600;
}

.template-content {
  display: flex;
  flex-direction: column;
}

.template-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.template-info {
  flex: 1;
}

.template-name {
  font-size: 16px;
  font-weight: 500;
  margin: 0 0 4px;
  color: var(--ant-color-text);
}

.template-meta {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}

.template-author,
.template-time {
  display: flex;
  align-items: center;
  gap: 4px;
}

.template-description {
  font-size: 14px;
  color: var(--ant-color-text-secondary);
  margin: 0;
  line-height: 1.5;
}

.no-search-results,
.no-templates {
  text-align: center;
  padding: 32px 16px;
  color: var(--ant-color-text-secondary);
}

.no-results-icon,
.no-templates-icon {
  font-size: 48px;
  color: var(--ant-color-text-tertiary);
  margin-bottom: 16px;
}

.no-templates-content h3 {
  color: var(--ant-color-text);
  margin: 0 0 8px;
}

.no-templates-content p {
  color: var(--ant-color-text-secondary);
  margin: 0;
}

.no-results-tip {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
  margin-top: 4px;
}

/* 创建方式选择弹窗样式 */
.create-mode-modal {
  text-align: left;
}

.create-mode-modal :deep(.ant-modal-header) {
  border-bottom: 2px solid var(--ant-color-border-secondary);
  padding: 20px 24px;
}

.create-mode-modal :deep(.ant-modal-title) {
  font-size: 18px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.create-mode-modal :deep(.ant-modal-body) {
  padding: 24px;
}

.create-mode-modal :deep(.ant-modal-footer) {
  padding: 16px 24px;
  border-top: 1px solid var(--ant-color-border-secondary);
}

/* 脚本选择弹窗样式 */
.script-select-modal {
  text-align: left;
}

.script-select-modal :deep(.ant-modal-header) {
  border-bottom: 2px solid var(--ant-color-border-secondary);
  padding: 20px 24px;
}

.script-select-modal :deep(.ant-modal-title) {
  font-size: 18px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.script-select-modal :deep(.ant-modal-body) {
  padding: 24px;
  max-height: 500px;
  overflow-y: auto;
}

.script-select-modal :deep(.ant-modal-footer) {
  padding: 16px 24px;
  border-top: 1px solid var(--ant-color-border-secondary);
}

.script-selection {
  margin-top: 8px;
}

.scripts-list {
  max-height: 450px;
  overflow-y: auto;
  border: 1px solid var(--ant-color-border);
  border-radius: 6px;
  background: var(--ant-color-bg-container);
}

.script-item {
  padding: 16px;
  border-bottom: 1px solid var(--ant-color-border);
  cursor: pointer;
  background: var(--ant-color-bg-container);
  position: relative;
  border-left: 3px solid transparent;
}

.script-item:last-child {
  border-bottom: none;
}

.script-item:hover {
  border-left-color: var(--ant-color-primary-hover);
}

.script-item.selected {
  background: var(--ant-color-primary-bg);
  border-left-color: var(--ant-color-primary);
}

.script-item.selected .script-name {
  color: var(--ant-color-primary);
  font-weight: 600;
}

.script-item-content {
  display: flex;
  align-items: center;
  width: 100%;
}

.script-icon {
  width: 48px;
  height: 48px;
  margin-right: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  background: var(--ant-color-primary-bg);
  flex-shrink: 0;
}

.type-icon {
  width: 32px;
  height: 32px;
}

.script-info {
  flex: 1;
  min-width: 0;
}

.script-name {
  font-size: 16px;
  font-weight: 500;
  margin: 0 0 6px;
  color: var(--ant-color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.script-meta {
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 13px;
  color: var(--ant-color-text-secondary);
}

.script-type {
  font-weight: 500;
}

.script-users {
  display: flex;
  align-items: center;
  gap: 4px;
}

.no-scripts {
  text-align: center;
  padding: 48px 16px;
  color: var(--ant-color-text-secondary);
}
</style>
