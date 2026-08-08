<template>
  <div class="user-edit-container">
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
          v-if="!showOkwwConfigMask"
          type="primary"
          ghost
          size="large"
          :loading="okwwConfigLoading"
          :disabled="pageLoading || !userId"
          @click="handleOkwwConfig"
        >
          <template #icon>
            <SettingOutlined />
          </template>
          配置 ok-ww
        </a-button>
        <a-button v-else type="default" size="large" disabled class="configuring-button">
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
      <div v-if="showOkwwConfigMask" class="okww-config-mask">
        <div class="mask-content">
          <div class="mask-icon">
            <SettingOutlined :style="{ fontSize: '48px', color: 'var(--ant-color-primary)' }" />
          </div>
          <h2 class="mask-title">正在进行 ok-ww 设置</h2>
          <p class="mask-description">
            请在 ok-ww 界面完成设置。
            <br />
            完成后点击“保存设置”结束本次会话。
          </p>
          <div class="mask-actions">
            <a-button
              v-if="okwwWebsocketId"
              type="primary"
              size="large"
              @click="handleSaveOkwwConfig"
            >
              保存设置
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
                    class="modern-input"
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
                    class="modern-select"
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
                <a-form-item label="配置模式">
                  <a-select
                    v-model:value="formData.Info.Mode"
                    size="large"
                    class="modern-select"
                    @change="saveField('Info.Mode', formData.Info.Mode)"
                  >
                    <a-select-option value="简洁">简洁</a-select-option>
                    <a-select-option value="详细">详细</a-select-option>
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
                    class="modern-input"
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
                    class="modern-input"
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
                    class="modern-select"
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
                class="modern-input"
                @blur="saveField('Info.Notes', formData.Info.Notes)"
              />
            </a-form-item>
          </div>
        </a-form>
      </a-card>

      <a-card class="config-card" style="margin-top: 24px">
        <a-form :model="formData" layout="vertical" class="config-form">
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
                  <a-select
                    v-model:value="formData.Task.TaskIndex"
                    size="large"
                    @change="handleTaskIndexChange"
                  >
                    <a-select-option
                      v-for="item in okwwTaskOptions"
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
                    size="large"
                    readonly
                    class="modern-input"
                  />
                </a-form-item>
              </a-col>
            </a-row>

            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item label="消耗体力刷取">
                  <a-select
                    v-model:value="formData.Task.WhichToFarm"
                    size="large"
                    :options="farmOptions"
                    @change="saveTaskConfig"
                  />
                </a-form-item>
              </a-col>
              <a-col v-if="formData.Task.WhichToFarm === 'Tacet Suppression'" :span="12">
                <a-form-item label="F2 列表中的无音区序号">
                  <a-input-number
                    v-model:value="formData.Task.WhichTacetSuppressionToFarm"
                    :min="1"
                    :max="99"
                    style="width: 100%"
                    size="large"
                    @blur="saveTaskConfig"
                  />
                </a-form-item>
              </a-col>
              <a-col v-else-if="formData.Task.WhichToFarm === 'Forgery Challenge'" :span="12">
                <a-form-item label="F2 列表中的凝素领域序号">
                  <a-input-number
                    v-model:value="formData.Task.WhichForgeryChallengeToFarm"
                    :min="1"
                    :max="99"
                    style="width: 100%"
                    size="large"
                    @blur="saveTaskConfig"
                  />
                </a-form-item>
              </a-col>
              <a-col v-else :span="12">
                <a-form-item label="模拟领域材料">
                  <a-select
                    v-model:value="formData.Task.MaterialSelection"
                    size="large"
                    :options="materialOptions"
                    @change="saveTaskConfig"
                  />
                </a-form-item>
              </a-col>
            </a-row>

            <a-form-item label="需要时使用梦魇巢穴完成日常声骸">
              <a-switch
                v-model:checked="formData.Task.FarmNightmareNestForDailyEcho"
                @change="saveTaskConfig"
              />
            </a-form-item>

            <a-form-item label="每日任务后运行的附加任务">
              <a-checkbox-group
                v-model:value="formData.Task.AdditionalTasks"
                :options="additionalTaskOptions"
                @change="saveTaskConfig"
              />
            </a-form-item>
          </div>
        </a-form>
      </a-card>

      <a-card class="config-card" style="margin-top: 24px">
        <a-form :model="formData" layout="vertical" class="config-form">
          <ExtraScriptSection :form-data="formData" :loading="pageLoading" @save="saveField" />
        </a-form>
      </a-card>

      <a-card class="config-card" style="margin-top: 24px">
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
import { message, Modal } from 'ant-design-vue'
import { ArrowLeftOutlined, QuestionCircleOutlined, SettingOutlined } from '@ant-design/icons-vue'
import { Service, type OkwwUserConfig } from '@/api'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import { useUserApi } from '@/composables/useUserApi'
import { useScriptApi } from '@/composables/useScriptApi'
import { useWebSocket } from '@/composables/useWebSocket'
import WebhookManager from '@/components/WebhookManager.vue'
import ExtraScriptSection from '@/components/ExtraScriptSection.vue'

