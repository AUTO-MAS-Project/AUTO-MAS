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

    <!-- 原生 GUI 会话遮罩（配置会话 / 查看会话，公用组件对齐 ok-nte） -->
    <GuiSessionMask
      :open="showOkwwConfigMask"
      :icon="SettingOutlined"
      :title="t('edit.okWwSetupProgress')"
      :description="`${t('edit.finishSetupOkWw')}\n${t('edit.clickSaveSettingsWhen')}`"
    >
      <template #actions>
        <a-button v-if="okwwTaskId" type="primary" size="large" @click="handleSaveOkwwConfig">
          {{ t('edit.saveSettings') }}
        </a-button>
      </template>
    </GuiSessionMask>
    <GuiSessionMask
      :open="showOkwwViewMask"
      :icon="EyeOutlined"
      :title="t('edit.okwwViewingTitle')"
      :description="`${t('edit.okwwViewingDesc')}\n${t('edit.okwwViewingDesc2')}`"
    >
      <template #actions>
        <a-button
          v-if="okwwTaskId"
          type="primary"
          size="large"
          :loading="stoppingOkwwConfig"
          @click="handleCloseOkwwView"
        >
          {{ t('edit.okwwViewClose') }}
        </a-button>
      </template>
    </GuiSessionMask>

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
                  :alert-message="t('edit.configSourceHintBase')"
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
                      <a-tooltip mouse-enter-delay="0.5" :title="t('edit.collectsKeyMomentsFrom')">
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
              <div class="section-header-actions">
                <a-button size="small" @click="openRestoreModal">
                  <template #icon><HistoryOutlined /></template>
                  {{ t('edit.configRestoreTitle') }}
                </a-button>
              </div>
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

    <!-- ══ 配置恢复（通用组件：MAS 用户配置在前、ok-ww 原生配置在后）══ -->
    <ConfigRestoreSection
      v-model:open="restoreOpen"
      :script-name="OKWW_DISPLAY_NAME"
      :targets="restoreTargets"
      :api="restoreApi"
      :script-desc="t('edit.okwwConfigRestoreScriptDesc')"
      :on-restored="handleRestored"
      :on-detail="handleRestoreView"
    >
      <!-- ok-ww 备份摘要为文件集结构，用插槽完全接管预览区 -->
      <template #preview="{ raw }">
        <a-empty
          v-if="!previewFiles(raw).length"
          :description="t('edit.configRestorePreviewEmpty')"
        />
        <div v-else>
          <template v-for="f in previewFiles(raw)" :key="f.name">
            <h4 class="okww-preview-title">{{ f.label }}</h4>
            <a-descriptions :column="1" size="small" bordered class="okww-preview-box">
              <a-descriptions-item v-for="row in f.summary" :key="row.key" :label="row.key">
                {{ row.value }}
              </a-descriptions-item>
            </a-descriptions>
          </template>
        </div>
      </template>
    </ConfigRestoreSection>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, h, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import {
  EyeOutlined,
  HistoryOutlined,
  QuestionCircleOutlined,
  SettingOutlined,
} from '@ant-design/icons-vue'
import { Service, type OkwwUserConfig } from '@/api'
import { useUserApi } from '@/composables/useUserApi'
import { useScriptApi } from '@/composables/useScriptApi'
import { useOkwwGuiSession } from '@/composables/useOkwwGuiSession'
import { useSaveQueue } from '@/composables/useSaveQueue'
import UserEditHeader from '@/components/UserEditHeader.vue'
import ExtraScriptSection from '@/components/ExtraScriptSection.vue'
import UserNotifyConfig from '@/components/UserNotifyConfig.vue'
import GuiSessionMask from '@/components/GuiSessionMask.vue'
import ConfigRestoreSection from '@/views/EditView/User/components/ConfigRestoreSection.vue'
import GeneralConfigModeSelector from './GeneralConfigModeSelector.vue'

const { t } = useI18n()

const logger = window.electronAPI.getLogger('ok-ww用户编辑')
const route = useRoute()
const router = useRouter()
const { addUser, getUsers, updateUser, error: userApiError, addUserErrorCode } = useUserApi()
const { getScript } = useScriptApi()
const {
  okwwConfigLoading,
  okwwTaskId,
  showOkwwConfigMask,
  showOkwwViewMask,
  stoppingOkwwConfig,
  startSession,
  saveSession,
  stopSession,
} = useOkwwGuiSession()

const scriptId = route.params.scriptId as string
const userId = ref((route.params.userId as string) || '')
const isEdit = ref(!!userId.value)
const scriptName = ref('ok-ww脚本')

const pageLoading = ref(true)
const isInitializing = ref(true)
// 保存串行队列：连续改动按序写回，不再被布尔互斥丢掉
const { isSaving, enqueue } = useSaveQueue()

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

const handleCancel = async () => {
  await stopSession()
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
  if (isInitializing.value || !userId.value) return

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

  await enqueue(async () => {
    try {
      await updateUser(scriptId, userId.value, patch)
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
    }
  }, key)
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
  await startSession(userId.value)
}

const handleSaveOkwwConfig = () => {
  void saveSession()
}

