<template>
  <div class="user-edit-container">
    <UserEditHeader
      :script-id="scriptId"
      :script-name="scriptName"
      :is-edit="isEdit"
      script-edit-segment="oknte"
      config-label="配置 OK-NTE"
      :config-loading="oknteConfigLoading"
      :config-active="showOkNteConfigMask"
      :config-disabled="pageLoading || !activeUserId"
      @config="handleOkNteConfig"
      @cancel="handleCancel"
    />

    <teleport to="body">
      <div v-if="showOkNteConfigMask" class="oknte-config-mask">
        <div class="mask-content">
          <div class="mask-icon">
            <SettingOutlined :style="{ fontSize: '48px', color: 'var(--ant-color-primary)' }" />
          </div>
          <h2 class="mask-title">正在进行 OK-NTE 配置</h2>
          <p class="mask-description">
            当前正在进行该用户的 OK-NTE GUI 配置，请在 OK-NTE 界面完成相关设置。
            <br />
            配置完成后，请点击“保存配置”按钮来结束配置会话。
          </p>
          <div class="mask-actions">
            <a-button v-if="oknteTaskId" type="primary" size="large" @click="handleSaveOkNteConfig">
              保存配置
            </a-button>
          </div>
        </div>
      </div>
    </teleport>

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
                  <a-input
                    v-model:value="formData.userName"
                    placeholder="请输入用户名"
                    size="large"
                    @blur="saveField('Info.Name', formData.userName)"
                  />
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
                  <a-select
                    v-model:value="formData.Info.Status"
                    size="large"
                    @change="saveField('Info.Status', formData.Info.Status)"
                  >
                    <a-select-option :value="true">是</a-select-option>
                    <a-select-option :value="false">否</a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
            </a-row>

            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      账号
                      <a-tooltip title="用于切换账号，无需切换则留空。官服输入 11 位手机号">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-input
                    v-model:value="formData.Info.Id"
                    placeholder="请输入账号"
                    size="large"
                    @blur="saveField('Info.Id', formData.Info.Id)"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      密码
                      <a-tooltip title="PC 端需要切换账号时必须填写">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-input-password
                    v-model:value="formData.Info.Password"
                    placeholder="请输入密码"
                    size="large"
                    @blur="saveField('Info.Password', formData.Info.Password)"
                  />
                </a-form-item>
              </a-col>
            </a-row>

            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      游戏资源
                      <a-tooltip title="选择当前用户使用的游戏资源">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-select
                    v-model:value="formData.Info.Resource"
                    placeholder="请选择资源"
                    size="large"
                    :options="resourceOptions"
                    @change="saveField('Info.Resource', formData.Info.Resource)"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="12">
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
                @blur="saveField('Info.Notes', formData.Info.Notes)"
              />
            </a-form-item>
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
                      <a-tooltip title="任务序号与 OK-NTE 任务列表一致">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-select
                    v-model:value="formData.Task.TaskIndex"
                    size="large"
                    @change="handleTaskIndexChange"
                  >
                    <a-select-option
                      v-for="item in oknteTaskOptions"
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
                  <a-input :value="currentStartupArguments" size="large" readonly />
                </a-form-item>
              </a-col>
            </a-row>
          </div>
        </a-form>
      </a-card>

      <!-- OK-NTE 配置编辑器 -->
      <a-card class="config-card" style="margin-top: 24px">
        <OkNteConfigEditor
          v-if="activeUserId"
          :script-id="scriptId"
          :user-id="activeUserId"
          :refresh-token="oknteConfigRefreshToken"
          @saved="handleConfigSaved"
        />
      </a-card>

      <a-card class="config-card" style="margin-top: 24px">
        <a-form :model="formData" layout="vertical" class="config-form">
          <UserNotifyConfig
            v-model="formData.Notify"
            :loading="pageLoading"
            :script-id="scriptId"
            :user-id="activeUserId"
            @save="saveField"
          />
        </a-form>
      </a-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { QuestionCircleOutlined, SettingOutlined } from '@ant-design/icons-vue'
import { Service, type OkNteUserConfig } from '@/api'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import { useUserApi } from '@/composables/useUserApi'
import { useScriptApi } from '@/composables/useScriptApi'
import { useWebSocket } from '@/composables/useWebSocket'
import {
  WS_TASK_COMPLETED,
  WS_TASK_NOTICE,
  type WSTaskCompletedData,
  type WSTaskNoticeData,
} from '@/services/websocket/types'
import UserEditHeader from '@/components/UserEditHeader.vue'
import UserNotifyConfig from '@/components/UserNotifyConfig.vue'
import OkNteConfigEditor from './OkNteUserEdit/OkNteConfigEditor.vue'

const logger = window.electronAPI.getLogger('OK-NTE用户编辑')
const route = useRoute()
const router = useRouter()
const { addUser, getUsers, updateUser } = useUserApi()
const { getScript } = useScriptApi()
const { subscribe, unsubscribe } = useWebSocket()

