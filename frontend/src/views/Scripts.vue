<template>
  <!-- 加载状态 -->
  <div v-if="loading" class="loading-container">
    <a-spin size="large" tip="加载中，请稍候..." />
  </div>

  <!-- 主要内容 -->
  <div class="scripts-header">
    <div class="header-title">
      <h1>脚本管理</h1>
    </div>
    <a-space size="middle">
      <a-button type="primary" size="large" @click="handleAddScript" class="link">
        <template #icon>
          <PlusOutlined />
        </template>
        新建脚本
      </a-button>
      <a-button size="large" @click="handleRefresh" class="default">
        <template #icon>
          <ReloadOutlined />
        </template>
        刷新
      </a-button>
    </a-space>
  </div>

  <!-- 空状态 -->
  <div v-if="scripts.length === 0" class="empty-state">
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
    :scripts="scripts"
    :active-connections="activeConnections"
    @edit="handleEditScript"
    @delete="handleDeleteScript"
    @add-user="handleAddUser"
    @edit-user="handleEditUser"
    @delete-user="handleDeleteUser"
    @maa-config="handleMAAConfig"
    @disconnect-maa="handleDisconnectMAA"
    @toggle-user-status="handleToggleUserStatus"
  />

  <!-- 脚本类型选择弹窗 -->
  <a-modal
    v-model:open="typeSelectVisible"
    title="选择脚本类型"
    :confirm-loading="addLoading"
    @ok="handleConfirmAddScript"
    @cancel="typeSelectVisible = false"
    class="type-select-modal"
    width="500px"
    ok-text="确定"
    cancel-text="取消"
  >
    <div class="type-selection">
      <a-radio-group v-model:value="selectedType" class="type-radio-group">
        <a-radio-button value="MAA" class="type-option">
          <div class="type-content">
            <div class="type-logo-container">
              <img src="@/assets/MAA.png" alt="MAA" class="type-logo" />
            </div>
            <div class="type-info">
              <div class="type-title">MAA脚本</div>
              <div class="type-description">明日方舟自动化脚本，支持多账号日常代理等功能</div>
            </div>
          </div>
        </a-radio-button>
        <a-radio-button value="General" class="type-option">
          <div class="type-content">
            <div class="type-logo-container">
              <img src="@/assets/AUTO_MAA.png" alt="AUTO_MAA" class="type-logo" />
            </div>
            <div class="type-info">
              <div class="type-title">通用脚本</div>
              <div class="type-description">通用自动化脚本，适用于所有具备日志文件的脚本</div>
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
    @ok="handleConfirmGeneralMode"
    @cancel="generalModeSelectVisible = false"
    class="general-mode-modal"
    width="600px"
    ok-text="确定"
    cancel-text="返回"
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
    @ok="handleConfirmTemplate"
    @cancel="handleCancelTemplate"
    class="template-select-modal"
    width="1000px"
    ok-text="使用此模板"
    cancel-text="返回"
    :ok-button-props="{ disabled: !selectedTemplate }"
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

                <div
                  class="template-description"
                  v-html="parseMarkdown(template.description)"
                ></div>
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
  FileSearchOutlined,
  FileTextOutlined,
  PlusOutlined,
  ReloadOutlined,
  SettingOutlined,
  UserOutlined,
} from '@ant-design/icons-vue'
import ScriptTable from '@/components/ScriptTable.vue'
import type { Script, ScriptType, User } from '@/types/script'
import { useScriptApi } from '@/composables/useScriptApi'
import { useUserApi } from '@/composables/useUserApi'
import { useWebSocket } from '@/composables/useWebSocket'
import { useTemplateApi, type WebConfigTemplate } from '@/composables/useTemplateApi'
import MarkdownIt from 'markdown-it'

const router = useRouter()
const { addScript, deleteScript, getScriptsWithUsers, loading } = useScriptApi()
const { addUser, updateUser, deleteUser, loading: userLoading } = useUserApi()
const { connect, disconnect, disconnectAll } = useWebSocket()
const { getWebConfigTemplates, importScriptFromWeb, loading: templateApiLoading } = useTemplateApi()

// 初始化markdown解析器
const md = new MarkdownIt({
  html: false,
  linkify: true,
  typographer: true,
})

