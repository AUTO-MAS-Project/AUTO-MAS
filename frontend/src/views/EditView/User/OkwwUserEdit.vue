<template>
  <div class="user-edit-container">
    <teleport to="body">
      <div v-if="showConfigMask" class="maa-config-mask">
        <div class="mask-content">
          <div class="mask-icon">
            <SettingOutlined :style="{ fontSize: '48px', color: 'var(--ant-color-primary)' }" />
          </div>
          <h2 class="mask-title">正在进行 ok-ww 配置</h2>
          <p class="mask-description">
            当前正在为这个用户打开 ok-ww 配置界面，请在 ok-ww 中完成相关设置。
            <br />
            配置完成后，点击“保存配置”结束本次会话。
          </p>
          <div class="mask-actions">
            <a-button v-if="websocketId" type="primary" size="large" @click="handleSaveOkwwConfig">
              保存配置
            </a-button>
          </div>
        </div>
      </div>
    </teleport>

    <div class="user-edit-header">
      <div class="header-nav">
        <a-breadcrumb class="breadcrumb">
          <a-breadcrumb-item>
            <router-link to="/scripts">脚本管理</router-link>
          </a-breadcrumb-item>
          <a-breadcrumb-item>
            <router-link :to="`/scripts/${scriptId}/edit/okww`" class="breadcrumb-link">
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
          v-if="formData.Info.Mode === '详细' && !showConfigMask"
          type="primary"
          ghost
          size="large"
          :loading="configLoading"
          @click="handleOkwwConfig"
        >
          <template #icon>
            <SettingOutlined />
          </template>
          ok-ww 配置
        </a-button>
        <a-button
          v-if="formData.Info.Mode === '详细' && showConfigMask"
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

    <div class="user-edit-content">
      <a-card class="config-card" :loading="pageLoading">
        <a-form :model="formData" layout="vertical" class="config-form">
          <div class="form-section">
            <div class="section-header">
              <h3>基本信息</h3>
            </div>

            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      用户名
                      <a-tooltip title="用于区分用户的名称，相同名称的用户将被视为同一用户进行统计">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-input v-model:value="formData.userName" placeholder="请输入用户名" size="large" class="modern-input" @blur="saveField('Info.Name', formData.userName)" />
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      启用状态
                      <a-tooltip title="是否启用该用户">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-select v-model:value="formData.Info.Status" size="large" @change="saveField('Info.Status', formData.Info.Status)">
                    <a-select-option :value="true">是</a-select-option>
                    <a-select-option :value="false">否</a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
            </a-row>

            <a-row :gutter="24">
              <a-col :span="8">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      用户配置模式
                      <a-tooltip title="简洁模式共用脚本页配置；详细模式每个用户独立配置">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-select v-model:value="formData.Info.Mode" size="large" @change="handleModeChange">
                    <a-select-option value="简洁">简洁</a-select-option>
                    <a-select-option value="详细">详细</a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
              <a-col :span="8">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      剩余天数
                      <a-tooltip title="账号剩余的有效天数，「-1」表示无限">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-input-number v-model:value="formData.Info.RemainedDay" :min="-1" :max="9999" size="large" style="width: 100%" @blur="saveField('Info.RemainedDay', formData.Info.RemainedDay)" />
                </a-form-item>
              </a-col>
              <a-col :span="16">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      备注
                      <a-tooltip title="为用户添加备注信息">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-textarea v-model:value="formData.Info.Notes" :rows="4" class="modern-input" @blur="saveField('Info.Notes', formData.Info.Notes)" />
                </a-form-item>
              </a-col>
            </a-row>
          </div>

          <div class="form-section">
            <div class="section-header">
              <h3>任务配置</h3>
            </div>

            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      启动任务（-t N）
                      <a-tooltip title="任务序号与 ok-ww 任务列表一致">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-select v-model:value="formData.Task.TaskIndex" size="large" @change="handleTaskIndexChange">
                    <a-select-option v-for="item in okwwTaskOptions" :key="item.value" :value="item.value">
                      {{ item.label }}
                    </a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      当前启动参数
                      <a-tooltip title="参数由任务配置自动生成，固定追加 -e">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-input :value="currentStartupArguments" size="large" readonly class="modern-input" />
                </a-form-item>
              </a-col>
            </a-row>
          </div>

          <div class="form-section">
            <div class="section-header">
              <h3>通知配置</h3>
            </div>
            <a-row :gutter="24" align="middle">
              <a-col :span="6">
                <span style="font-weight: 500">启用通知</span>
              </a-col>
              <a-col :span="18">
                <a-switch
                  v-model:checked="formData.Notify.Enabled"
                  @change="saveField('Notify.Enabled', formData.Notify.Enabled)"
                />
              </a-col>
            </a-row>

            <a-row :gutter="24" style="margin-top: 16px">
              <a-col :span="6">
                <span style="font-weight: 500">通知内容</span>
              </a-col>
              <a-col :span="18">
                <a-checkbox
                  v-model:checked="formData.Notify.IfSendStatistic"
                  :disabled="!formData.Notify.Enabled"
                  @change="saveField('Notify.IfSendStatistic', formData.Notify.IfSendStatistic)"
                >
                  统计信息
                </a-checkbox>
              </a-col>
            </a-row>

            <a-row :gutter="24" style="margin-top: 16px">
              <a-col :span="6">
                <a-checkbox
                  v-model:checked="formData.Notify.IfSendMail"
                  :disabled="!formData.Notify.Enabled"
                  @change="saveField('Notify.IfSendMail', formData.Notify.IfSendMail)"
                >
                  邮件通知
                </a-checkbox>
              </a-col>
              <a-col :span="18">
                <a-input
                  v-model:value="formData.Notify.ToAddress"
                  placeholder="请输入收件邮箱"
                  :disabled="!formData.Notify.Enabled || !formData.Notify.IfSendMail"
                  size="large"
                  @blur="saveField('Notify.ToAddress', formData.Notify.ToAddress)"
                />
              </a-col>
            </a-row>

            <a-row :gutter="24" style="margin-top: 16px">
              <a-col :span="6">
                <a-checkbox
                  v-model:checked="formData.Notify.IfServerChan"
                  :disabled="!formData.Notify.Enabled"
                  @change="saveField('Notify.IfServerChan', formData.Notify.IfServerChan)"
                >
                  Server酱
                </a-checkbox>
              </a-col>
              <a-col :span="18">
                <a-input
                  v-model:value="formData.Notify.ServerChanKey"
                  placeholder="请输入 SENDKEY"
                  :disabled="!formData.Notify.Enabled || !formData.Notify.IfServerChan"
                  size="large"
                  @blur="saveField('Notify.ServerChanKey', formData.Notify.ServerChanKey)"
                />
              </a-col>
            </a-row>

            <div style="margin-top: 16px">
              <WebhookManager mode="user" :script-id="scriptId" :user-id="userId" />
            </div>
          </div>
        </a-form>
      </a-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { ArrowLeftOutlined, QuestionCircleOutlined, SettingOutlined } from '@ant-design/icons-vue'