const handleCloseOkwwView = () => {
  void stopSession()
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

// ══ 配置恢复（通用组件 props 供给：双目标 MAS 在前脚本在后）══
// 专项统一名（文案参数化用）：ok-ww 统一叫「ok-ww」
const OKWW_DISPLAY_NAME = 'ok-ww'
const restoreOpen = ref(false)

// 目标池顺序 = segmented 展示顺序：MAS 用户配置（在前）、ok-ww 原生配置（在后）
const restoreTargets: Array<{ key: string; kind: 'user' | 'script' }> = [
  { key: 'mas', kind: 'user' },
  { key: 'native', kind: 'script' },
]

// 组件调用后端：通用 /backup/* 端点（脚本/用户上下文在此闭包捕获）
const restoreApi = {
  list: async (target: string) =>
    Service.listConfigBackupsApiApiScriptsBackupListGet(scriptId, userId.value, target),
  preview: async (target: string, time: string) =>
    Service.getConfigBackupPreviewApiApiScriptsBackupPreviewGet(
      scriptId,
      userId.value,
      time,
      target
    ),
  restore: async (target: string, time: string) =>
    Service.restoreConfigBackupApiApiScriptsBackupRestorePost({
      scriptId,
      userId: userId.value,
      time,
      target,
    }),
  readFile: async (target: string, time: string, path: string) =>
    Service.getConfigBackupFileApiApiScriptsBackupFileGet(
      scriptId,
      userId.value,
      time,
      target,
      path
    ),
}

const openRestoreModal = () => {
  restoreOpen.value = true
}

// 预览响应原文（unknown）收敛为文件集视图：泛用组件的 raw 插槽不带专项类型
interface OkwwPreviewFileView {
  name: string
  label: string
  summary: Array<{ key: string; value: string }>
}
const previewFiles = (raw: unknown): OkwwPreviewFileView[] =>
  (raw as { fileCards?: OkwwPreviewFileView[] } | null)?.fileCards ?? []

// 一键恢复成功：mas 恢复含快速配置覆盖层字段回填，重拉表单——否则旧表单
// 值在下次保存时会静默覆盖回滚结果；native 恢复不影响本页表单
const handleRestored = async (target: string) => {
  restoreOpen.value = false
  if (target === 'mas') {
    await loadUser()
  }
}

// 「查看详细配置」语义（对齐一条龙）：恢复该时点 + 拉起查看会话预览。
// 弹窗文案必须显式区分——该按钮极易被误以为只读，实际会真覆盖当前配置。
// mas 备份：恢复到 MAS 目录后启动查看会话（下发为查看的必经复制，GUI 所见
// 即备份）；原生备份：恢复到 ok-ww 本体后启动脚本级查看会话（跳过下发，
// 原生目录即备份）。查看会话结束不回写配置，原生现场由任务前快照还原。
const handleRestoreView = (target: string, item: { time: string }) => {
  Modal.confirm({
    title: t('edit.configRestoreDetailView'),
    content: h(
      'p',
      { style: { color: 'var(--ant-color-error)', margin: 0 } },
      t('edit.configRestoreDetailConfirm', { script: OKWW_DISPLAY_NAME })
    ),
    okText: t('edit.configRestoreConfirmOk'),
    cancelText: t('edit.cancel'),
    onOk: async () => {
      try {
        const resp = await Service.restoreConfigBackupApiApiScriptsBackupRestorePost({
          scriptId,
          userId: userId.value,
          time: item.time,
          target,
        })
        // 后端失败走 HTTP 200 + body code=400，须显式检查返回体：备份不存在/
        // 路径未设置等抛错若被吞掉，会照常关弹窗并打开查看会话
        if (resp.code !== 200) {
          throw new Error(resp.message || t('edit.configRestoreFailed'))
        }
        restoreOpen.value = false
        if (target === 'mas') {
          await startSession(userId.value, true)
        } else {
          await startSession(scriptId, true)
        }
      } catch (e) {
        message.error(e instanceof Error ? e.message : t('edit.configRestoreFailed'))
      }
    },
  })
}

// 编辑会话归档（进入/退出时机，指纹去重）：与运行/会话下发前的双池归档
// （AutoProxy/ScriptConfig 下发处）配合——进入归档原生配置当前状态（MAS
// 触碰前原始态），退出归档 MAS 配置终态（编辑会话包络）
const ensureOkwwBackup = async (target: 'mas' | 'native') => {
  if (!userId.value) return
  try {
    await Service.ensureConfigBackupApiApiScriptsBackupEnsurePost({
      scriptId,
      userId: userId.value,
      target,
    })
  } catch (e) {
    logger.error(e instanceof Error ? e.message : String(e))
  }
}

onMounted(async () => {
  if (await loadScriptInfo()) {
    await loadUser()
    // 进入编辑页：归档 ok-ww 原生配置当前状态（MAS 触碰前的原始态）
    await ensureOkwwBackup('native')
  }
})

onUnmounted(() => {
  // 退出编辑页：归档 MAS 配置终态（编辑会话包络），并结束未关闭的会话
  void ensureOkwwBackup('mas')
  void stopSession()
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
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.section-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
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

/* 配置预览：逐文件的摘要标题与摘要表 */
.okww-preview-title {
  margin: 14px 0 6px;
  font-size: 14px;
  font-weight: 600;
}

.okww-preview-title:first-child {
  margin-top: 0;
}

.okww-preview-box {
  margin-bottom: 4px;
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