const scripts = ref<Script[]>([])
const typeSelectVisible = ref(false)
const generalModeSelectVisible = ref(false)
const templateSelectVisible = ref(false)
const selectedType = ref<ScriptType>('MAA')
const selectedGeneralMode = ref('template')
const selectedTemplate = ref<WebConfigTemplate | null>(null)
const templates = ref<WebConfigTemplate[]>([])
const addLoading = ref(false)
const templateLoading = ref(false)
const searchKeyword = ref('')

// WebSocket连接管理
const activeConnections = ref<Map<string, string>>(new Map()) // scriptId -> websocketId

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

onMounted(() => {
  loadScripts()
})

onUnmounted(() => {
  // 清理所有WebSocket连接
  disconnectAll()
})

const loadScripts = async () => {
  try {
    const scriptDetails = await getScriptsWithUsers()

    // 将 ScriptDetail 转换为 Script 格式（为了兼容现有的表格组件）
    scripts.value = scriptDetails.map(detail => ({
      id: detail.uid,
      type: detail.type,
      name: detail.name,
      config: detail.config,
      users: detail.users || [],
      createTime: detail.createTime || new Date().toLocaleString(),
    }))
  } catch (error) {
    console.error('加载脚本列表失败:', error)
    message.error('加载脚本列表失败')
  }
}

const handleAddScript = () => {
  selectedType.value = 'MAA'
  typeSelectVisible.value = true
}

const handleConfirmAddScript = async () => {
  if (selectedType.value === 'General') {
    // 如果选择通用脚本，进入创建方式选择
    typeSelectVisible.value = false
    generalModeSelectVisible.value = true
    return
  }

  // MAA脚本直接创建
  addLoading.value = true
  try {
    const result = await addScript(selectedType.value)
    if (result) {
      message.success(result.message)
      typeSelectVisible.value = false
      // 跳转到编辑页面，传递API返回的数据
      router.push({
        path: `/scripts/${result.scriptId}/edit`,
        state: {
          scriptData: {
            id: result.scriptId,
            type: selectedType.value,
            config: result.data,
          },
        },
      })
    }
  } catch (error) {
    console.error('添加脚本失败:', error)
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
      const result = await addScript('General')
      if (result) {
        message.success(result.message)
        router.push({
          path: `/scripts/${result.scriptId}/edit`,
          state: {
            scriptData: {
              id: result.scriptId,
              type: 'General',
              config: result.data,
            },
          },
        })
      }
    } catch (error) {
      console.error('添加脚本失败:', error)
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
    console.error('加载模板列表失败:', error)
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
    const createResult = await addScript('General')
    if (!createResult) {
      return
    }

    // 2. 使用模板URL导入配置
    const importResult = await importScriptFromWeb(
      createResult.scriptId,
      selectedTemplate.value.downloadUrl
    )

    if (importResult) {
      message.success(`已根据模板 "${selectedTemplate.value.configName}" 创建脚本`)
      templateSelectVisible.value = false
      selectedTemplate.value = null

      // 刷新脚本列表
      await loadScripts()

      // 跳转到编辑页面，不传递state数据，让编辑页面从API重新加载最新配置
      router.push(`/scripts/${createResult.scriptId}/edit`)
    }
  } catch (error) {
    console.error('使用模板创建脚本失败:', error)
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
  // 跳转到独立的编辑页面
  router.push(`/scripts/${script.id}/edit`)
}

const handleDeleteScript = async (script: Script) => {
  const result = await deleteScript(script.id)
  if (result) {
    message.success('脚本删除成功')
    loadScripts()
  }
}

const handleAddUser = (script: Script) => {
  // 跳转到添加用户页面
  router.push(`/scripts/${script.id}/users/add`)
}

const handleEditUser = (user: User) => {
  // 从用户数据中找到对应的脚本
  const script = scripts.value.find(s => s.users.some(u => u.id === user.id))
  if (script) {
    // 跳转到编辑用户页面
    router.push(`/scripts/${script.id}/users/${user.id}/edit`)
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

  const result = await deleteUser(script.id, user.id)
  if (result) {
    // 删除成功后，从本地数据中移除用户
    const userIndex = script.users.findIndex(u => u.id === user.id)
    if (userIndex > -1) {
      script.users.splice(userIndex, 1)
    }
    message.success('用户删除成功')
  }
}

const handleRefresh = () => {
  loadScripts()
  message.success('刷新成功')
}

const handleMAAConfig = async (script: Script) => {
  try {
    // 检查是否已有连接
    const existingWebsocketId = activeConnections.value.get(script.id)
    if (existingWebsocketId) {
      message.warning('该脚本已在配置中，请先断开连接')
      return
    }

    // 建立WebSocket连接进行MAA配置
    const websocketId = await connect({
      taskId: script.id,
      mode: '设置脚本',
      showNotifications: true,
      onStatusChange: status => {
        console.log(`脚本 ${script.name} 连接状态: ${status}`)
      },
      onMessage: data => {
        console.log(`脚本 ${script.name} 收到消息:`, data)
        // 这里可以根据需要处理特定的消息
      },
      onError: error => {
        console.error(`脚本 ${script.name} 连接错误:`, error)
        message.error(`MAA配置连接失败: ${error}`)
        // 清理连接记录
        activeConnections.value.delete(script.id)
      },
    })

    if (websocketId) {
      // 记录连接
      activeConnections.value.set(script.id, websocketId)
      message.success(`已开始配置 ${script.name}`)

      // 可选：设置自动断开连接的定时器（比如30分钟后）
      setTimeout(
        () => {
          if (activeConnections.value.has(script.id)) {
            disconnect(websocketId)
            activeConnections.value.delete(script.id)
            message.info(`${script.name} 配置会话已超时断开`)
          }
        },
        30 * 60 * 1000
      ) // 30分钟
    }
  } catch (error) {
    console.error('MAA配置失败:', error)
    message.error('MAA配置失败')
  }
}

const handleDisconnectMAA = (script: Script) => {
  const websocketId = activeConnections.value.get(script.id)
  if (websocketId) {
    disconnect(websocketId)
    activeConnections.value.delete(script.id)
    message.success(`已断开 ${script.name} 的配置连接`)
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
    const newStatus = !user.Info.Status

    // 调用 updateUser API
    const result = await updateUser(script.id, user.id, {
      Info: {
        ...user.Info,
        Status: newStatus,
      },
    })

    if (result) {
      // 本地同步状态
      user.Info.Status = newStatus
      // message.success(`用户 ${user.Info.Name} 已${newStatus ? '启用' : '禁用'}`)
    }
  } catch (error) {
    console.error('切换用户状态失败:', error)
    message.error('切换用户状态失败')
  }
}
</script>

<style scoped>
.loading-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 400px;
}

.scripts-main {
  padding: 32px;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--ant-color-bg-layout);
  min-height: 100vh;
}

