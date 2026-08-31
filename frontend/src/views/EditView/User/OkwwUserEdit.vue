<template>
  <div class="user-edit-container">
    <UserEditHeader
      :script-id="scriptId"
      :script-name="scriptName"
      :is-edit="isEdit"
      script-edit-segment="okww"
      config-label="配置 ok-ww"
      :config-loading="okwwConfigLoading"
      :config-active="showOkwwConfigMask"
      :config-disabled="pageLoading || !userId"
      @config="handleOkwwConfig"
      @cancel="handleCancel"
    />

    <teleport to="body">
      <div v-if="showOkwwConfigMask" class="okww-config-mask">
        <div class="mask-content">
          <div class="mask-icon">
            <SettingOutlined :style="{ fontSize: '48px', color: 'var(--ant-color-primary)' }" />
          </div>
          <h2 class="mask-title">{{ t('edit.okWwSetupProgress') }}</h2>
          <p class="mask-description">
            {{ t('edit.finishSetupOkWw') }}
            <br />
            {{ t('edit.clickSaveSettingsWhen') }}
          </p>
          <div class="mask-actions">
            <a-button v-if="okwwTaskId" type="primary" size="large" @click="handleSaveOkwwConfig">
              {{ t('edit.saveSettings') }}
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
              <h3>{{ t('edit.basicInfo') }}</h3>
            </div>

            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      {{ t('edit.username') }}
                      <a-tooltip :title="t('edit.nameUsedTellUsers')">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-input
                    v-model:value="formData.userName"
                    :placeholder="t('edit.enterUsername')"
                    size="large"
                    @blur="saveField('Info.Name', formData.userName)"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      {{ t('edit.enabled') }}
                      <a-tooltip :title="t('edit.whetherThisUserEnabled')">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-select
                    v-model:value="formData.Info.Status"
                    size="large"
                    @change="saveField('Info.Status', formData.Info.Status)"
                  >
                    <a-select-option :value="true">{{ t('edit.yes') }}</a-select-option>
                    <a-select-option :value="false">{{ t('edit.no') }}</a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
            </a-row>

            <a-row :gutter="24">
              <a-col :span="24">
                <GeneralConfigModeSelector
                  :model-value="formData.Info.Mode"
                  :options="okwwConfigModeOptions"
                  :disabled="pageLoading"
                  :saving="isSaving"
                  alert-message="脚本使用脚本级共享配置，用户使用当前用户独立配置；直控直接使用 Okww 原有配置。快速配置为独立覆盖层，仅覆盖本页暴露的高频任务字段。"
                  @change="handleConfigModeChange"
                />
              </a-col>
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      {{ t('edit.enableQuickConfiguration') }}
                      <a-tooltip :title="t('edit.overridesCurrentScriptConfiguration')">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-select
                    v-model:value="formData.Info.IfQuickConfig"
                    size="large"
                    :options="quickConfigOptions"
                    @change="saveField('Info.IfQuickConfig', formData.Info.IfQuickConfig)"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      {{ t('edit.collectNodeDetails') }}
                      <a-tooltip
                        mouse-enter-delay="0.5"
                        :title="t('edit.collectsKeyMomentsFrom')"
                      >
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-select
                    v-model:value="formData.Notify.PushLogMode"
                    size="large"
                    class="modern-select"
                    :options="pushLogModeOptions"
                    @change="saveField('Notify.PushLogMode', formData.Notify.PushLogMode)"
                  />
                </a-form-item>
              </a-col>
            </a-row>

            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      {{ t('edit.account') }}
                      <a-tooltip :title="t('edit.usedSwitchAccountsLeave')">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-input
                    v-model:value="formData.Info.Id"
                    :placeholder="t('edit.enterAccount')"
                    size="large"
                    @blur="saveField('Info.Id', formData.Info.Id)"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      {{ t('edit.gameResource') }}
                      <a-tooltip :title="t('edit.pickGameResourceThis')">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-select
                    v-model:value="formData.Info.Resource"
                    :placeholder="t('edit.pickResource')"
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
                      {{ t('edit.daysLeft') }}
                      <a-tooltip :title="t('edit.daysLeftAccount1')">
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
                  {{ t('edit.note') }}
                  <a-tooltip :title="t('edit.addNoteAboutThis')">
                    <QuestionCircleOutlined class="help-icon" />
                  </a-tooltip>
                </span>
              </template>
              <a-textarea
                v-model:value="formData.Info.Notes"
                :placeholder="t('edit.enterNote')"
                :rows="4"
                @blur="saveField('Info.Notes', formData.Info.Notes)"
              />
            </a-form-item>
          </div>
        </a-form>
      </a-card>

      <a-card v-if="formData.Info.IfQuickConfig" class="config-card" style="margin-top: 24px">
        <a-form :model="formData" layout="vertical" class="config-form">
          <div class="form-section">
            <div class="section-header">
              <h3>{{ t('edit.taskConfiguration') }}</h3>
            </div>

            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      {{ t('edit.startTaskTN') }}
                      <a-tooltip :title="t('edit.taskNumbersMatchOk2')">
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
                      {{ t('edit.currentLaunchArguments') }}
                      <a-tooltip :title="t('edit.argumentsGeneratedFromTask')">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </span>
                  </template>
                  <a-input :value="currentStartupArguments" size="large" readonly />
                </a-form-item>
              </a-col>
            </a-row>

            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item :label="t('edit.spendSanityFarm')">
                  <a-select
                    v-model:value="formData.Task.WhichToFarm"
                    size="large"
                    :options="farmOptions"
                    @change="saveTaskConfig"
                  />
                </a-form-item>
              </a-col>
              <a-col v-if="formData.Task.WhichToFarm === 'Tacet Suppression'" :span="12">
                <a-form-item :label="t('edit.sonanceCasketNumberF2')">
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
                <a-form-item :label="t('edit.echoDomainNumberF2')">
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
                <a-form-item :label="t('edit.simulatedUniverseMaterials')">
                  <a-select
                    v-model:value="formData.Task.MaterialSelection"
                    size="large"
                    :options="materialOptions"
                    @change="saveTaskConfig"
                  />
                </a-form-item>
              </a-col>
            </a-row>

            <a-form-item :label="t('edit.useNightmareNestDaily')">
              <a-switch
                v-model:checked="formData.Task.FarmNightmareNestForDailyEcho"
                @change="saveTaskConfig"
              />
            </a-form-item>

            <a-form-item :label="t('edit.extraTasksThatRun')">
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
          <ExtraScriptSection
            v-model:form-data="formData"
            :loading="pageLoading"
            @save="saveField"
          />
        </a-form>
      </a-card>

      <a-card class="config-card" style="margin-top: 24px">
        <a-form :model="formData" layout="vertical" class="config-form">
          <UserNotifyConfig
            v-model="formData.Notify"
            :loading="pageLoading"
            :script-id="scriptId"
            :user-id="userId"
            @save="saveField"
          />
        </a-form>
      </a-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import { QuestionCircleOutlined, SettingOutlined } from '@ant-design/icons-vue'
