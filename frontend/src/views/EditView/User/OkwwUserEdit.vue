<template>
  <div class="user-edit-container">
    <UserEditHeader
      :script-id="scriptId"
      :script-name="scriptName"
      :is-edit="isEdit"
      script-edit-segment="okww"
      :user-id="userId"
      :config-label="t('core.edit.configureOkww')"
      :config-loading="okwwConfigLoading"
      :config-active="showOkwwConfigMask"
      :config-disabled="configActionsDisabled"
      @config="handleOkwwConfig"
      @cancel="handleCancel"
    />

    <!-- 原生 GUI 会话遮罩（配置会话 / 查看会话，公用组件对齐 ok-nte） -->
    <GuiSessionMask
      :open="showOkwwConfigMask"
      :icon="SettingOutlined"
      :title="t('core.edit.okWwSetupProgress')"
      :description="`${t('core.edit.finishSetupOkWw')}\n${t('core.edit.clickSaveSettingsWhen')}`"
    >
      <template #actions>
        <a-button v-if="okwwTaskId" type="primary" size="large" @click="handleSaveOkwwConfig">
          {{ t('core.edit.saveSettings') }}
        </a-button>
      </template>
    </GuiSessionMask>
    <GuiSessionMask
      :open="showOkwwViewMask"
      :icon="EyeOutlined"
      :title="t('core.edit.okwwViewingTitle')"
      :description="`${t('core.edit.okwwViewingDesc')}\n${t('core.edit.okwwViewingDesc2')}`"
    >
      <template #actions>
        <a-button
          v-if="okwwTaskId"
          type="primary"
          size="large"
          :loading="stoppingOkwwConfig"
          @click="handleCloseOkwwView"
        >
          {{ t('core.edit.okwwViewClose') }}
        </a-button>
      </template>
    </GuiSessionMask>

    <ConfigLockPanel :script-id="scriptId" content-class="user-edit-content">
      <a-card class="config-card" :loading="pageLoading">
        <a-form :model="formData" layout="vertical" class="config-form">
          <div class="form-section">
            <div class="section-header">
              <h3>{{ t('core.edit.basicInfo') }}</h3>
            </div>

            <a-row :gutter="24">
              <a-col :span="12">
                <UserNameField
                  v-model="formData.userName"
                  :hint="t('core.edit.nameUsedTellUsers')"
                  :placeholder="t('core.edit.enterUsername')"
                  @save="saveField('Info.Name', formData.userName)"
                />
              </a-col>
              <a-col :span="12">
                <UserStatusField
                  v-model="formData.Info.Status"
                  :hint="t('core.edit.whetherThisUserEnabled')"
                  @save="saveField('Info.Status', formData.Info.Status)"
                />
              </a-col>
            </a-row>

            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <span class="form-label">
                      {{ t('core.edit.collectNodeDetails') }}
                      <a-tooltip
                        mouse-enter-delay="0.5"
                        :title="t('core.edit.collectsKeyMomentsFrom')"
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
                    <FieldLabelWithHint
                      :text="t('core.edit.account')"
                      :hint="t('core.edit.usedSwitchAccountsLeave')"
                      variant="form"
                    />
                  </template>
                  <a-input
                    v-model:value="formData.Info.Id"
                    :placeholder="t('core.edit.enterAccount')"
                    size="large"
                    @blur="saveField('Info.Id', formData.Info.Id)"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <a-form-item>
                  <template #label>
                    <FieldLabelWithHint
                      :text="t('core.edit.gameResource')"
                      :hint="t('core.edit.pickGameResourceThis')"
                      variant="form"
                    />
                  </template>
                  <a-select
                    v-model:value="formData.Info.Resource"
                    :placeholder="t('core.edit.pickResource')"
                    size="large"
                    :options="resourceOptions"
                    @change="saveField('Info.Resource', formData.Info.Resource)"
                  />
                </a-form-item>
              </a-col>
              <a-col :span="12">
                <UserRemainedDayField
                  v-model="formData.Info.RemainedDay"
                  :hint="t('core.edit.daysLeftAccount1')"
                  @save="saveField('Info.RemainedDay', formData.Info.RemainedDay)"
                />
              </a-col>
            </a-row>

            <UserNotesField
              v-model="formData.Info.Notes"
              :hint="t('core.edit.addNoteAboutThis')"
              :placeholder="t('core.edit.enterNote')"
              :rows="4"
              @save="saveField('Info.Notes', formData.Info.Notes)"
            />
          </div>
        </a-form>
      </a-card>

      <!-- 配置文件来源：base 三态 ⊕ overlay 两态，与 MaaEnd / MAA 共用同一套面板 -->
      <a-card class="config-card config-source-card" :loading="pageLoading">
        <a-form :model="formData" layout="vertical" class="config-form">
          <div class="form-section">
            <div class="section-header">
              <h3>{{ t('core.edit.configurationSource') }}</h3>
            </div>
            <a-row :gutter="24">
              <a-col :span="24">
                <GeneralConfigModeSelector
                  :model-value="formData.Info.Base"
                  :options="okwwConfigModeOptions"
                  :disabled="configActionsDisabled"
                  :saving="isSaving"
                  :quick-config="formData.Info.IfQuickConfig"
                  :quick-config-disabled="configActionsDisabled || isInitializing"
                  :alert-message="t('core.edit.configSourceHintBase')"
                  :show-gui-hint="false"
                  @change="handleConfigModeChange"
                  @quick-config-change="handleQuickConfigChange"
                />
              </a-col>
            </a-row>
            <a-row :gutter="24">
              <a-col :span="24" class="config-actions-tail">
                <ConfigActionsSection
                  :base="formData.Info.Base"
                  script-label="ok-ww"
                  :disabled="configActionsDisabled"
                  :config-loading="okwwConfigLoading"
                  :configuring="showOkwwConfigMask"
                  :import-loading="okwwImportLoading"
                  @configure="handleOkwwConfig"
                  @import-config="handleImportOkwwConfig"
                  @script-config="handleScriptConfig"
                />
              </a-col>
            </a-row>
          </div>
        </a-form>
      </a-card>

      <a-flex class="section-header" justify="space-between" align="center" wrap="wrap" gap="small">
        <h3>{{ t('core.edit.taskConfiguration') }}</h3>
        <a-space>
          <a-button size="small" @click="openRestoreModal">
            <template #icon><HistoryOutlined /></template>
            {{ t('core.edit.configRestoreTitle') }}
          </a-button>
        </a-space>
      </a-flex>
      <a-card v-if="formData.Info.IfQuickConfig" class="config-card">
        <a-form :model="formData" layout="vertical" class="config-form">
          <div class="form-section">
            <a-row :gutter="24">
              <a-col :span="24">
                <a-form-item>
                  <template #label>
                    <FieldLabelWithHint
                      :text="t('core.edit.currentLaunchArguments')"
                      :hint="t('core.edit.argumentsGeneratedFromTask')"
                      variant="form"
                    />
                  </template>
                  <a-input :value="currentStartupArguments" size="large" readonly />
                </a-form-item>
              </a-col>
            </a-row>

            <a-row :gutter="24">
              <a-col :span="12">
                <a-form-item :label="t('core.edit.spendSanityFarm')">
                  <a-select
                    v-model:value="formData.Task.WhichToFarm"
                    size="large"
                    :options="farmOptions"
                    @change="saveTaskConfig"
                  />
                </a-form-item>
              </a-col>
              <a-col v-if="formData.Task.WhichToFarm === 'Tacet Suppression'" :span="12">
                <a-form-item :label="t('core.edit.sonanceCasketNumberF2')">
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
                <a-form-item :label="t('core.edit.echoDomainNumberF2')">
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
                <a-form-item :label="t('core.edit.simulatedUniverseMaterials')">
                  <a-select
                    v-model:value="formData.Task.MaterialSelection"
                    size="large"
                    :options="materialOptions"
                    @change="saveTaskConfig"
                  />
                </a-form-item>
              </a-col>
            </a-row>

            <a-form-item :label="t('core.edit.useNightmareNestDaily')">
              <a-switch
                v-model:checked="formData.Task.FarmNightmareNestForDailyEcho"
                @change="saveTaskConfig"
              />
            </a-form-item>

            <a-form-item :label="t('core.edit.extraTasksThatRun')">
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
    </ConfigLockPanel>

    <!-- ══ 配置恢复（通用组件：MAS 用户配置在前、ok-ww 原生配置在后）══ -->
    <ConfigRestoreSection
      v-model:open="restoreOpen"
      :disabled="configLocked"
      :script-name="OKWW_DISPLAY_NAME"
      :targets="restoreTargets"
      :api="restoreApi"
      :script-desc="t('core.edit.okwwConfigRestoreScriptDesc')"
      :on-restored="handleRestored"
      :on-detail="handleRestoreView"
    >
      <!-- ok-ww 备份摘要为文件集结构，用插槽完全接管预览区 -->
      <template #preview="{ raw }">
        <NoData
          v-if="!previewFiles(raw).length"
          :description="t('core.edit.configRestorePreviewEmpty')"
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
import UserNameField from '@/views/EditView/User/components/UserNameField.vue'
import UserNotesField from '@/views/EditView/User/components/UserNotesField.vue'
import UserRemainedDayField from '@/views/EditView/User/components/UserRemainedDayField.vue'
import UserStatusField from '@/views/EditView/User/components/UserStatusField.vue'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import ConfigLockPanel from '@/components/ConfigLockPanel.vue'
import { useScriptConfigLock } from '@/composables/useScriptConfigLock'
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
import type { OkwwUserConfig } from '@/api'
import { useUserApi } from '@/composables/useUserApi'
import { useScriptApi } from '@/composables/useScriptApi'
import { useOkwwGuiSession } from '@/composables/useOkwwGuiSession'
import { useSaveQueue } from '@/composables/useSaveQueue'
import UserEditHeader from '@/components/UserEditHeader.vue'
import ExtraScriptSection from '@/components/ExtraScriptSection.vue'
import UserNotifyConfig from '@/components/UserNotifyConfig.vue'
import GuiSessionMask from '@/components/GuiSessionMask.vue'
import ConfigRestoreSection from '@/views/EditView/User/components/ConfigRestoreSection.vue'
import { buildRestoreConfirm } from '@/utils/configRestoreMode'
import GeneralConfigModeSelector from './GeneralConfigModeSelector.vue'
import ConfigActionsSection from './ConfigActionsSection.vue'
import { useConfigBackupApi } from '@/composables/useConfigBackupApi'

