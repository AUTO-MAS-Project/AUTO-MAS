<template>
  <div class="user-edit-container">
    <div class="user-edit-header">
      <div class="header-nav">
        <a-breadcrumb class="breadcrumb">
          <a-breadcrumb-item>
            <router-link to="/scripts">脚本管理</router-link>
          </a-breadcrumb-item>
          <a-breadcrumb-item>
            <router-link :to="`/scripts/${scriptId}/edit/maaend`" class="breadcrumb-link">
              {{ scriptName }}
            </router-link>
          </a-breadcrumb-item>
          <a-breadcrumb-item>
            {{ isEdit ? '编辑用户' : '添加用户' }}
          </a-breadcrumb-item>
        </a-breadcrumb>
      </div>

      <a-space size="middle">
        <a-button
          v-if="!showMaaEndConfigMask"
          type="primary"
          ghost
          size="large"
          :loading="maaEndConfigLoading"
          @click="handleMaaEndConfig"
        >
          <template #icon>
            <SettingOutlined />
          </template>
          MaaEnd 配置
        </a-button>
        <a-button
          v-if="showMaaEndConfigMask"
          type="default"
          size="large"
          disabled
          style="color: #52c41a; border-color: #52c41a"
        >
          <template #icon>
            <SettingOutlined />
          </template>
          正在配置
        </a-button>
        <a-button size="large" class="cancel-button" @click="handleCancel">
          <template #icon>
            <ArrowLeftOutlined />
          </template>
          返回
        </a-button>
      </a-space>
    </div>

    <teleport to="body">
      <div v-if="showMaaEndConfigMask" class="maaend-config-mask">
        <div class="mask-content">
          <div class="mask-icon">
            <SettingOutlined :style="{ fontSize: '48px', color: '#1890ff' }" />
          </div>
          <h2 class="mask-title">正在进行 MaaEnd 配置</h2>
          <p class="mask-description">
            当前正在配置该用户的 MaaEnd，请在 MaaEnd 配置界面完成相关设置。
            <br />
            配置完成后，请点击"保存配置"按钮来结束配置会话。
          </p>
          <div class="mask-actions">
            <a-button
              v-if="maaEndWebsocketId"
              type="primary"
              size="large"
              @click="handleSaveMaaEndConfig"
            >
              保存配置
            </a-button>
          </div>
        </div>
      </div>
    </teleport>

    <div class="user-edit-content">
      <a-card class="config-card">
        <a-form
          ref="formRef"
          :model="formData"
          :rules="rules"
          layout="vertical"
          class="config-form"
        >
          <div class="form-section">
            <div class="section-header">
              <h3>基本信息</h3>
            </div>
            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item name="userName" required>
                  <template #label>
                    <a-tooltip title="用于识别用户的显示名称">
                      <span class="form-label">
                        用户名
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <a-input
                    v-model:value="formData.userName"
                    placeholder="请输入用户名"
                    :disabled="loading"
                    size="large"
                    class="modern-input"
                    @blur="handleFieldSave('userName', formData.userName)"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="6">
                <a-form-item name="status">
                  <template #label>
                    <a-tooltip title="是否启用该用户">
                      <span class="form-label">
                        启用状态
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <a-select
                    v-model:value="formData.Info.Status"
                    size="large"
                    @change="handleFieldSave('Info.Status', formData.Info.Status)"
                  >
                    <a-select-option :value="true">是</a-select-option>
                    <a-select-option :value="false">否</a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
              <a-col :span="6">
                <a-form-item name="remainedDay">
                  <template #label>
                    <a-tooltip title="账号剩余的有效天数，「-1」表示无限">
                      <span class="form-label">
                        剩余天数
                        <QuestionCircleOutlined class="help-icon" />
                      </span>
                    </a-tooltip>
                  </template>
                  <a-input-number
                    v-model:value="formData.Info.RemainedDay"
                    :min="-1"
                    :max="9999"
                    :disabled="loading"
                    size="large"
                    style="width: 100%"
                    @blur="handleFieldSave('Info.RemainedDay', formData.Info.RemainedDay)"
                  />
                </a-form-item>
              </a-col>
            </a-row>
          </div>

          <div class="form-section">
            <div class="section-header">
              <h3>任务配置</h3>
            </div>
            <a-alert
              message="占位实现"
              description="用户级任务具体配置区域预留，后续版本接入。"
              type="info"
              show-icon
            />
          </div>

          <div class="form-section">
            <div class="section-header">
              <h3>运行状态</h3>
            </div>
            <a-descriptions bordered :column="3" size="small">
              <a-descriptions-item label="上次运行时间">
                {{ formData.Data.LastRun || '-' }}
              </a-descriptions-item>
              <a-descriptions-item label="运行次数">
                {{ formData.Data.RunTimes ?? 0 }}
              </a-descriptions-item>
              <a-descriptions-item label="上次运行状态">
                {{ formData.Data.LastStatus || '-' }}
              </a-descriptions-item>
            </a-descriptions>
          </div>
        </a-form>
      </a-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { ArrowLeftOutlined, QuestionCircleOutlined, SettingOutlined } from '@ant-design/icons-vue'