.scripts-container {
  padding: 32px;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--ant-color-bg-layout);
  min-height: 100vh;
}

.scripts-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 32px;
  padding: 0 8px;
}

.header-title {
  display: flex;
  align-items: center;
  gap: 16px;
}

.title-icon {
  font-size: 32px;
  color: var(--ant-color-primary);
}

.header-title h1 {
  margin: 0;
  font-size: 32px;
  font-weight: 700;
  color: var(--ant-color-text);
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

/* 空状态样式 */
.empty-state {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 500px;
  padding: 60px 20px;
  background: linear-gradient(135deg, rgba(24, 144, 255, 0.02), rgba(24, 144, 255, 0.01));
  border-radius: 16px;
  margin: 20px 0;
}

.empty-content {
  text-align: center;
  max-width: 480px;
  animation: fadeInUp 0.8s ease-out;
}

.empty-image-container {
  position: relative;
  margin-bottom: 32px;
  display: inline-block;
}

.empty-image-container::before {
  content: '';
  position: absolute;
  top: -20px;
  left: -20px;
  right: -20px;
  bottom: -20px;
  background: radial-gradient(circle, rgba(24, 144, 255, 0.1) 0%, transparent 70%);
  border-radius: 50%;
  animation: pulse 3s ease-in-out infinite;
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

.empty-text-content {
  margin-top: 16px;
}

.empty-title {
  font-size: 24px;
  font-weight: 600;
  color: var(--ant-color-text);
  margin: 0 0 12px 0;
  background: linear-gradient(135deg, var(--ant-color-text), var(--ant-color-text-secondary));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.empty-description {
  font-size: 16px;
  color: var(--ant-color-text-secondary);
  line-height: 1.6;
  margin: 0;
  opacity: 0.8;
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(30px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes pulse {
  0%, 100% {
    opacity: 0.6;
    transform: scale(1);
  }
  50% {
    opacity: 0.8;
    transform: scale(1.05);
  }
}

/* 脚本类型选择弹窗样式 */
.type-select-modal :deep(.ant-modal-content) {
  border-radius: 16px;
  overflow: hidden;
  background: var(--ant-color-bg-container);
}

.type-select-modal :deep(.ant-modal-header) {
  background: var(--ant-color-bg-container);
  border-bottom: 1px solid var(--ant-color-border-secondary);
  padding: 24px 32px 20px;
}

.type-select-modal :deep(.ant-modal-title) {
  font-size: 20px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.type-select-modal :deep(.ant-modal-body) {
  padding: 32px;
}

.type-selection {
  margin: 16px 0;
}

.type-radio-group {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.type-radio-group :deep(.ant-radio-button-wrapper) {
  height: auto;
  padding: 0;
  border: 2px solid var(--ant-color-border);
  border-radius: 12px;
  background: var(--ant-color-bg-container);
  transition: all 0.3s ease;
  overflow: hidden;
}

.type-radio-group :deep(.ant-radio-button-wrapper-checked) {
  border-color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
}

.type-radio-group :deep(.ant-radio-button-wrapper::before) {
  display: none;
}

.type-content {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px 24px;
  width: 100%;
}

.type-logo-container {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--ant-color-bg-elevated);
  border: 1px solid var(--ant-color-border-secondary);
  flex-shrink: 0;
  overflow: hidden;
}

.type-logo {
  width: 36px;
  height: 36px;
  object-fit: contain;
  transition: all 0.3s ease;
}

.type-info {
  flex: 1;
}

.type-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--ant-color-text);
  margin-bottom: 4px;
}

.type-description {
  font-size: 14px;
  color: var(--ant-color-text-secondary);
  line-height: 1.5;
}

/* 通用脚本创建方式选择弹窗样式 */
.general-mode-select-modal :deep(.ant-modal-content) {
  border-radius: 16px;
  overflow: hidden;
  background: var(--ant-color-bg-container);
}

.general-mode-select-modal :deep(.ant-modal-header) {
  background: var(--ant-color-bg-container);
  border-bottom: 1px solid var(--ant-color-border-secondary);
  padding: 24px 32px 20px;
}

.general-mode-select-modal :deep(.ant-modal-title) {
  font-size: 20px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.general-mode-select-modal :deep(.ant-modal-body) {
  padding: 32px;
}

.mode-selection {
  margin: 16px 0;
}

.mode-radio-group {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.mode-radio-group :deep(.ant-radio-button-wrapper) {
  height: auto;
  padding: 0;
  border: 2px solid var(--ant-color-border);
  border-radius: 12px;
  background: var(--ant-color-bg-container);
  transition: all 0.3s ease;
  overflow: hidden;
}

.mode-radio-group :deep(.ant-radio-button-wrapper-checked) {
  border-color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
  box-shadow: 0 4px 16px rgba(24, 144, 255, 0.3);
}

.mode-radio-group :deep(.ant-radio-button-wrapper::before) {
  display: none;
}

.mode-content {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  border-radius: 12px;
  background: var(--ant-color-bg-elevated);
  border: 1px solid var(--ant-color-border-secondary);
  transition: all 0.3s ease;
}

/* 模板选择弹窗样式 */
.template-select-modal :deep(.ant-modal-content) {
  border-radius: 20px;
  overflow: hidden;
  background: var(--ant-color-bg-container);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.12);
}

.template-select-modal :deep(.ant-modal-header) {
  background: linear-gradient(135deg, var(--ant-color-bg-container), var(--ant-color-primary-bg));
  border-bottom: 1px solid var(--ant-color-border-secondary);
  padding: 28px 36px 24px;
}

.template-select-modal :deep(.ant-modal-title) {
  font-size: 22px;
  font-weight: 700;
  color: var(--ant-color-text);
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.template-select-modal :deep(.ant-modal-body) {
  padding: 0 36px 36px;
  background: var(--ant-color-bg-layout);
}

.template-selection {
  margin: 0;
}

.template-list {
  width: 100%;
  max-height: 400px;
  overflow-y: auto;
}

.template-item {
  cursor: pointer;
  transition: all 0.3s ease;
  border-radius: 12px;
  margin-bottom: 12px;
  border: 2px solid var(--ant-color-border);
  background: var(--ant-color-bg-container);
}

.template-item.selected {
  border-color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
  box-shadow: 0 4px 16px rgba(24, 144, 255, 0.3);
}

.template-item-content {
  padding: 16px 20px;
}

.template-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.template-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.template-author {
  font-size: 14px;
  color: var(--ant-color-text-secondary);
}

.template-description {
  font-size: 14px;
  color: var(--ant-color-text-secondary);
  margin: 8px 0;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.template-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 12px;
}

.template-time {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
  display: flex;
  align-items: center;
  gap: 4px;
}

.no-templates {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 300px;
  background: var(--ant-color-bg-container);
  border-radius: 16px;
  margin-top: 20px;
}

.no-templates-content {
  text-align: center;
  padding: 40px;
  max-width: 400px;
}

.no-templates-icon {
  font-size: 64px;
  color: var(--ant-color-text-tertiary);
  margin-bottom: 24px;
  opacity: 0.6;
}

.no-templates-content h3 {
  font-size: 20px;
  font-weight: 600;
  color: var(--ant-color-text);
  margin: 0 0 12px;
}

.no-templates-content p {
  font-size: 14px;
  color: var(--ant-color-text-secondary);
  line-height: 1.6;
  margin: 0;
}

.mode-icon {
  font-size: 20px;
  color: var(--ant-color-primary);
}

.mode-info {
  flex: 1;
}

.mode-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--ant-color-text);
  margin-bottom: 4px;
}

.mode-description {
  font-size: 14px;
  color: var(--ant-color-text-secondary);
  line-height: 1.4;
}

/* 深色模式适配 */
@media (prefers-color-scheme: dark) {
  .scripts-content {
    box-shadow:
      0 4px 20px rgba(0, 0, 0, 0.3),
      0 1px 3px rgba(0, 0, 0, 0.4);
  }

  .add-button {
    box-shadow: 0 4px 12px rgba(24, 144, 255, 0.4);
  }
}

/* 响应式设计 */
@media (max-width: 768px) {
  .scripts-main {
    padding: 16px;
  }

  .scripts-header {
    flex-direction: column;
    gap: 16px;
    align-items: stretch;
  }

  .header-title h1 {
    font-size: 24px;
  }

  .scripts-content {
    padding: 16px;
  }

  .type-content {
    padding: 16px;
  }

  .type-icon {
    font-size: 24px;
  }

  .type-title {
    font-size: 16px;
  }

  /* 模板选择弹窗响应式 */
  .template-select-modal {
    width: 95vw !important;
    max-width: 600px;
  }

  .template-select-modal :deep(.ant-modal-body) {
    padding: 0 20px 20px;
  }

  .templates-container {
    padding: 16px;
  }

  .templates-list {
    max-height: 350px;
  }

  .templates-header {
    flex-direction: column;
    gap: 12px;
    align-items: stretch;
  }

  .search-container {
    max-width: none;
    margin-left: 0;
  }

  .templates-header {
    flex-direction: column;
    gap: 12px;
    align-items: flex-start;
  }

  .template-card-header {
    padding: 20px;
  }

  .template-card-body {
    padding: 20px;
    min-height: 120px;
  }

  .template-card-footer {
    padding: 16px 20px;
  }

  .template-title {
    font-size: 16px;
  }
}

/* 模板容器样式 */
.templates-container {
  background: var(--ant-color-bg-container);
  border-radius: 12px;
  padding: 20px;
  margin-top: 16px;
}

.templates-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.templates-count {
  display: flex;
  align-items: center;
  gap: 8px;
}

.count-badge {
  background: var(--ant-color-primary);
  color: white;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
  min-width: 20px;
  text-align: center;
}

.count-text {
  font-size: 14px;
  font-weight: 500;
  color: var(--ant-color-text);
}

.search-container {
  flex: 1;
  max-width: 300px;
  margin-left: 16px;
}

.template-search {
  width: 100%;
}

/* 模板列表布局 */
.templates-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 450px;
  overflow-y: auto;
  /* 隐藏滚动条 */
  scrollbar-width: none;
  /* Firefox */
  -ms-overflow-style: none;
  /* IE and Edge */
}

.templates-list::-webkit-scrollbar {
  display: none;
  /* Chrome, Safari and Opera */
}

.template-item {
  background: var(--ant-color-bg-elevated);
  border: 1px solid var(--ant-color-border);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.template-item.selected {
  border-color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
  box-shadow: 0 0 0 1px var(--ant-color-primary-border);
}

.template-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 24px;
  background: linear-gradient(135deg, rgba(24, 144, 255, 0.05), rgba(24, 144, 255, 0.02));
  border-bottom: 1px solid var(--ant-color-border-secondary);
  position: relative;
}

.template-icon-wrapper::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: linear-gradient(45deg, rgba(255, 255, 255, 0.2), transparent);
  border-radius: 16px;
}

.template-icon {
  font-size: 20px;
  color: white;
  z-index: 1;
}

.template-badge {
  background: var(--ant-color-success);
  color: white;
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.badge-text {
  font-size: 12px;
}

.template-card-body {
  padding: 24px;
  min-height: 140px;
  display: flex;
  flex-direction: column;
  flex: 1;
}

.template-title-wrapper {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16px;
}

.template-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--ant-color-text);
  margin: 0;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  flex: 1;
  margin-right: 12px;
}

.selected-indicator {
  flex-shrink: 0;
}

.selected-icon {
  font-size: 20px;
  color: var(--ant-color-success);
  animation: checkmark 0.3s ease-in-out;
}

@keyframes checkmark {
  0% {
    transform: scale(0);
    opacity: 0;
  }

  50% {
    transform: scale(1.2);
  }

  100% {
    transform: scale(1);
    opacity: 1;
  }
}

.template-description {
  font-size: 14px;
  color: var(--ant-color-text-secondary);
  line-height: 1.6;
  margin: 0;
  flex: 1;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.template-card-footer {
  padding: 20px 24px;
  background: rgba(0, 0, 0, 0.02);
  border-top: 1px solid var(--ant-color-border-secondary);
  margin-top: auto;
}

.template-meta {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--ant-color-text-secondary);
}

.meta-icon {
  font-size: 14px;
  color: var(--ant-color-text-tertiary);
}

.meta-text {
  font-weight: 500;
}

/* 新的模板项样式 */
.template-content {
  padding: 12px 16px;
}

.template-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 8px;
}