const { t } = useI18n()

const logger = window.electronAPI.getLogger('ok-ww用户编辑')
const route = useRoute()
const router = useRouter()
const { addUser, getUsers, updateUser, error: userApiError, addUserErrorCode } = useUserApi()
const { getScript, importScriptConfigFile, error: scriptApiError } = useScriptApi()
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
const okwwImportLoading = ref(false)

const scriptId = route.params.scriptId as string
const userId = ref((route.params.userId as string) || '')
const isEdit = ref(!!userId.value)
const { configLocked } = useScriptConfigLock(() => scriptId)
const scriptName = ref('ok-ww脚本')

const pageLoading = ref(true)
const isInitializing = ref(true)
// 保存串行队列：连续改动按序写回，不再被布尔互斥丢掉
const { isSaving, enqueue } = useSaveQueue()
const configActionsDisabled = computed(
  () =>
    pageLoading.value ||
    !userId.value ||
    isSaving.value ||
    okwwConfigLoading.value ||
    okwwImportLoading.value ||
    showOkwwConfigMask.value ||
    showOkwwViewMask.value ||
    stoppingOkwwConfig.value ||
    configLocked.value
)

const resourceOptions = [
  { label: '官服（China）', value: '官服' },
  { label: '国际服（Global）', value: '国际服' },
]