const logger = window.electronAPI.getLogger('ok-ww用户编辑')
const route = useRoute()
const router = useRouter()
const { addUser, getUsers, updateUser, error: userApiError, addUserErrorCode } = useUserApi()
const { getScript } = useScriptApi()
const { subscribe, unsubscribe } = useWebSocket()

const scriptId = route.params.scriptId as string
const userId = ref((route.params.userId as string) || '')
const isEdit = ref(!!userId.value)
const scriptName = ref('ok-ww脚本')

const pageLoading = ref(true)
const isInitializing = ref(true)
const isSaving = ref(false)
const okwwConfigLoading = ref(false)
const okwwSubscriptionId = ref<string | null>(null)
const okwwWebsocketId = ref<string | null>(null)
const showOkwwConfigMask = ref(false)
let okwwConfigTimeout: number | null = null

const resourceOptions = [
  { label: '官服（China）', value: '官服' },
  { label: '国际服（Global）', value: '国际服' },
]

const okwwTaskOptions = [
  { label: '1 - DailyTask（日常）', value: 1 },
  { label: '7 - MultiAccountDailyTask（多账号日常）', value: 7 },
]

const farmOptions = [
  { label: '无音区', value: 'Tacet Suppression' },
  { label: '凝素领域', value: 'Forgery Challenge' },
  { label: '模拟领域', value: 'Simulation Challenge' },
]

const materialOptions = [
  { label: '共鸣者经验', value: 'Resonator EXP' },
  { label: '武器经验', value: 'Weapon EXP' },
  { label: '贝币', value: 'Shell Credit' },
]

const additionalTaskOptions = [
  { label: '检查每周乐园', value: 'Check Weekly Garden' },
  { label: '自动刷所有梦魇巢穴', value: 'Auto Farm all Nightmare Nest' },
  { label: '已弃置声骸超过 1000 时融合', value: 'Merge Echo If discarded > 1000' },
  { label: '传送并刷取 4C 声骸', value: 'Teleport and Farm 4C Echo' },
]

type FormSection<T> = { [K in keyof T]-?: NonNullable<T[K]> }

type OkwwUserFormData = {
  userName: string
  Info: FormSection<NonNullable<OkwwUserConfig['Info']>>
  Task: FormSection<NonNullable<OkwwUserConfig['Task']>>
  Notify: FormSection<NonNullable<OkwwUserConfig['Notify']>>
  Data: FormSection<NonNullable<OkwwUserConfig['Data']>>
}