import { Service, TaskCreateIn, type OkwwUserConfig } from '@/api'
import { useUserApi } from '@/composables/useUserApi'
import { useScriptApi } from '@/composables/useScriptApi'
import { subscribe, unsubscribe } from '@/composables/useWebSocket'
import WebhookManager from '@/components/WebhookManager.vue'

const logger = window.electronAPI.getLogger('ok-ww用户编辑')
const route = useRoute()
const router = useRouter()
const { addUser, getUsers, updateUser } = useUserApi()
const { getScript } = useScriptApi()

const scriptId = route.params.scriptId as string
let userId = (route.params.userId as string) || ''
const isEdit = ref(!!userId)
const scriptName = ref('ok-ww脚本')

const pageLoading = ref(true)
const showConfigMask = ref(false)
const configLoading = ref(false)
const subscriptionId = ref<string | null>(null)
const websocketId = ref<string | null>(null)
const isInitializing = ref(true)
const isSaving = ref(false)

const okwwTaskOptions = [
  { label: '1 - DailyTask（日常）', value: 1 },
  { label: '2 - MultiAccountDailyTask（多账号日常）', value: 2 },
  { label: '3 - FarmEchoTask（刷声骸）', value: 3 },
  { label: '4 - AutoRogueTask（自动索拉里斯）', value: 4 },
  { label: '5 - ForgeryTask（锻造）', value: 5 },
  { label: '6 - NightmareNestTask（梦魇巢穴）', value: 6 },
  { label: '7 - SimulationTask（模拟）', value: 7 },
  { label: '8 - TacetTask（无音区）', value: 8 },
  { label: '9 - EnhanceEchoTask（强化声骸）', value: 9 },
  { label: '10 - ChangeEchoTask（换声骸）', value: 10 },
  { label: '11 - DiagnosisTask（诊断）', value: 11 },
]