import type { FormInstance, Rule } from 'ant-design-vue/es/form'
import { useUserApi } from '@/composables/useUserApi'
import { useScriptApi } from '@/composables/useScriptApi'
import { useWebSocket } from '@/composables/useWebSocket'
import { Service } from '@/api'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'

const logger = window.electronAPI.getLogger('MaaEnd用户编辑')

const router = useRouter()
const route = useRoute()
const { addUser, updateUser, getUsers, loading: userLoading } = useUserApi()
const { getScript } = useScriptApi()
const { subscribe, unsubscribe } = useWebSocket()

const formRef = ref<FormInstance>()
const loading = computed(() => userLoading.value)
const isInitializing = ref(true)
const isSaving = ref(false)

const maaEndConfigLoading = ref(false)
const showMaaEndConfigMask = ref(false)
const maaEndSubscriptionId = ref<string | null>(null)
const maaEndWebsocketId = ref<string | null>(null)
let maaEndConfigTimeout: number | null = null

const scriptId = route.params.scriptId as string
let userId = route.params.userId as string
const isEdit = ref(!!userId)
const scriptName = ref('')

const getDefaultMaaEndUserData = () => ({
  Info: {
    Name: '',
    Status: true,
    RemainedDay: -1,
  },
  Task: {
    OptionOverride: '{ }',
  },
  Data: {
    LastRun: '2000-01-01 00:00:00',
    RunTimes: 0,
    LastStatus: '-',
  },
})

const formData = reactive({
  userName: '',
  ...getDefaultMaaEndUserData(),
})

const rules = computed(() => {
  const baseRules: Record<string, Rule[]> = {
    userName: [
      { required: true, message: '请输入用户名', trigger: 'blur' },
      { min: 1, max: 50, message: '用户名长度应在1-50个字符之间', trigger: 'blur' },
    ],
  }
  return baseRules
})

const cleanupConfigSession = () => {
  if (maaEndSubscriptionId.value) {
    unsubscribe(maaEndSubscriptionId.value)
    maaEndSubscriptionId.value = null
  }
  maaEndWebsocketId.value = null
  showMaaEndConfigMask.value = false

  if (maaEndConfigTimeout) {
    window.clearTimeout(maaEndConfigTimeout)
    maaEndConfigTimeout = null
  }
}

const syncUserName = () => {
  if (formData.Info.Name !== formData.userName) {
    formData.Info.Name = formData.userName
  }
}

const validateOptionOverride = (value: string): boolean => {
  const trimmed = (value || '').trim()
  if (!trimmed) return true

  try {
    JSON.parse(trimmed)
    return true
  } catch {
    message.error('任务选项覆盖必须是合法 JSON')
    return false
  }
}

const handleFieldSave = async (key: string, value: any) => {
  if (isInitializing.value || isSaving.value || !userId) {
    logger.debug(
      `跳过保存: 初始化=${isInitializing.value}, 保存中=${isSaving.value}, userId=${userId}`
    )
    return
  }

  if (key === 'userName') {
    syncUserName()
    key = 'Info.Name'
    value = formData.Info.Name
  }

  if (key === 'Task.OptionOverride' && !validateOptionOverride(String(value ?? ''))) {
    return
  }

  isSaving.value = true
  try {
    const parts = key.split('.')
    const userData: Record<string, any> = {}
    let current = userData

    for (let i = 0; i < parts.length - 1; i++) {
      current[parts[i]] = {}
      current = current[parts[i]]
    }
    current[parts[parts.length - 1]] = value

    const success = await updateUser(scriptId, userId, userData)
    if (success) {
      logger.info(`字段已保存: ${key}`)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存字段失败: ${errorMsg}`)
  } finally {
    isSaving.value = false
  }
}

const loadScriptInfo = async () => {
  try {
    const scriptDetail = await getScript(scriptId)
    if (scriptDetail) {
      scriptName.value = scriptDetail.name
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载脚本信息失败: ${errorMsg}`)
  }
}