.template-info {
  flex: 1;
}

.template-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--ant-color-text);
  margin: 0 0 6px 0;
  line-height: 1.3;
}

.template-meta {
  display: flex;
  gap: 12px;
  font-size: 11px;
  color: var(--ant-color-text-tertiary);
}

.template-author,
.template-time {
  display: flex;
  align-items: center;
  gap: 3px;
}

.template-selector {
  margin-left: 12px;
  flex-shrink: 0;
}

.template-description {
  font-size: 13px;
  color: var(--ant-color-text-secondary);
  line-height: 1.4;
  margin-top: 4px;
}

.template-description :deep(p) {
  margin: 0 0 6px 0;
}

.template-description :deep(p:last-child) {
  margin-bottom: 0;
}

.template-description :deep(code) {
  background: var(--ant-color-bg-layout);
  padding: 1px 3px;
  border-radius: 3px;
  font-size: 11px;
}

.template-description :deep(strong) {
  font-weight: 600;
  color: var(--ant-color-text);
}

.template-description :deep(em) {
  font-style: italic;
}

.template-description :deep(ul),
.template-description :deep(ol) {
  margin: 6px 0;
  padding-left: 16px;
}

.template-description :deep(li) {
  margin: 2px 0;
}

/* 搜索无结果样式 */
.no-search-results {
  text-align: center;
  padding: 40px 20px;
  color: var(--ant-color-text-secondary);
}

.no-results-icon {
  font-size: 48px;
  color: var(--ant-color-text-tertiary);
  margin-bottom: 16px;
  opacity: 0.6;
}

.no-search-results p {
  margin: 0 0 8px 0;
  font-size: 14px;
}

.no-results-tip {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}
</style>
