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
    @start-maa-config="handleStartMAAConfig"
    @save-maa-config="handleSaveMAAConfig"
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
              <img src="@/assets/AUTO-MAS.ico" alt="AUTO-MAS" class="type-logo" />
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
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  ClockCircleOutlined,
  FileSearchOutlined,
  FileTextOutlined,
  PlusOutlined,
  SettingOutlined,
  UserOutlined,
} from '@ant-design/icons-vue'
import ScriptTable from '@/components/ScriptTable.vue'
import type { Script, ScriptType, User } from '@/types/script'
import { useScriptApi } from '@/composables/useScriptApi'
import { useUserApi } from '@/composables/useUserApi'
import { useWebSocket } from '@/composables/useWebSocket'
import { useTemplateApi, type WebConfigTemplate } from '@/composables/useTemplateApi'
import { Service } from '@/api/services/Service'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import MarkdownIt from 'markdown-it'

const router = useRouter()
const { addScript, deleteScript, getScriptsWithUsers, loading } = useScriptApi()
const { updateUser, deleteUser } = useUserApi()
const { subscribe, unsubscribe } = useWebSocket()
const { getWebConfigTemplates, importScriptFromWeb } = useTemplateApi()

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
        path: `/scripts/${result.scriptId}/edit/maa`,
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
          path: `/scripts/${result.scriptId}/edit/general`,
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
      router.push(`/scripts/${createResult.scriptId}/edit/general`)
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
  // 根据脚本类型跳转到对应的编辑页面
  if (script.type === 'MAA') {
    router.push(`/scripts/${script.id}/edit/maa`)
  } else {
    router.push(`/scripts/${script.id}/edit/general`)
  }
}

const handleDeleteScript = async (script: Script) => {
  const result = await deleteScript(script.id)
  if (result) {
    message.success('脚本删除成功')
    loadScripts()
  }
}

const handleAddUser = (script: Script) => {
  // 根据条件判断跳转到 MAA 还是通用用户添加页面
  if (script.type === 'MAA') {
    router.push(`/scripts/${script.id}/users/add/maa`) // 跳转到 MAA 用户添加页面
  } else {
    router.push(`/scripts/${script.id}/users/add/general`) // 跳转到通用用户添加页面
  }
}

const handleEditUser = (user: User) => {
  // 从用户数据中找到对应的脚本
  const script = scripts.value.find(s => s.users.some(u => u.id === user.id))
  if (script) {
    // 判断是 MAA 用户还是通用用户
    if (user.Info.Server) {
      // 跳转到 MAA 用户编辑页面
      router.push(`/scripts/${script.id}/users/${user.id}/edit/maa`)
    } else {
      // 跳转到通用用户编辑页面
      router.push(`/scripts/${script.id}/users/${user.id}/edit/general`)
    }
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

const handleStartMAAConfig = async (script: Script) => {
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
      mode: TaskCreateIn.mode.SettingScriptMode
    })

    if (response.code === 200) {
      // 订阅WebSocket消息
      subscribe(response.websocketId, {
        onError: error => {
          console.error(`脚本 ${script.name} 连接错误:`, error)
          message.error(`MAA配置连接失败: ${error}`)
          activeConnections.value.delete(script.id)
        },
        onResult: (data: any) => {
          // 处理配置完成消息（兼容任何结构）
          if (data.Accomplish) {
            message.success(`${script.name} 配置已完成`)
            activeConnections.value.delete(script.id)
          }
        }
      })

      // 记录连接和websocketId
      activeConnections.value.set(script.id, response.websocketId)
      message.success(`已启动 ${script.name} 的MAA配置`)

      // 设置自动断开连接的定时器（30分钟后）
      setTimeout(
        () => {
          if (activeConnections.value.has(script.id)) {
            const wsId = activeConnections.value.get(script.id)
            if (wsId) {
              unsubscribe(wsId)
            }
            activeConnections.value.delete(script.id)
            message.info(`${script.name} 配置会话已超时断开`)
          }
        },
        30 * 60 * 1000
      ) // 30分钟
    } else {
      message.error(response.message || '启动MAA配置失败')
    }
  } catch (error) {
    console.error('启动MAA配置失败:', error)
    message.error('启动MAA配置失败')
  }
}

const handleSaveMAAConfig = async (script: Script) => {
  try {
    const websocketId = activeConnections.value.get(script.id)
    if (!websocketId) {
      message.error('未找到活动的配置会话')
      return
    }

    // 调用停止配置任务API
    const response = await Service.stopTaskApiDispatchStopPost({
      taskId: websocketId
    })

    if (response.code === 200) {
      // 取消订阅
      unsubscribe(websocketId)
      activeConnections.value.delete(script.id)
      message.success(`${script.name} 的配置已保存`)
    } else {
      message.error(response.message || '保存配置失败')
    }
  } catch (error) {
    console.error('保存MAA配置失败:', error)
    message.error('保存MAA配置失败')
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
      message.success('用户状态更新成功')
    }
  } catch (error) {
    console.error('更新用户状态失败:', error)
    message.error('更新用户状态失败')
  }
}
</script>

<style scoped>
.loading-container {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}

.scripts-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.header-title h1 {
  font-size: 28px;
  font-weight: 600;
  margin: 0;
}