type OkwwConfigMessage = {
  type?: string
  data?: {
    Accomplish?: unknown
    [key: string]: unknown
  }
}

const getDefaultUserData = () => ({
  Info: {
    Name: '',
    Status: true,
    Mode: '简洁',
    RemainedDay: -1,
    Notes: '',
  },
  Task: {
    TaskIndex: 1,
    ExitOnFinish: true,
  },
  Notify: {
    Enabled: false,
    IfSendStatistic: false,
    IfSendMail: false,
    ToAddress: '',
    IfServerChan: false,
    ServerChanKey: '',
    CustomWebhooks: [],
  },
  Data: {
    LastProxyDate: '',
    ProxyTimes: 0,
  },
})

const formData = reactive({
  userName: '',
  ...(getDefaultUserData() as unknown as OkwwUserConfig),
})

const currentStartupArguments = computed(() => `-t ${formData.Task.TaskIndex || 1} -e`)

const handleCancel = () => router.push('/scripts')

const createUserImmediately = async () => {
  const resp = await addUser(scriptId)
  if (!resp?.userId) {
    throw new Error(resp?.message || '创建用户失败')
  }
  userId = resp.userId
  isEdit.value = true
  await router.replace({
    name: 'OkwwUserEdit',
    params: { scriptId, userId },
  })
}

const saveField = async (key: string, value: unknown) => {
  if (isInitializing.value || isSaving.value || !userId) return

  isSaving.value = true
  try {
    const parts = key.split('.')
    const patch: Record<string, any> = {}
    let current = patch
    for (let i = 0; i < parts.length - 1; i += 1) {
      current[parts[i]] = {}
      current = current[parts[i]]
    }
    current[parts[parts.length - 1]] = value

    if (key === 'Info.Name') {
      formData.userName = String(value || '')
    }

    await updateUser(scriptId, userId, patch)
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
  } finally {
    isSaving.value = false
  }
}

const saveTaskConfig = async () => {
  if (isInitializing.value || !userId) return
  formData.Task.ExitOnFinish = true
  await updateUser(scriptId, userId, {
    Task: {
      TaskIndex: formData.Task.TaskIndex,
      ExitOnFinish: true,
    },
  })
}

const handleTaskIndexChange = async (value: number) => {
  formData.Task.TaskIndex = value
  try {
    await saveTaskConfig()
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
  }
}

const handleModeChange = async (value: '简洁' | '详细') => {
  formData.Info.Mode = value
  await saveField('Info.Mode', value)
}

const loadScriptInfo = async () => {
  const detail = await getScript(scriptId)
  if (detail) {
    scriptName.value = detail.name
  }
}

