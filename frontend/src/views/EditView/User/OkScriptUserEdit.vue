<template>
  <div class="user-edit-container">
    <PageHeader
      :title="formData.userName || (isEdit ? '编辑用户' : '添加用户')"
      :subtitle="`${scriptName} · ok-script 用户配置`"
      :bordered="false"
      compact
      transparent
    >
      <a-tag color="blue">ok-script</a-tag>
      <template #actions>
        <a-button class="cancel-button" @click="handleCancel">
          <template #icon>
            <ArrowLeftOutlined />
          </template>
          返回
        </a-button>
      </template>
    </PageHeader>

    <div class="user-edit-content">
      <a-spin :spinning="pageLoading" tip="加载用户配置中...">
        <div class="config-surface">
          <a-alert
            v-if="saveError"
            class="save-error"
            type="error"
            show-icon
            :message="saveError"
          />
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
                        <a-tooltip
                          title="用于区分用户的名称，相同名称的用户将被视为同一用户进行统计"
                        >
                          <QuestionCircleOutlined class="help-icon" />
                        </a-tooltip>
                      </span>
                    </template>
                    <a-input
                      v-model:value="formData.userName"
                      placeholder="请输入用户名"
                      size="large"
                      class="modern-input"
                      @blur="saveField('Info.Name', formData.userName)"
                    />
                  </a-form-item>
                </a-col>
                <a-col :span="6">
                  <a-form-item>
                    <template #label>
                      <span class="form-label">
                        启用状态
                        <a-tooltip title="是否启用该用户">
                          <QuestionCircleOutlined class="help-icon" />
                        </a-tooltip>
                      </span>
                    </template>
                    <a-select
                      v-model:value="formData.Info.Status"
                      size="large"
                      class="modern-select"
                      @change="saveField('Info.Status', formData.Info.Status)"
                    >
                      <a-select-option :value="true">是</a-select-option>
                      <a-select-option :value="false">否</a-select-option>
                    </a-select>
                  </a-form-item>
                </a-col>
                <a-col :span="6">
                  <a-form-item>
                    <template #label>
                      <span class="form-label">
                        剩余天数
                        <a-tooltip title="账号剩余的有效天数，「-1」表示无限">
                          <QuestionCircleOutlined class="help-icon" />
                        </a-tooltip>
                      </span>
                    </template>
                    <a-input-number
                      v-model:value="formData.Info.RemainedDay"
                      :min="-1"
                      :max="9999"
                      size="large"
                      style="width: 100%"
                      @blur="saveField('Info.RemainedDay', formData.Info.RemainedDay)"
                    />
                  </a-form-item>
                </a-col>
              </a-row>

              <a-form-item>
                <template #label>
                  <span class="form-label">
                    备注
                    <a-tooltip title="为用户添加备注信息">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-textarea
                  v-model:value="formData.Info.Notes"
                  placeholder="请输入备注"
                  :rows="4"
                  class="modern-input"
                  @blur="saveField('Info.Notes', formData.Info.Notes)"
                />
              </a-form-item>
            </div>
          </a-form>

          <a-form :model="formData" layout="vertical" class="config-form">
            <div class="form-section">
              <div class="section-header">
                <h3>任务配置</h3>
              </div>

              <a-alert
                v-if="providerMetadata?.runtimeVerified === false"
                type="warning"
                show-icon
                :message="providerMetadata.runtimeBlockReason || '当前项目暂未完成运行验证'"
                style="margin-bottom: 16px"
              />
              <a-alert
                v-else-if="!providerMetadata && !pageLoading"
                type="info"
                show-icon
                message="请先在脚本页选择已适配的 ok-script 项目"
                style="margin-bottom: 16px"
              />

              <a-row :gutter="24">
                <a-col :span="12">
                  <a-form-item>
                    <template #label>
                      <span class="form-label">
                        启动任务（-t N）
                        <a-tooltip title="任务序号与 ok-script 一次性任务列表一致">
                          <QuestionCircleOutlined class="help-icon" />
                        </a-tooltip>
                      </span>
                    </template>
                    <a-select
                      v-model:value="formData.Task.TaskIndex"
                      size="large"
                      class="modern-select"
                      :disabled="taskOptions.length === 0"
                      @change="handleTaskIndexChange"
                    >
                      <a-select-option
                        v-for="item in taskOptions"
                        :key="item.value"
                        :value="item.value"
                      >
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
                    <a-input
                      :value="currentStartupArguments"
                      :placeholder="taskOptions.length ? '' : '选择项目后自动生成'"
                      size="large"
                      readonly
                      class="modern-input"
                    />
                  </a-form-item>
                </a-col>
              </a-row>
            </div>
          </a-form>

          <section v-if="userId && providerMetadata" class="editor-section">
            <OkScriptConfigEditor
              :script-id="scriptId"
              :user-id="userId"
              endpoint-prefix="/plugin/ok-script/configs"
              @saved="handleConfigSaved"
            />
          </section>

          <a-form :model="formData" layout="vertical" class="config-form">
            <ExtraScriptSection :form-data="formData" :loading="pageLoading" @save="saveField" />
          </a-form>

          <a-form :model="formData" layout="vertical" class="config-form">
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
                  <a-space-compact block>
                    <a-input-password
                      v-model:value="formData.Notify.ServerChanKey"
                      :placeholder="
                        serverChanKeyConfigured ? '已配置，留空保持不变' : '请输入 SENDKEY'
                      "
                      :disabled="!formData.Notify.Enabled || !formData.Notify.IfServerChan"
                      size="large"
                      @blur="saveField('Notify.ServerChanKey', formData.Notify.ServerChanKey)"
                    />
                    <a-button
                      v-if="serverChanKeyConfigured && !formData.Notify.ServerChanKey"
                      danger
                      size="large"
                      :disabled="isSaving"
                      @click="confirmClearServerChanKey"
                    >
                      清空原值
                    </a-button>
                  </a-space-compact>
                </a-col>
              </a-row>

              <div style="margin-top: 16px">
                <WebhookManager mode="user" :script-id="scriptId" :user-id="userId" />
              </div>
            </div>
          </a-form>
        </div>
      </a-spin>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import { ArrowLeftOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import PageHeader from '@/components/mac/PageHeader.vue'
import { useUserApi } from '@/composables/useUserApi'
import { useScriptApi } from '@/composables/useScriptApi'
import {
  useOkScriptConfigApi,
  type OkScriptProviderMetadata,
} from '@/composables/useOkScriptConfigApi'
import WebhookManager from '@/components/WebhookManager.vue'
import ExtraScriptSection from '@/components/ExtraScriptSection.vue'
import OkScriptConfigEditor from '@/views/OkScriptUserEdit/OkScriptConfigEditor.vue'

const logger = window.electronAPI.getLogger('ok-script用户编辑')
const route = useRoute()
const router = useRouter()
const { addUser, getUsers, updateUser } = useUserApi()
const { getScript } = useScriptApi()
const okScriptConfigApi = useOkScriptConfigApi('/plugin/ok-script/configs')

const scriptId = route.params.scriptId as string
const userId = ref((route.params.userId as string) || '')
const isEdit = ref(!!userId.value)
const scriptName = ref('ok-script 项目')

const pageLoading = ref(true)
const isInitializing = ref(true)
const isSaving = ref(false)
const saveError = ref('')
const serverChanKeyConfigured = ref(false)

interface OkScriptUserInfoForm {
  Name: string
  Status: boolean
  RemainedDay: number
  IfScriptBeforeTask: boolean
  ScriptBeforeTask: string
  IfScriptAfterTask: boolean
  ScriptAfterTask: string
  Notes: string
}

interface OkScriptUserTaskForm {
  TaskIndex: number
}

interface OkScriptUserNotifyForm {
  Enabled: boolean
  IfSendStatistic: boolean
  IfSendMail: boolean
  ToAddress: string
  IfServerChan: boolean
  ServerChanKey: string
  CustomWebhooks: unknown[]
}

interface OkScriptUserDataForm {
  LastProxyDate: string
  ProxyTimes: number
  LastProxyStatus: string
  LastTaskIndex: number
}

interface OkScriptUserFormData {
  userName: string
  Info: OkScriptUserInfoForm
  Task: OkScriptUserTaskForm
  Notify: OkScriptUserNotifyForm
  Data: OkScriptUserDataForm
}

type OkScriptUserApiData = Partial<{
  Info: Partial<OkScriptUserInfoForm>
  Task: Partial<OkScriptUserTaskForm>
  Notify: Partial<OkScriptUserNotifyForm>
  Data: Partial<OkScriptUserDataForm>
}>

const getDefaultUserData = (): Omit<OkScriptUserFormData, 'userName'> => ({
  Info: {
    Name: '',
    Status: true,
    RemainedDay: -1,
    IfScriptBeforeTask: false,
    ScriptBeforeTask: '',
    IfScriptAfterTask: false,
    ScriptAfterTask: '',
    Notes: '',
  },
  Task: {
    TaskIndex: 1,
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
    LastProxyDate: '2000-01-01',
    ProxyTimes: 0,
    LastProxyStatus: '未知',
    LastTaskIndex: 0,
  },
})

const formData = reactive<OkScriptUserFormData>({
  userName: '',
  ...getDefaultUserData(),
})

const providerMetadata = ref<OkScriptProviderMetadata | null>(null)

const taskOptions = computed(() => providerMetadata.value?.taskOptions || [])
const currentStartupArguments = computed(() =>
  taskOptions.value.length ? `-t ${formData.Task.TaskIndex || 1} -e` : ''
)

const handleCancel = () => router.push('/scripts')

const createUserImmediately = async () => {
  const resp = await addUser(scriptId)
  if (!resp?.userId) {
    throw new Error(resp?.message || '创建用户失败')
  }
  userId.value = resp.userId
  isEdit.value = true
  await router.replace({
    name: 'OkScriptUserEdit',
    params: { scriptId, userId: userId.value },
  })
}

const saveField = async (key: string, value: unknown) => {
  if (isInitializing.value || isSaving.value || !userId.value) return
  if (key === 'Notify.ServerChanKey' && !String(value || '').trim()) return

  isSaving.value = true
  saveError.value = ''
  try {
    const parts = key.split('.')
    const patch: Record<string, unknown> = {}
    let current = patch
    for (let i = 0; i < parts.length - 1; i += 1) {
      current[parts[i]] = {}
      current = current[parts[i]] as Record<string, unknown>
    }
    current[parts[parts.length - 1]] = value

    if (key === 'Info.Name') {
      formData.userName = String(value || '')
    }

    const saved = await updateUser(scriptId, userId.value, patch)
    if (!saved) {
      throw new Error('用户配置保存失败，请检查后端连接')
    }
    if (key === 'Notify.ServerChanKey') {
      serverChanKeyConfigured.value = true
      formData.Notify.ServerChanKey = ''
    }
  } catch (e) {
    const errorMsg = e instanceof Error ? e.message : String(e)
    saveError.value = errorMsg
    logger.error(errorMsg)
    message.error(errorMsg)
  } finally {
    isSaving.value = false
  }
}

const clearServerChanKey = async () => {
  if (isInitializing.value || isSaving.value || !userId.value) return

  isSaving.value = true
  saveError.value = ''
  try {
    const saved = await updateUser(scriptId, userId.value, {
      Notify: { ServerChanKey: '' },
    })
    if (!saved) {
      throw new Error('ServerChanKey 清空失败，请检查后端连接')
    }
    serverChanKeyConfigured.value = false
    formData.Notify.ServerChanKey = ''
    message.success('ServerChanKey 已清空')
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    saveError.value = errorMsg
    logger.error('ServerChanKey 清空失败')
    message.error(errorMsg)
    throw error
  } finally {
    isSaving.value = false
  }
}

const confirmClearServerChanKey = () => {
  Modal.confirm({
    title: '清空已保存的 ServerChanKey？',
    content: '清空后无法恢复，如需继续使用必须重新填写。',
    okText: '清空',
    okType: 'danger',
    cancelText: '取消',
    onOk: clearServerChanKey,
  })
}

const saveTaskConfig = async () => {
  if (isInitializing.value || !userId.value) return
  const saved = await updateUser(scriptId, userId.value, {
    Task: {
      TaskIndex: formData.Task.TaskIndex,
    },
  })
  if (!saved) {
    throw new Error('任务配置保存失败，请检查后端连接')
  }
}

const handleTaskIndexChange = async (value: number) => {
  formData.Task.TaskIndex = value
  saveError.value = ''
  try {
    await saveTaskConfig()
  } catch (e) {
    const errorMsg = e instanceof Error ? e.message : String(e)
    saveError.value = errorMsg
    logger.error(errorMsg)
    message.error(errorMsg)
  }
}

const loadProjectConfig = async () => {
  if (!userId.value) return
  providerMetadata.value = null
  try {
    const resp = await okScriptConfigApi.listConfigFiles(scriptId, userId.value)
    if (resp?.code !== 200) {
      logger.warn(`项目配置暂不可用: ${resp?.message || '未选择已适配项目'}`)
      return
    }

    providerMetadata.value = resp.provider || null
  } catch (e) {
    const errorMsg = e instanceof Error ? e.message : String(e)
    logger.error(`加载项目配置失败: ${errorMsg}`)
    message.error(`加载项目配置失败: ${errorMsg}`)
  }
}

const handleConfigSaved = () => {
  logger.info('配置已保存')
}

const loadScriptInfo = async () => {
  const detail = await getScript(scriptId)
  if (!detail) {
    message.error('脚本不存在或加载失败')
    handleCancel()
    return false
  }
  if (detail.type !== 'OkScript') {
    message.error('脚本类型不是 ok-script 项目')
    handleCancel()
    return false
  }
  scriptName.value = detail.name
  return true
}

const clampTaskIndex = (value: unknown): number | null => {
  if (!taskOptions.value.length) return null

  const taskIndex = Number(value)
  const defaultTaskIndex = taskOptions.value[0]?.value || 1
  if (!Number.isFinite(taskIndex)) return defaultTaskIndex
  const normalizedTaskIndex = Math.trunc(taskIndex)
  return taskOptions.value.some(option => option.value === normalizedTaskIndex)
    ? normalizedTaskIndex
    : defaultTaskIndex
}

const loadUser = async () => {
  pageLoading.value = true
  try {
    if (!userId.value) {
      await createUserImmediately()
    }
    const resp = await getUsers(scriptId, userId.value)
    const userIndex = resp?.index?.find(i => i.uid === userId.value)
    const data = resp?.data?.[userId.value]
    if (!userIndex || !data) {
      throw new Error('用户不存在或加载失败')
    }

    const userData = data as OkScriptUserApiData
    const defaults = getDefaultUserData()
    serverChanKeyConfigured.value = Boolean(userData.Notify?.ServerChanKey)
    const notify = { ...defaults.Notify, ...(userData.Notify || {}), ServerChanKey: '' }

    Object.assign(formData, {
      Info: { ...defaults.Info, ...(userData.Info || {}) },
      Task: { ...defaults.Task, ...(userData.Task || {}) },
      Notify: notify,
      Data: { ...defaults.Data, ...(userData.Data || {}) },
    })

    await loadProjectConfig()

    const normalizedTaskIndex = clampTaskIndex(formData.Task.TaskIndex)
    if (normalizedTaskIndex !== null && normalizedTaskIndex !== formData.Task.TaskIndex) {
      formData.Task.TaskIndex = normalizedTaskIndex
      const saved = await updateUser(scriptId, userId.value, {
        Task: {
          TaskIndex: normalizedTaskIndex,
        },
      })
      if (!saved) {
        throw new Error('任务配置自动修正失败')
      }
    }

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

onMounted(async () => {
  if (!(await loadScriptInfo())) {
    isInitializing.value = false
    pageLoading.value = false
    return
  }
  await loadUser()
})
</script>

<style scoped>
.user-edit-container {
  min-height: 100%;
}

.cancel-button {
  border-radius: var(--v6-radius-control);
}

.user-edit-content {
  width: min(100%, 1280px);
  margin: 0 auto;
  padding: 0 var(--v6-content-padding-inline) var(--v6-space-8);
}

.config-surface {
  padding: var(--v6-space-5);
  border: 1px solid var(--v6-color-border-subtle);
  border-radius: var(--v6-radius-card);
  background: var(--v6-vibrancy-material);
  box-shadow: var(--v6-shadow-card);
  backdrop-filter: var(--v6-backdrop-vibrancy);
  -webkit-backdrop-filter: var(--v6-backdrop-vibrancy);
}

.form-section {
  margin: 0;
  padding: var(--v6-space-5) 0;
  border-bottom: 1px solid var(--v6-color-border-subtle);
}

.config-form:first-of-type .form-section {
  padding-top: 0;
}

.section-header {
  margin-bottom: var(--v6-space-4);
  padding-bottom: var(--v6-space-2);
  border-bottom: 1px solid var(--v6-color-border-subtle);
}

.section-header h3 {
  margin: 0;
  font-size: var(--v6-font-size-lg);
  font-weight: var(--v6-font-weight-semibold);
  display: flex;
  align-items: center;
  color: var(--v6-color-text);
}

.form-label {
  display: flex;
  align-items: center;
  gap: var(--v6-space-2);
  font-weight: var(--v6-font-weight-medium);
}

.help-icon {
  color: var(--v6-color-text-tertiary);
  cursor: help;
}

.modern-select {
  width: 100%;
}

.editor-section {
  padding: var(--v6-space-5) 0;
  border-bottom: 1px solid var(--v6-color-border-subtle);
}

.save-error {
  margin-bottom: var(--v6-space-4);
  border-radius: var(--v6-radius-control);
}

.config-form:last-child .form-section {
  padding-bottom: 0;
  border-bottom: 0;
}

:root[data-perf-mode='low'] .config-surface {
  background: var(--v6-color-surface);
  box-shadow: none;
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
}

@media (max-width: 768px) {
  .user-edit-content {
    padding-inline: var(--v6-space-4);
  }

  .config-surface {
    padding: var(--v6-space-4);
  }

  .config-form :deep(.ant-col) {
    flex: 0 0 100%;
    max-width: 100%;
  }
}
</style>