const loadUserData = async () => {
  try {
    const userResponse = await getUsers(scriptId, userId)

    if (!userResponse || userResponse.code !== 200) {
      message.error('加载用户失败')
      router.push('/scripts')
      return
    }

    const userIndex = userResponse.index.find((index: any) => index.uid === userId)
    if (!userIndex || !userResponse.data[userId]) {
      message.error('用户不存在')
      router.push('/scripts')
      return
    }

    if (userIndex.type !== 'MaaEndUserConfig') {
      message.error('用户类型不匹配')
      router.push('/scripts')
      return
    }

    const userData = userResponse.data[userId] as any
    Object.assign(formData, {
      Info: { ...getDefaultMaaEndUserData().Info, ...userData.Info },
      Task: { ...getDefaultMaaEndUserData().Task, ...userData.Task },
      Data: { ...getDefaultMaaEndUserData().Data, ...userData.Data },
    })

    if (!formData.Task.OptionOverride || !String(formData.Task.OptionOverride).trim()) {
      formData.Task.OptionOverride = '{ }'
    }

    await nextTick()
    formData.userName = formData.Info.Name || ''
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载用户失败: ${errorMsg}`)
    message.error('加载用户失败')
    router.push('/scripts')
  }
}

const handleMaaEndConfig = async () => {
  if (!userId) {
    message.error('请先创建用户')
    return
  }

  try {
    maaEndConfigLoading.value = true
    cleanupConfigSession()

    const response = await Service.addTaskApiDispatchStartPost({
      taskId: userId,
      mode: TaskCreateIn.mode.SCRIPT_CONFIG,
    })

    if (!response || !response.taskId) {
      message.error(response?.message || '启动MaaEnd配置失败')
      return
    }

    const wsId = response.taskId
    const subscriptionId = subscribe({ id: wsId }, async (wsMessage: any) => {
      if (wsMessage.type === 'error') {
        const errText =
          typeof wsMessage.data === 'string' ? wsMessage.data : JSON.stringify(wsMessage.data)
        logger.error(`MaaEnd配置错误: ${errText}`)
        message.error(`MaaEnd配置连接失败: ${errText}`)
        cleanupConfigSession()
        return
      }

      if (wsMessage.type === 'Info' && wsMessage.data && wsMessage.data.Error) {
        logger.error(`MaaEnd配置异常: ${wsMessage.data.Error}`)
        message.error(`MaaEnd配置失败: ${wsMessage.data.Error}`)
        return
      }

      if (
        wsMessage.type === 'Signal' &&
        wsMessage.data &&
        wsMessage.data.Accomplish !== undefined
      ) {
        const result = String(wsMessage.data.Accomplish ?? '')
        if (result && !result.includes('异常') && !result.includes('错误')) {
          message.success(`用户 ${formData.Info?.Name || formData.userName} 的配置已完成`)
        }
        cleanupConfigSession()
        await loadUserData()
      }
    })

    maaEndSubscriptionId.value = subscriptionId
    maaEndWebsocketId.value = wsId
    showMaaEndConfigMask.value = true

    message.success(`已开始配置用户 ${formData.Info?.Name || formData.userName} 的MaaEnd设置`)

    maaEndConfigTimeout = window.setTimeout(
      () => {
        if (maaEndSubscriptionId.value) {
          cleanupConfigSession()
          message.info(`用户 ${formData.Info?.Name || formData.userName} 的配置会话已超时断开`)
        }
      },
      30 * 60 * 1000
    )
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`启动MaaEnd配置失败: ${errorMsg}`)
    message.error('启动MaaEnd配置失败')
  } finally {
    maaEndConfigLoading.value = false
  }
}

const handleSaveMaaEndConfig = async () => {
  try {
    const websocketId = maaEndWebsocketId.value
    if (!websocketId) {
      message.error('未找到活动的配置会话')
      return
    }

    const response = await Service.stopTaskApiDispatchStopPost({ taskId: websocketId })
    if (response && response.code === 200) {
      cleanupConfigSession()
      await loadUserData()
      message.success(`用户 ${formData.Info?.Name || formData.userName} 的配置已保存`)
    } else {
      message.error(response?.message || '保存配置失败')
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存MaaEnd配置失败: ${errorMsg}`)
    message.error('保存MaaEnd配置失败')
  }
}

const handleCancel = () => {
  router.push('/scripts')
}

onMounted(async () => {
  await loadScriptInfo()

  if (!userId) {
    const result = await addUser(scriptId)
    if (result && result.userId) {
      userId = result.userId
      isEdit.value = true
      logger.info(`新建用户，获取userId: ${userId}`)
    } else {
      message.error('创建用户失败')
      router.push('/scripts')
      return
    }
  }

  await loadUserData()
  await nextTick()
  isInitializing.value = false
})

onUnmounted(() => {
  cleanupConfigSession()
})
</script>

<style scoped>
.user-edit-container {
  padding: 32px;
  min-height: 100vh;
  background: var(--ant-color-bg-layout);
}

.user-edit-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.user-edit-content {
  max-width: 1200px;
  margin: 0 auto;
}

.config-card {
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.config-card :deep(.ant-card-body) {
  padding: 32px;
}

.form-section {
  margin-bottom: 24px;
}

.section-header {
  margin-bottom: 16px;
}

.section-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.form-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}

.maaend-config-mask {
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

@media (max-width: 768px) {
  .user-edit-container {
    padding: 16px;
  }

  .user-edit-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }
}
</style>