// 节点详情推送模式（value 为后端 Notify.PushLogMode 取值，驱动逻辑需保持原样；label 走词表）
const pushLogModeOptions = [
  { label: t('core.edit.pushLogModeOff'), value: '关闭' },
  { label: t('core.edit.pushLogModeList'), value: '逐条' },
  { label: t('core.edit.pushLogModeSummary'), value: '汇总' },
]

const okwwConfigModeOptions: Array<{
  label: string
  value: 'shared' | 'independent' | 'native'
  title: string
  description: string
  icon: 'file' | 'database' | 'setting'
}> = [
  {
    label: t('core.edit.script'),
    value: 'shared',
    title: t('core.edit.script'),
    description: t('core.edit.useSharedScriptLevel'),
    icon: 'file',
  },
  {
    label: t('core.edit.user'),
    value: 'independent',
    title: t('core.edit.user'),
    description: t('core.edit.useThisUserS'),
    icon: 'database',
  },
  {
    label: t('core.edit.directControl'),
    value: 'native',
    title: t('core.edit.directControl'),
    description: t('core.edit.useExistingOkwwConfiguration'),
    icon: 'setting',
  },
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
    Base: 'shared',
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
    LastProxyDate: '2000-01-01T00:00:00+04:00',
    ProxyTimes: 0,
    LastProxyStatus: '未知',
    LastTaskIndex: 0,
  },
})