const scriptId = route.params.scriptId as string
let userId = (route.params.userId as string) || ''
const isEdit = ref(!!userId)
const activeUserId = ref(userId)
const scriptName = ref('OK-NTE脚本')

const pageLoading = ref(true)
const isInitializing = ref(true)
const isSaving = ref(false)
const oknteConfigLoading = ref(false)
const oknteSubscriptionIds = ref<string[]>([])
const oknteTaskId = ref<string | null>(null)
const showOkNteConfigMask = ref(false)
const oknteConfigRefreshToken = ref(0)
let oknteConfigTimeout: number | null = null

/** OK-NTE 已适配任务（-t 1..19）；新版上游 DailyRoutineTask 是 -t 2 */
const OKNTE_MAX_TASK_INDEX = 19

const resourceOptions = [{ label: '官服', value: '官服' }]

const oknteTaskOptions = [
  { label: '1 - LauncherTask（启动游戏）', value: 1 },
  { label: '2 - DailyRoutineTask（日常任务）', value: 2 },
  { label: '3 - FishingTask（自动钓鱼）', value: 3 },
  { label: '4 - AnomalyTask（异象界域）', value: 4 },
  { label: '5 - AnomalyHunter（异象追猎）', value: 5 },
  { label: '6 - RhythmTask（自动音游）', value: 6 },
  { label: '7 - OwnerSelectionTask（店长特供）', value: 7 },
  { label: '8 - AutoHeistTask（自动粉爪大劫案）', value: 8 },
  { label: '9 - BagelAITools（呗果智能体）', value: 9 },
  { label: '10 - WhirlwindTask（自动小旋风）', value: 10 },
  { label: '11 - DSDFarmTask（九百九十九夜）', value: 11 },
  { label: '12 - CombatDetectionTestTask（自动战斗检测诊断）', value: 12 },
  { label: '13 - DiagnosisTask（诊断）', value: 13 },
  { label: '14 - DailyClaimTask（日常领取）', value: 14 },
  { label: '15 - GiftTask（羁遇赠礼）', value: 15 },
  { label: '16 - CoffeeTask（一咖舍）', value: 16 },
  { label: '17 - FountainTask（喷泉签到）', value: 17 },
  { label: '18 - FurnitureTask（异象家具）', value: 18 },
  { label: '19 - CinemaDateTask（影院约会）', value: 19 },
]

type FormSection<T> = { [K in keyof T]-?: NonNullable<T[K]> }

type OkNteUserFormData = {
  userName: string
  Info: FormSection<NonNullable<OkNteUserConfig['Info']>>
  Task: FormSection<NonNullable<OkNteUserConfig['Task']>>
  Notify: FormSection<NonNullable<OkNteUserConfig['Notify']>>
  Data: FormSection<NonNullable<OkNteUserConfig['Data']>>
}

const getDefaultUserData = (): Omit<OkNteUserFormData, 'userName'> => ({
  Info: {
    Name: '',
    Status: true,
    Id: '',
    Password: '',
    Mode: '简洁',
    Resource: '官服',
    RemainedDay: -1,
    IfUseMasConfig: true,
    IfScriptBeforeTask: false,
    ScriptBeforeTask: '',
    IfScriptAfterTask: false,
    ScriptAfterTask: '',
    Notes: '',
    Tag: '',
  },
  Task: {
    TaskIndex: 2,
    ExitOnFinish: true,
  },
  Notify: {
    Enabled: false,
    IfSendStatistic: false,
    IfSendMail: false,
    ToAddress: '',
    IfServerChan: false,
    ServerChanKey: '',
  },
  Data: {
    LastProxyDate: '',
    ProxyTimes: 0,
    LastProxyStatus: '',
    LastTaskIndex: 0,
  },
})

const formData = reactive<OkNteUserFormData>({
  userName: '',
  ...getDefaultUserData(),
})

const currentStartupArguments = computed(() => `-t ${formData.Task.TaskIndex || 2} -e`)

const clearOkNteConfigSession = () => {
  for (const subscriptionId of oknteSubscriptionIds.value) {
    unsubscribe(subscriptionId)
  }
  oknteSubscriptionIds.value = []
  oknteTaskId.value = null
  showOkNteConfigMask.value = false
  if (oknteConfigTimeout) {
    window.clearTimeout(oknteConfigTimeout)
    oknteConfigTimeout = null
  }
}

const handleCancel = () => {
  clearOkNteConfigSession()
  router.push('/scripts')
}

const refreshOkNteConfigEditor = () => {
  oknteConfigRefreshToken.value += 1
}