const loadUser = async () => {
  pageLoading.value = true
  try {
    if (!userId) {
      await createUserImmediately()
    }
    const resp = await getUsers(scriptId, userId)
    const idx = resp?.index?.find(i => i.uid === userId)
    const data = resp?.data?.[userId]
    if (!idx || !data) {
      throw new Error('用户不存在或加载失败')
    }

    Object.assign(formData, {
      Info: { ...getDefaultUserData().Info, ...(data.Info || {}) },
      Task: { ...getDefaultUserData().Task, ...(data.Task || {}) },
      Notify: { ...getDefaultUserData().Notify, ...(data.Notify || {}) },
      Data: { ...getDefaultUserData().Data, ...(data.Data || {}) },
    })
    formData.Task.ExitOnFinish = true
    await nextTick()
    formData.userName = formData.Info.Name || ''
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
    message.error('加载用户失败')
    handleCancel()
  } finally {
    isInitializing.value = false
    pageLoading.value = false
  }
}

const cleanupWs = () => {
  if (subscriptionId.value) {
    unsubscribe(subscriptionId.value)
    subscriptionId.value = null
  }
  websocketId.value = null
  showConfigMask.value = false
}

const handleOkwwConfig = async () => {
  if (!userId) {
    message.error('用户未就绪，请稍后重试')
    return
  }
  if (formData.Info.Mode !== '详细') {
    message.info('当前为简洁模式，请在脚本页使用「配置 ok-ww」按钮')
    return
  }
  try {
    configLoading.value = true
    cleanupWs()

    const resp = await Service.addTaskApiDispatchStartPost({
      taskId: userId,
      mode: TaskCreateIn.mode.SCRIPT_CONFIG,
    })

    if (resp?.code !== 200 || !resp?.taskId) {
      throw new Error(resp?.message || '启动 ok-ww 配置失败')
    }

    websocketId.value = resp.taskId
    const subId = subscribe({ id: resp.taskId }, (wsMessage: OkwwConfigMessage) => {
      if (wsMessage.type === 'error') {
        message.error(`ok-ww 配置连接失败: ${wsMessage.data}`)
        cleanupWs()
        return
      }
      if (wsMessage.type === 'Signal' && wsMessage.data?.Accomplish !== undefined) {
        cleanupWs()
      }
    })
    subscriptionId.value = subId
    showConfigMask.value = true
    message.success('已开始 ok-ww 配置会话')
  } catch (e) {
    message.error(e instanceof Error ? e.message : '启动 ok-ww 配置失败')
  } finally {
    configLoading.value = false
  }
}

const handleSaveOkwwConfig = async () => {
  const wsId = websocketId.value
  if (!wsId) {
    message.error('未找到活动的配置会话')
    return
  }
  try {
    const resp = await Service.stopTaskApiDispatchStopPost({ taskId: wsId })
    if (resp?.code === 200) {
      cleanupWs()
      message.success('ok-ww 配置已保存')
    } else {
      message.error(resp?.message || '保存配置失败')
    }
  } catch {
    message.error('保存配置失败')
  }
}

onMounted(async () => {
  await loadScriptInfo()
  await loadUser()
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
  margin-bottom: 32px;
  padding: 0 8px;
}

.header-nav {
  flex: 1;
}

.breadcrumb {
  margin: 0;
}

.cancel-button {
  border: 1px solid var(--ant-color-border);
  background: var(--ant-color-bg-container);
  color: var(--ant-color-text);
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
  margin-bottom: 32px;
}

.section-header {
  margin-bottom: 20px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--ant-color-border-secondary);
}

.section-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 12px;
}

.section-header h3::before {
  content: '';
  width: 4px;
  height: 24px;
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  border-radius: 2px;
}

.form-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  cursor: help;
}

.modern-input {
  border-radius: 8px;
  border: 2px solid var(--ant-color-border);
}

/* 与 Scripts.vue / MAAUserEdit 配置遮罩一致 */
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

@media (max-width: 768px) {
  .user-edit-container {
    padding: 16px;
  }

  .user-edit-header {
    flex-direction: column;
    gap: 16px;
    align-items: stretch;
  }

  .config-card :deep(.ant-card-body) {
    padding: 20px;
  }
}
</style>