const formData = reactive<OkwwUserFormData>({
  userName: '',
  ...getDefaultUserData(),
})

// ok-ww 只调度日常任务（-t 1 = DailyTask）；账号切换由 MAS 侧实现
const currentStartupArguments = '-t 1 -e'

const handleConfigModeChange = async (value: boolean | string) => {
  if (configActionsDisabled.value) return
  if (typeof value !== 'string' || !['shared', 'independent', 'native'].includes(value)) return
  const previous = formData.Info.Base
  formData.Info.Base = value as 'shared' | 'independent' | 'native'
  if (!(await saveField('Info.Base', formData.Info.Base))) formData.Info.Base = previous
}

const handleCancel = async () => {
  await stopSession()
  await router.push('/scripts')
}

const createUserImmediately = async (): Promise<boolean> => {
  if (configLocked.value) return false

  const resp = await addUser(scriptId, { showError: false })
  if (!resp?.userId) {
    const errorMessage = userApiError.value || '创建用户失败'
    if (addUserErrorCode.value === 409) {
      Modal.warning({
        title: t('core.edit.noOkWwSettings'),
        content: t('core.edit.currentOkWwInstall'),
        okText: t('core.edit.backScriptList'),
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

  return await enqueue(async () => {
    try {
      return await updateUser(scriptId, userId.value, patch)
    } catch (e) {
      logger.error(e instanceof Error ? e.message : String(e))
    }
  }, key)
}

const handleQuickConfigChange = async (value: boolean) => {
  const previous = formData.Info.IfQuickConfig
  formData.Info.IfQuickConfig = value
  if (!(await saveField('Info.IfQuickConfig', value))) {
    formData.Info.IfQuickConfig = previous
  }
}

const saveTaskConfig = async () => {
  if (isInitializing.value || !userId.value) return
  await enqueue(() =>
    updateUser(scriptId, userId.value, {
      Task: {
        WhichToFarm: formData.Task.WhichToFarm,
        WhichTacetSuppressionToFarm: formData.Task.WhichTacetSuppressionToFarm,
        WhichForgeryChallengeToFarm: formData.Task.WhichForgeryChallengeToFarm,
        MaterialSelection: formData.Task.MaterialSelection,
        FarmNightmareNestForDailyEcho: formData.Task.FarmNightmareNestForDailyEcho,
        AdditionalTasks: formData.Task.AdditionalTasks,
      },
    })
  )
}

const handleOkwwConfig = async () => {
  if (configActionsDisabled.value) return
  await startSession(userId.value, false, 'user')
}

const handleImportOkwwConfig = async () => {
  if (configActionsDisabled.value) return
  okwwImportLoading.value = true
  try {
    if (formData.Info.Base === 'native') throw new Error(t('core.edit.nativeConfigNoImport'))
    const response = await importScriptConfigFile(scriptId, userId.value)
    if (response.code !== 200)
      throw new Error(response.message || t('core.edit.importScriptConfigFailed'))
    const importTarget =
      formData.Info.Base === 'shared'
        ? t('core.comp.configSourceShared')
        : t('core.comp.configSourceIndependent')
    message.success(t('core.edit.importedP0ConfigurationFile', { p0: importTarget }))
  } catch (error) {
    message.error(error instanceof Error ? error.message : t('core.edit.importScriptConfigFailed'))
  } finally {
    okwwImportLoading.value = false
  }
}

// 编辑托管设置：ok-ww 页没有路由守卫，先显式停会话再跳转。
const handleScriptConfig = async () => {
  if (configActionsDisabled.value) return
  if (!(await stopSession(true))) return
  await router.push(`/scripts/${scriptId}/edit/okww`)
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
    if (!scriptApiError.value) message.error(t('core.edit.okWwScriptDoes'))
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
    if (!userApiError.value) message.error(t('core.edit.couldNotLoadUser'))
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
const { restoreApi, ensureBackup } = useConfigBackupApi({
  scriptId,
  userId: () => userId.value,
  logger,
})

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
// 与一键恢复同口径：单弹窗文案，跨配置来源时换标题并追加来源切换说明
// （确认后由基座把配置来源切回备份时点再恢复）。
const handleRestoreView = (
  target: string,
  item: { time: string; base?: string | null },
  currentMode?: string | null
) => {
  if (configLocked.value) return Promise.resolve(false)

  return new Promise<boolean>(resolve => {
    const { title, paragraphs } = buildRestoreConfirm(
      t,
      {
        title: t('core.edit.configRestoreDetailView'),
        desc: t('core.edit.configRestoreDetailConfirm', { script: OKWW_DISPLAY_NAME }),
      },
      item.base,
      currentMode
    )
    Modal.confirm({
      title,
      content: h(
        'div',
        paragraphs.map(text =>
          h('p', { style: { color: 'var(--ant-color-error)', margin: '0 0 8px' } }, text)
        )
      ),
      okType: 'danger',
      okText: t('core.edit.configRestoreConfirmOk'),
      cancelText: t('core.edit.cancel'),
      onOk: async () => {
        if (configLocked.value) {
          message.error(t('core.edit.configLocked'))
          resolve(false)
          return
        }

        try {
          const resp = await restoreApi.restore(target, item.time)
          // 后端失败走 HTTP 200 + body code=400，须显式检查返回体：备份不存在/
          // 路径未设置等抛错若被吞掉，会照常关弹窗并打开查看会话
          if (resp.code !== 200) {
            throw new Error(resp.message || t('core.edit.configRestoreFailed'))
          }
          restoreOpen.value = false
          if (target === 'mas') {
            // 恢复后重拉表单：后端 UserData 已回填，不重拉会让旧表单值在
            // 下次保存时整块写回、覆盖恢复结果（对齐一键恢复 handleRestored）
            await loadUser()
            await startSession(userId.value, true, 'user')
          } else {
            await startSession(scriptId, true, 'script')
          }
          resolve(true)
        } catch (e) {
          message.error(e instanceof Error ? e.message : t('core.edit.configRestoreFailed'))
          resolve(false)
        }
      },
      onCancel: () => resolve(false),
    })
  })
}

// 编辑会话归档（进入/退出时机，指纹去重）：与运行/会话下发前的双池归档
// （AutoProxy/ScriptConfig 下发处）配合——进入归档原生配置当前状态（MAS
// 触碰前原始态），退出归档 MAS 配置终态（编辑会话包络）
const ensureOkwwBackup = ensureBackup

onMounted(async () => {
  if (await loadScriptInfo()) {
    await loadUser()
    // 进入编辑页：归档 ok-ww 原生配置当前状态（MAS 触碰前的原始态）
    await ensureOkwwBackup('native')
  }
})

onUnmounted(() => {
  // 退出编辑页：先停会话再归档 MAS 配置终态——并行会与 final_task 的回写
  // 撞车，归档到半程状态；会话未开时 stopSession 自身早退，不影响归档时机
  void (async () => {
    await stopSession()
    await ensureOkwwBackup('mas')
  })()
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

/* 配置文件来源是独立卡片，与页面其它卡片一样自带上下的 24px 卡片间距
   （卡片默认首尾相接，该卡片上下的 基本信息卡片 / 任务配置 标题会直接贴住卡边）。 */
.config-source-card {
  margin: 24px 0;
}

/* 该卡片只有一个分区，且尾部是配置操作项：卡片自身的 padding 已是底部留白，
   去掉分区与操作项的尾距，避免卡片底部多出一整块空白。 */
.config-source-card :deep(.form-section),
.config-actions-tail :deep(.ant-form-item) {
  margin-bottom: 0;
}

.section-header {
  border-bottom-width: 1px;
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