const createUserImmediately = async () => {
  const resp = await addUser(scriptId)
  if (!resp?.userId) {
    throw new Error(resp?.message || '创建用户失败')
  }
  userId = resp.userId
  activeUserId.value = userId
  isEdit.value = true
  await router.replace({
    name: 'OkNteUserEdit',
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

const handleOkNteConfig = async () => {
  if (!userId) {
    message.error('请先创建用户后再配置 OK-NTE')
    return
  }

  try {
    oknteConfigLoading.value = true
    showOkNteConfigMask.value = true
    clearOkNteConfigSession()
    showOkNteConfigMask.value = true

    const response = await Service.addTaskApiDispatchStartPost({
      taskId: userId,
      mode: TaskCreateIn.mode.SCRIPT_CONFIG,
    })

    if (!response?.taskId) {
      message.error(response?.message || '启动 OK-NTE 配置失败')
      showOkNteConfigMask.value = false
      return
    }

    const wsId = response.taskId
    const subscriptionIds = [
      // 处理任务提示中的错误消息（不取消订阅，等待任务结束消息）
      subscribe({ id: wsId, type: WS_TASK_NOTICE }, wsMessage => {
        const data = wsMessage.data as unknown as WSTaskNoticeData
        if (data.level === 'error') {
          logger.error(`用户 ${formData.userName} OK-NTE 配置异常: ${data.message}`)
          message.error(`OK-NTE 配置失败: ${data.message}`)
        }
      }),
      // 处理任务结束消息
      subscribe({ id: wsId, type: WS_TASK_COMPLETED }, wsMessage => {
        const data = wsMessage.data as unknown as WSTaskCompletedData
        logger.info(`用户 ${formData.userName} OK-NTE 配置任务已结束`)
        if (data.outcome === 'success') {
          refreshOkNteConfigEditor()
          message.success(`用户 ${formData.userName} 的 OK-NTE 配置已完成`)
        }
        clearOkNteConfigSession()
      }),
    ]

    oknteSubscriptionIds.value = subscriptionIds
    oknteTaskId.value = wsId
    message.success(`已开始配置用户 ${formData.userName} 的 OK-NTE 设置`)

    oknteConfigTimeout = window.setTimeout(
      async () => {
        if (oknteTaskId.value) {
          message.warning('OK-NTE 配置会话已超时，正在自动保存配置')
          await handleSaveOkNteConfig()
        }
      },
      30 * 60 * 1000
    )
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
    message.error('启动 OK-NTE 配置失败')
    showOkNteConfigMask.value = false
  } finally {
    oknteConfigLoading.value = false
  }
}

const handleSaveOkNteConfig = async () => {
  const taskId = oknteTaskId.value
  if (!taskId) {
    message.error('未找到活动的 OK-NTE 配置会话')
    return
  }

  try {
    const response = await Service.stopTaskApiDispatchStopPost({ taskId })
    if (response?.code === 200) {
      refreshOkNteConfigEditor()
      clearOkNteConfigSession()
      message.success('用户的 OK-NTE 配置已保存')
    } else {
      message.error(response?.message || '保存 OK-NTE 配置失败')
    }
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
    message.error('保存 OK-NTE 配置失败')
  }
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
    const userIndex = resp?.index?.find(i => i.uid === userId)
    const data = resp?.data?.[userId] as OkNteUserConfig | undefined
    if (!userIndex || !data) {
      throw new Error('用户不存在或加载失败')
    }

    Object.assign(formData, {
      Info: { ...getDefaultUserData().Info, ...(data.Info || {}) },
      Task: { ...getDefaultUserData().Task, ...(data.Task || {}) },
      Notify: { ...getDefaultUserData().Notify, ...(data.Notify || {}) },
      Data: { ...getDefaultUserData().Data, ...(data.Data || {}) },
    })
    formData.Task.ExitOnFinish = true
    const taskIndex = Number(formData.Task.TaskIndex)
    if (!Number.isFinite(taskIndex) || taskIndex < 1 || taskIndex > OKNTE_MAX_TASK_INDEX) {
      formData.Task.TaskIndex = 2
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

const handleConfigSaved = () => {
  logger.info('OK-NTE 配置已保存')
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

.oknte-config-mask {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.45);
}

.mask-content {
  width: 100%;
  max-width: 480px;
  padding: 24px;
  text-align: center;
  background: var(--ant-color-bg-elevated);
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  box-shadow:
    0 6px 16px 0 rgba(0, 0, 0, 0.08),
    0 3px 6px -4px rgba(0, 0, 0, 0.12),
    0 9px 28px 8px rgba(0, 0, 0, 0.05);
}

.mask-icon {
  margin-bottom: 16px;
}

.mask-title {
  margin: 0 0 8px;
  font-size: 18px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.mask-description {
  margin: 0 0 24px;
  font-size: 14px;
  line-height: 1.5;
  color: var(--ant-color-text-secondary);
}

.mask-actions {
  display: flex;
  justify-content: center;
}

@media (max-width: 768px) {
  .user-edit-container {
    padding: 16px;
  }

  .config-card :deep(.ant-card-body) {
    padding: 20px;
  }
}
</style>