import { Service, type OkwwUserConfig } from '@/api'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import { useUserApi } from '@/composables/useUserApi'
import { useScriptApi } from '@/composables/useScriptApi'
import { useWebSocket } from '@/composables/useWebSocket'
import {
  WS_TASK_COMPLETED,
  WS_TASK_NOTICE,
  type WSTaskNoticeData,
} from '@/services/websocket/types'
import UserEditHeader from '@/components/UserEditHeader.vue'
import ExtraScriptSection from '@/components/ExtraScriptSection.vue'
import UserNotifyConfig from '@/components/UserNotifyConfig.vue'
import GeneralConfigModeSelector from './GeneralConfigModeSelector.vue'

const { t } = useI18n()

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
const okwwSubscriptionIds = ref<string[]>([])
const okwwTaskId = ref<string | null>(null)
const showOkwwConfigMask = ref(false)
const stoppingOkwwConfig = ref(false)
let okwwConfigTimeout: number | null = null

const resourceOptions = [
  { label: '官服（China）', value: '官服' },
  { label: '国际服（Global）', value: '国际服' },
]

const quickConfigOptions = [
  { label: t('edit.enabled3'), value: true },
  { label: t('edit.off'), value: false },
]

// 节点详情推送模式（value 为后端 Notify.PushLogMode 取值，驱动逻辑需保持原样；label 走词表）
const pushLogModeOptions = [
  { label: t('edit.pushLogModeOff'), value: '关闭' },
  { label: t('edit.pushLogModeList'), value: '逐条' },
  { label: t('edit.pushLogModeSummary'), value: '汇总' },
]