.empty-state {
  text-align: center;
  padding: 40px 20px;
}

.empty-image-container {
  margin-bottom: 16px;
}

.empty-title {
  font-size: 22px;
  font-weight: 500;
  margin: 0 0 8px 0;
}

.empty-description {
  font-size: 16px;
  color: var(--ant-color-text-secondary);
}

/* 模态框通用样式 */
.type-select-modal :deep(.ant-modal-content),
.general-mode-modal :deep(.ant-modal-content),
.template-select-modal :deep(.ant-modal-content) {
  border-radius: 12px;
}

.type-select-modal :deep(.ant-modal-header),
.general-mode-modal :deep(.ant-modal-header),
.template-select_modal :deep(.ant-modal-header) {
  border-bottom: 1px solid var(--ant-color-border);
  padding: 16px 24px;
}

.type-select-modal :deep(.ant-modal-title),
.general-mode_modal :deep(.ant-modal-title),
.template-select-modal :deep(.ant-modal-title) {
  font-size: 18px;
  font-weight: 600;
}

.type-select-modal :deep(.ant-modal-body),
.general-mode-modal :deep(.ant-modal-body) {
  padding: 24px;
}

.template-select-modal :deep(.ant-modal-body) {
  padding: 0;
}

/* 选择组样式 */
.type-selection,
.mode-selection {
  margin: 16px 0;
}

.type-radio-group,
.mode-radio-group {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.type-radio-group :deep(.ant-radio-button-wrapper),
.mode-radio-group :deep(.ant-radio-button-wrapper) {
  height: auto;
  padding: 0;
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
  transition: all 0.3s ease;
  text-align: left;
}

.type-radio-group :deep(.ant-radio-button-wrapper:hover),
.mode-radio-group :deep(.ant-radio-button-wrapper:hover) {
  border-color: var(--ant-color-primary);
}

.type-radio-group :deep(.ant-radio-button-wrapper-checked),
.mode-radio-group :deep(.ant-radio-button-wrapper-checked) {
  border-color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-primary);
}

.type-radio-group :deep(.ant-radio-button-wrapper::before),
.mode-radio-group :deep(.ant-radio-button-wrapper::before) {
  display: none;
}

.type-radio-group :deep(.ant-radio-button-wrapper .ant-radio-button),
.mode-radio-group :deep(.ant-radio-button-wrapper .ant-radio-button) {
  display: none;
}

.type-content {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
  width: 100%;
}

.mode-content {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
}

.type-logo-container {
  width: 40px;
  height: 40px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--ant-color-bg-elevated);
  border: 1px solid var(--ant-color-border-secondary);
  flex-shrink: 0;
}

.type-logo {
  width: 32px;
  height: 32px;
  object-fit: contain;
}

.mode-icon {
  font-size: 24px;
  color: var(--ant-color-primary);
  flex-shrink: 0;
}

.type-info,
.mode-info {
  flex: 1;
}

.type-title,
.mode-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--ant-color-text);
  margin-bottom: 4px;
}

.type-description,
.mode-description {
  font-size: 14px;
  color: var(--ant-color-text-secondary);
  line-height: 1.4;
}

/* 模板选择样式 */
.template-selection {
  min-height: 400px;
}

.no-templates {
  text-align: center;
  padding: 60px 20px;
}

.no-templates-content {
  color: var(--ant-color-text-secondary);
}

.no-templates-icon {
  font-size: 48px;
  margin-bottom: 16px;
  color: var(--ant-color-text-tertiary);
}

.templates-container {
  height: 600px;
  display: flex;
  flex-direction: column;
}

.templates-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 24px;
  border-bottom: 1px solid var(--ant-color-border);
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
}

.count-text {
  color: var(--ant-color-text-secondary);
}

.search-container {
  flex: 1;
  max-width: 300px;
  margin-left: 16px;
}

.templates-list {
  flex: 1;
  overflow-y: auto;
  padding: 0 24px 24px;
  /* 隐藏滚动条 */
  scrollbar-width: none; /* Firefox */
  -ms-overflow-style: none; /* IE and Edge */
}

.templates-list::-webkit-scrollbar {
  display: none; /* Chrome, Safari and Opera */
}

.no-search-results {
  text-align: center;
  padding: 60px 20px;
  color: var(--ant-color-text-secondary);
}

.no-results-icon {
  font-size: 48px;
  margin-bottom: 16px;
  color: var(--ant-color-text-tertiary);
}

.no-results-tip {
  font-size: 14px;
  color: var(--ant-color-text-tertiary);
}

.template-item {
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  margin-bottom: 16px;
  cursor: pointer;
  transition: all 0.3s ease;
  background: var(--ant-color-bg-container);
}

.template-item:hover {
  border-color: var(--ant-color-primary);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.template-item.selected {
  border-color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
}

.template-content {
  padding: 20px;
}

.template-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
}

.template-name {
  margin: 0 0 8px 0;
  font-size: 16px;
  font-weight: 600;
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
  color: var(--ant-color-text-secondary);
  line-height: 1.5;
}

.template-description :deep(p) {
  margin: 0 0 8px 0;
}

.template-description :deep(p:last-child) {
  margin-bottom: 0;
}
</style>
