<template>

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

    <ScriptTable
      :scripts="scripts"
      @edit="handleEditScript"
      @delete="handleDeleteScript"
      @add-user="handleAddUser"
      @edit-user="handleEditUser"
      @delete-user="handleDeleteUser"
      @maa-config="handleMAAConfig"
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
              <div class="type-description">明日方舟自动化脚本，支持日常任务、作战等功能</div>
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
              <div class="type-description">通用自动化脚本，支持自定义游戏和脚本配置</div>
            </div>
          </div>
        </a-radio-button>
      </a-radio-group>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import ScriptTable from '@/components/ScriptTable.vue'
import type { Script, ScriptType, User } from '@/types/script'
import { useScriptApi } from '@/composables/useScriptApi'
import { useUserApi } from '@/composables/useUserApi'

const router = useRouter()
const { addScript, deleteScript, getScriptsWithUsers, loading } = useScriptApi()
const { addUser, updateUser, deleteUser, loading: userLoading } = useUserApi()

const scripts = ref<Script[]>([])
const typeSelectVisible = ref(false)
const selectedType = ref<ScriptType>('MAA')
const addLoading = ref(false)

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

const handleMAAConfig = (script: Script) => {
  // TODO: 实现MAA全局配置功能
  console.log('设置MAA全局配置:', script)
  message.info('MAA全局配置功能待实现')
}

const handleToggleUserStatus = (user: User) => {
  // TODO: 实现用户状态切换功能
  console.log('切换用户状态:', user)
  message.info(`切换用户 ${user.Info.Name} 的状态功能待实现`)
}
</script>

<style scoped>
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

.type-radio-group :deep(.ant-radio-button-wrapper:hover) {
  border-color: var(--ant-color-primary);
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(24, 144, 255, 0.2);
}

.type-radio-group :deep(.ant-radio-button-wrapper-checked) {
  border-color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
  box-shadow: 0 4px 16px rgba(24, 144, 255, 0.3);
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

/* 深色模式适配 */
@media (prefers-color-scheme: dark) {
  .scripts-content {
    box-shadow:
      0 4px 20px rgba(0, 0, 0, 0.3),
      0 1px 3px rgba(0, 0, 0, 0.4);
  }

  .scripts-content:hover {
    box-shadow:
      0 8px 30px rgba(0, 0, 0, 0.4),
      0 2px 6px rgba(0, 0, 0, 0.5);
  }

  .add-button {
    box-shadow: 0 4px 12px rgba(24, 144, 255, 0.4);
  }

  .add-button:hover {
    box-shadow: 0 6px 16px rgba(24, 144, 255, 0.5);
  }

  .refresh-button:hover {
    box-shadow: 0 4px 12px rgba(255, 255, 255, 0.1);
  }
}

/* 响应式设计 */
@media (max-width: 768px) {
  .scripts-container {
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
}
</style>