const okwwConfigModeOptions: Array<{
  label: string
  value: '脚本' | '用户' | '直控'
  title: string
  description: string
  icon: 'file' | 'database' | 'setting'
}> = [
  {
    label: t('edit.script'),
    value: '脚本',
    title: t('edit.script'),
    description: t('edit.useSharedScriptLevel'),
    icon: 'file',
  },
  {
    label: t('edit.user'),
    value: '用户',
    title: t('edit.user'),
    description: t('edit.useThisUserS'),
    icon: 'database',
  },
  {
    label: t('edit.directControl'),
    value: '直控',
    title: t('edit.directControl'),
    description: t('edit.useExistingOkwwConfiguration'),
    icon: 'setting',
  },
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

type OkwwNotifyForm = FormSection<NonNullable<OkwwUserConfig['Notify']>>

type OkwwUserFormData = {
  userName: string
  Info: FormSection<NonNullable<OkwwUserConfig['Info']>>
  Task: FormSection<NonNullable<OkwwUserConfig['Task']>>
  Notify: OkwwNotifyForm
  Data: FormSection<NonNullable<OkwwUserConfig['Data']>>
}

const getDefaultUserData = (): Omit<OkwwUserFormData, 'userName'> => ({
  Info: {
    Name: '',
    Status: true,
    Id: '',
    IfUseMasConfig: true,
    Mode: '脚本',
    IfQuickConfig: true,
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
    PushLogMode: '汇总',
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

const handleConfigModeChange = async (value: boolean | string) => {
  if (typeof value !== 'string' || !['脚本', '用户', '直控'].includes(value)) return
  formData.Info.Mode = value as '脚本' | '用户' | '直控'
  await saveField('Info.Mode', formData.Info.Mode)
}

const clearOkwwConfigSession = () => {
  for (const subscriptionId of okwwSubscriptionIds.value) {
    unsubscribe(subscriptionId)
  }
  okwwSubscriptionIds.value = []
  okwwTaskId.value = null
  showOkwwConfigMask.value = false
  if (okwwConfigTimeout) {
    window.clearTimeout(okwwConfigTimeout)
    okwwConfigTimeout = null
  }
}

const stopOkwwConfigSession = async (keepOnFailure = false): Promise<boolean> => {
  const taskId = okwwTaskId.value
  if (!taskId) {
    clearOkwwConfigSession()
    return true
  }
  if (stoppingOkwwConfig.value) return false

  stoppingOkwwConfig.value = true
  try {
    const response = await Service.stopTaskApiDispatchStopPost({ taskId })
    if (response.code !== 200) {
      throw new Error(response.message || '停止 ok-ww 设置失败')
    }
    clearOkwwConfigSession()
    return true
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
    if (keepOnFailure) return false
    clearOkwwConfigSession()
    return false
  } finally {
    stoppingOkwwConfig.value = false
  }
}

const handleCancel = async () => {
  await stopOkwwConfigSession()
  await router.push('/scripts')
}

const createUserImmediately = async (): Promise<boolean> => {
  const resp = await addUser(scriptId, { showError: false })
  if (!resp?.userId) {
    const errorMessage = userApiError.value || '创建用户失败'
    if (addUserErrorCode.value === 409) {
      Modal.warning({
        title: t('edit.noOkWwSettings'),
        content: t('edit.currentOkWwInstall'),
        okText: t('edit.backScriptList'),
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
    okwwTaskId.value = response.taskId
    const subscriptionIds = [
      subscribe({ id: response.taskId, type: WS_TASK_NOTICE }, wsMessage => {
        const data = wsMessage.data as unknown as WSTaskNoticeData
        if (data.level === 'error') {
          message.error(t('edit.okWwSetupFailed', { p0: data.message }))
          void stopOkwwConfigSession()
        }
      }),
      subscribe({ id: response.taskId, type: WS_TASK_COMPLETED }, () => {
        clearOkwwConfigSession()
      }),
    ]
    okwwSubscriptionIds.value = subscriptionIds
    const configTarget =
      formData.Info.Mode === '直控'
        ? '脚本直控'
        : formData.Info.Mode === '脚本'
          ? '脚本共享'
          : '当前用户'
    message.success(t('edit.openedOkWwSettings', { p0: configTarget }))
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
  if (!okwwTaskId.value) return
  if (await stopOkwwConfigSession(true)) {
    message.success(t('edit.okWwSettingsSaved'))
  } else {
    message.error(t('edit.couldNotSaveOk2'))
  }
}

const loadScriptInfo = async (): Promise<boolean> => {
  const detail = await getScript(scriptId)
  if (!detail || detail.type !== 'Okww') {
    message.error(t('edit.okWwScriptDoes'))
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
    message.error(t('edit.couldNotLoadUser'))
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

onUnmounted(() => {
  void stopOkwwConfigSession()
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

.config-card :deep(.ant-card-body) {
  padding: 32px;
}

.section-header {
  border-bottom: 1px solid var(--ant-color-border-secondary);
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

  .config-card :deep(.ant-card-body) {
    padding: 20px;
  }
}
</style>