const getDefaultUserData = (): Omit<OkwwUserFormData, 'userName'> => ({
  Info: {
    Name: '',
    Status: true,
    Id: '',
    Password: '',
    Mode: '简洁',
    Resource: '官服',
    RemainedDay: -1,
    IfScriptBeforeTask: false,
    ScriptBeforeTask: '',
    IfScriptAfterTask: false,
    ScriptAfterTask: '',
    Notes: '',
    Tag: '',
  },
  Task: {
    TaskIndex: 1,
    WhichToFarm: 'Tacet Suppression',
    WhichTacetSuppressionToFarm: 1,
    WhichForgeryChallengeToFarm: 1,
    MaterialSelection: 'Shell Credit',
    FarmNightmareNestForDailyEcho: true,
    AdditionalTasks: ['Check Weekly Garden'],
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

const formData = reactive<OkwwUserFormData>({
  userName: '',
  ...getDefaultUserData(),
})

const currentStartupArguments = computed(() => `-t ${formData.Task.TaskIndex || 1} -e`)

const clearOkwwConfigSession = () => {
  if (okwwSubscriptionId.value) {
    unsubscribe(okwwSubscriptionId.value)
    okwwSubscriptionId.value = null
  }
  okwwWebsocketId.value = null
  showOkwwConfigMask.value = false
  if (okwwConfigTimeout) {
    window.clearTimeout(okwwConfigTimeout)
    okwwConfigTimeout = null
  }
}

const handleCancel = () => {
  clearOkwwConfigSession()
  router.push('/scripts')
}

const createUserImmediately = async (): Promise<boolean> => {
  const resp = await addUser(scriptId, { showError: false })
  if (!resp?.userId) {
    const errorMessage = userApiError.value || '创建用户失败'
    if (addUserErrorCode.value === 409) {
      Modal.warning({
        title: '尚未生成 ok-ww 设置',
        content:
          '当前 ok-ww 安装中没有可用的设置目录。首次下载后，请先返回脚本列表点击“配置 ok-ww”，在本体中保存一次设置，再重新添加用户。',
        okText: '返回脚本列表',
        onOk: handleCancel,
      })
      return false
    }
    message.error(errorMessage)
    handleCancel()
    return false
  }
  userId.value = resp.userId
  isEdit.value = true
  await router.replace({
    name: 'OkwwUserEdit',
    params: { scriptId, userId: userId.value },
  })
  return true
}

const saveField = async (key: string, value: unknown) => {
  if (isInitializing.value || isSaving.value || !userId.value) return

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

    await updateUser(scriptId, userId.value, patch)
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
  } finally {
    isSaving.value = false
  }
}

const saveTaskConfig = async () => {
  if (isInitializing.value || !userId.value) return
  await updateUser(scriptId, userId.value, {
    Task: {
      TaskIndex: formData.Task.TaskIndex,
      WhichToFarm: formData.Task.WhichToFarm,
      WhichTacetSuppressionToFarm: formData.Task.WhichTacetSuppressionToFarm,
      WhichForgeryChallengeToFarm: formData.Task.WhichForgeryChallengeToFarm,
      MaterialSelection: formData.Task.MaterialSelection,
      FarmNightmareNestForDailyEcho: formData.Task.FarmNightmareNestForDailyEcho,
      AdditionalTasks: formData.Task.AdditionalTasks,
    },
  })
}

const handleTaskIndexChange = async (value: 1 | 7) => {
  formData.Task.TaskIndex = value
  try {
    await saveTaskConfig()
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
  }
}

const handleOkwwConfig = async () => {
  if (!userId.value) return
  try {
    okwwConfigLoading.value = true
    const response = await Service.addTaskApiDispatchStartPost({
      taskId: userId.value,
      mode: TaskCreateIn.mode.SCRIPT_CONFIG,
    })
    if (response.code !== 200 || !response.taskId) {
      throw new Error(response.message || '启动 ok-ww 设置失败')
    }

    showOkwwConfigMask.value = true
    const subscriptionId = subscribe({ id: response.taskId }, (wsMessage: any) => {
      if (wsMessage.type === 'error') {
        message.error(`ok-ww 设置连接失败: ${String(wsMessage.data)}`)
        clearOkwwConfigSession()
        return
      }
      if (wsMessage.type === 'Info' && wsMessage.data?.Error) {
        message.error(`ok-ww 设置失败: ${String(wsMessage.data.Error)}`)
        return
      }
      if (wsMessage.type === 'Signal' && wsMessage.data?.Accomplish !== undefined) {
        clearOkwwConfigSession()
      }
    })
    okwwSubscriptionId.value = subscriptionId
    okwwWebsocketId.value = response.taskId
    message.success(`已打开${formData.Info.Mode === '简洁' ? '共享' : '当前用户'}的 ok-ww 设置`)
    okwwConfigTimeout = window.setTimeout(handleSaveOkwwConfig, 30 * 60 * 1000)
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
    message.error(e instanceof Error ? e.message : '启动 ok-ww 设置失败')
    clearOkwwConfigSession()
  } finally {
    okwwConfigLoading.value = false
  }
}

const handleSaveOkwwConfig = async () => {
  if (!okwwWebsocketId.value) return
  try {
    const response = await Service.stopTaskApiDispatchStopPost({
      taskId: okwwWebsocketId.value,
    })
    if (response.code !== 200) {
      throw new Error(response.message || '保存 ok-ww 设置失败')
    }
    clearOkwwConfigSession()
    message.success('ok-ww 设置已保存')
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
    message.error(e instanceof Error ? e.message : '保存 ok-ww 设置失败')
  }
}

const loadScriptInfo = async (): Promise<boolean> => {
  const detail = await getScript(scriptId)
  if (!detail || detail.type !== 'Okww') {
    message.error('ok-ww 脚本不存在或加载失败')
    handleCancel()
    return false
  }

  scriptName.value = detail.name
  return true
}

const loadUser = async () => {
  pageLoading.value = true
  try {
    if (!userId.value) {
      if (!(await createUserImmediately())) return
    }
    const resp = await getUsers(scriptId, userId.value)
    const userIndex = resp?.index?.find(i => i.uid === userId.value)
    const data = resp?.data?.[userId.value]
    if (!userIndex || !data) {
      throw new Error('用户不存在或加载失败')
    }

    const userData = data as OkwwUserConfig

    Object.assign(formData, {
      Info: { ...getDefaultUserData().Info, ...(userData.Info || {}) },
      Task: { ...getDefaultUserData().Task, ...(userData.Task || {}) },
      Notify: { ...getDefaultUserData().Notify, ...(userData.Notify || {}) },
      Data: { ...getDefaultUserData().Data, ...(userData.Data || {}) },
    })
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
  if (await loadScriptInfo()) {
    await loadUser()
  }
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

.configuring-button {
  color: #52c41a;
  border-color: #52c41a;
}

.user-edit-content {
  max-width: 1200px;
  margin: 0 auto;
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
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.section-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  display: flex;
  align-items: center;
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

.modern-select {
  width: 100%;
}

.okww-config-mask {
  position: fixed;
  inset: 32px 0 0;
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
