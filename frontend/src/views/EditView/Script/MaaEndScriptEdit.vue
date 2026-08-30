<template>
  <teleport to="body">
    <div v-if="showMaaEndConfigMask" class="maaend-config-mask">
      <div class="mask-content">
        <div class="mask-icon">
          <SettingOutlined :style="{ fontSize: '48px', color: 'var(--ant-color-primary)' }" />
        </div>
        <h2 class="mask-title">{{ t('edit.maaendConfigurationProgress') }}</h2>
        <p class="mask-description">
          {{ t('edit.scriptLevelMaaendConfiguration2') }}
          <br />
          {{ t('edit.clickSaveConfigurationWhen') }}
        </p>
        <div class="mask-actions">
          <a-button v-if="maaEndTaskId" type="primary" size="large" @click="handleSaveMaaEndConfig">
            {{ t('edit.saveConfiguration') }}
          </a-button>
        </div>
      </div>
    </div>
  </teleport>

  <ScriptEditHeader script-type="MaaEnd" @cancel="handleCancel">
    <template #extra-actions>
      <a-button
        type="primary"
        size="large"
        :loading="maaEndConfigLoading"
        :disabled="pageLoading || showMaaEndConfigMask"
        @click="handleMaaEndConfig"
      >
        <template #icon>
          <SettingOutlined />
        </template>
        {{ showMaaEndConfigMask ? '正在配置' : '配置 MaaEnd' }}
      </a-button>
    </template>
  </ScriptEditHeader>

  <div class="script-edit-content">
    <a-card :title="t('edit.maaendScriptConfiguration')" :loading="pageLoading" class="config-card">
      <template #extra>
        <a-tag class="type-tag">MaaEnd</a-tag>
      </template>

      <a-alert :message="t('edit.important')" type="warning" show-icon class="notice-alert">
        <template #description>
          <div class="notice-content">
            <p>{{ t('edit.k60SecondsRecommendedDefault') }}</p>
            <p>
              {{ t('edit.maaendAdapterStillUnder') }}
              <a
                :href="MAS_QQ_GROUP_URL"
                target="_blank"
                rel="noopener noreferrer"
                @click="handleExternalLink"
                >QQ群</a
              >
              {{ t('edit.reportIssueGo') }}
              <a
                href="https://github.com/AUTO-MAS-Project/AUTO-MAS/issues/149"
                @click="handleExternalLink"
                >BUG收集页</a
              >留言
            </p>
          </div>
        </template>
      </a-alert>

      <a-form ref="formRef" :model="formData" :rules="rules" layout="vertical" class="config-form">
        <div class="form-section">
          <div class="section-header">
            <h3>{{ t('edit.basicInfo') }}</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item name="name">
                <template #label>
                  <span class="form-label">
                    {{ t('edit.scriptName') }}
                    <a-tooltip :title="t('edit.tellsMaaendScriptInstances')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input
                  v-model:value="formData.name"
                  :placeholder="t('edit.enterScriptName')"
                  size="large"
                  @blur="handleChange('Info', 'Name', formData.name)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="16">
              <a-form-item name="path" :rules="rules.path">
                <template #label>
                  <span class="form-label">
                    {{ t('edit.maaendPath') }}
                    <a-tooltip :title="t('edit.pickDirectoryHoldingMaaend2')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-group compact class="path-input-group">
                  <a-input
                    v-model:value="formData.path"
                    :placeholder="t('edit.pickDirectoryHoldingMaaend')"
                    size="large"
                    class="path-input"
                    readonly
                  />
                  <a-button size="large" class="path-button" @click="selectMaaEndPath">
                    <template #icon>
                      <FolderOpenOutlined />
                    </template>
                    {{ t('edit.pickDirectory') }}
                  </a-button>
                </a-input-group>
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <div class="form-section">
          <div class="section-header">
            <h3>{{ t('edit.gameConfiguration') }}</h3>
          </div>

          <a-row :gutter="24">
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.controller') }}
                    <a-tooltip :title="t('edit.pickHowGameControlled')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-select
                  v-model:value="maaEndConfig.Game.ControllerType"
                  size="large"
                  :options="controllerOptions"
                  :loading="maaEndOptionsLoading"
                  :disabled="maaEndOptionsLoading || isSaving"
                  @change="handleControllerTypeChange"
                />
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.closeGameAfterTask2') }}
                    <a-tooltip :title="t('edit.whetherGameClosesAfter')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-select
                  v-model:value="maaEndConfig.Game.CloseOnFinish"
                  size="large"
                  :options="booleanOptions"
                  @change="handleChange('Game', 'CloseOnFinish', $event)"
                />
              </a-form-item>
            </a-col>
          </a-row>

          <a-row v-if="isWinController" :gutter="24">
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.gamePath') }}
                    <a-tooltip :title="t('edit.pickEndfieldExePath')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-group compact class="path-input-group">
                  <a-input
                    v-model:value="maaEndConfig.Game.Path"
                    :placeholder="t('edit.pickGameExecutable')"
                    size="large"
                    class="path-input"
                    readonly
                  />
                  <a-button size="large" class="path-button" @click="selectGamePath">
                    <template #icon>
                      <FolderOpenOutlined />
                    </template>
                    {{ t('edit.pickFile') }}
                  </a-button>
                </a-input-group>
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.launchArguments') }}
                    <a-tooltip :title="t('edit.commandLineArgumentsUsed')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input
                  v-model:value="maaEndConfig.Game.Arguments"
                  :placeholder="t('edit.enterLaunchArguments')"
                  size="large"
                  @blur="handleChange('Game', 'Arguments', maaEndConfig.Game.Arguments)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.waitTime') }}
                    <a-tooltip :title="t('edit.pcControllersOnlySeconds')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-number
                  v-model:value="maaEndConfig.Game.WaitTime"
                  :min="60"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @blur="handleChange('Game', 'WaitTime', maaEndConfig.Game.WaitTime)"
                />
              </a-form-item>
            </a-col>
          </a-row>

          <a-row v-else-if="isAdbController" :gutter="24">
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.emulator') }}
                    <a-tooltip :title="t('edit.pickEmulatorUse')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-select
                  v-model:value="maaEndConfig.Game.EmulatorId"
                  size="large"
                  :placeholder="t('edit.pickEmulator')"
                  :loading="emulatorLoading"
                  @change="handleEmulatorSelectChange"
                >
                  <a-select-option
                    v-for="item in emulatorOptions"
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
                    {{ t('edit.emulatorInstance') }}
                    <a-tooltip
                      :title="
                        emulatorDeviceOptions.length === 0 && !emulatorDeviceLoading
                          ? t('edit.thisEmulatorCannotBe')
                          : t('edit.pickEmulatorInstance')
                      "
                    >
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input
                  v-if="showManualEmulatorIndexInput"
                  v-model:value="maaEndConfig.Game.EmulatorIndex"
                  size="large"
                  :placeholder="t('edit.enterInstanceInfoAs')"
                  @blur="handleChange('Game', 'EmulatorIndex', maaEndConfig.Game.EmulatorIndex)"
                />
                <a-select
                  v-else
                  v-model:value="maaEndConfig.Game.EmulatorIndex"
                  size="large"
                  :placeholder="t('edit.pickInstance')"
                  :loading="emulatorDeviceLoading"
                  :disabled="!maaEndConfig.Game.EmulatorId"
                  @change="handleChange('Game', 'EmulatorIndex', $event)"
                >
                  <a-select-option
                    v-for="item in emulatorDeviceOptions"
                    :key="item.value"
                    :value="item.value"
                  >
                    {{ item.label }}
                  </a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <div class="form-section">
          <div class="section-header">
            <h3>{{ t('edit.runConfiguration') }}</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="6">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.accountSwitching') }}
                    <a-tooltip :title="t('edit.chooseWhetherMasSwitches')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-select
                  v-model:value="maaEndConfig.Run.AccountSwitchMethod"
                  size="large"
                  :options="accountSwitchMethodOptions"
                  @change="handleChange('Run', 'AccountSwitchMethod', $event)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.runsPerDay') }}
                    <a-tooltip :title="t('edit.skipRunOnceThis')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-number
                  v-model:value="maaEndConfig.Run.ProxyTimesLimit"
                  :min="0"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @blur="handleChange('Run', 'ProxyTimesLimit', maaEndConfig.Run.ProxyTimesLimit)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.retryLimit2') }}
                    <a-tooltip :title="t('edit.ifRunStillUnfinished')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-number
                  v-model:value="maaEndConfig.Run.RunTimesLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @blur="handleChange('Run', 'RunTimesLimit', maaEndConfig.Run.RunTimesLimit)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.runTimeoutMinutes') }}
                    <a-tooltip :title="t('edit.treatRunAsTimed')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-number
                  v-model:value="maaEndConfig.Run.RunTimeLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @blur="handleChange('Run', 'RunTimeLimit', maaEndConfig.Run.RunTimeLimit)"
                />
              </a-form-item>
            </a-col>
          </a-row>
        </div>
      </a-form>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { FormInstance } from 'ant-design-vue'
import { message } from 'ant-design-vue'
import type { ComboBoxItem } from '@/api'
import { Service } from '@/api'
import type { MaaEndScriptConfig, ScriptType } from '@/types/script'
import { useEmulatorDeviceOptions } from '@/composables/useEmulatorDeviceOptions'
import { useScriptApi } from '@/composables/useScriptApi'
import { useWebSocket } from '@/composables/useWebSocket'
import {
  WS_TASK_COMPLETED,
  WS_TASK_NOTICE,
  type WSTaskNoticeData,
} from '@/services/websocket/types'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import { MAS_QQ_GROUP_URL, handleExternalLink } from '@/utils/openExternal'
import { FolderOpenOutlined, QuestionCircleOutlined, SettingOutlined } from '@ant-design/icons-vue'
import ScriptEditHeader from '@/components/ScriptEditHeader.vue'

const { t } = useI18n()

const route = useRoute()
const router = useRouter()
const { getScript, getMaaEndOptions, updateScript } = useScriptApi()
const {
  emulatorDeviceLoading,
  emulatorDeviceOptions,
  clearEmulatorDeviceOptions,
  loadEmulatorDeviceOptions,
} = useEmulatorDeviceOptions()
const { subscribe, unsubscribe } = useWebSocket()

const formRef = ref<FormInstance>()
const pageLoading = ref(false)
const scriptId = route.params.id as string
const isInitializing = ref(true)
const isSaving = ref(false)
const maaEndOptionsLoading = ref(false)
const maaEndConfigLoading = ref(false)
const showMaaEndConfigMask = ref(false)
const maaEndSubscriptionIds = ref<string[]>([])
const maaEndTaskId = ref<string | null>(null)
let maaEndConfigTimeout: number | null = null

const formData = reactive({
  name: '',
  type: 'MaaEnd' as ScriptType,
  get path() {
    return maaEndConfig.Info.Path
  },
  set path(value: string) {
    maaEndConfig.Info.Path = value
  },
})

const maaEndConfig = reactive<MaaEndScriptConfig>({
  Info: {
    Name: '',
    Path: '.',
  },
  Run: {
    RunTimeLimit: 30,
    ProxyTimesLimit: 0,
    RunTimesLimit: 3,
    AccountSwitchMethod: 'MAS',
  },
  Game: {
    ControllerType: '',
    Path: '',
    Arguments: '',
    WaitTime: 60,
    EmulatorId: '',
    EmulatorIndex: '',
    CloseOnFinish: false,
  },
})

const rules = {
  name: [{ required: true, message: t('edit.enterScriptName'), trigger: 'blur' }],
  path: [{ required: true, message: t('edit.pickMaaendPath'), trigger: 'blur' }],
}

const controllerOptions = ref<ComboBoxItem[]>([])
const controllerProtocols = ref<Record<string, string>>({})

const booleanOptions = [
  { label: '是', value: true },
  { label: '否', value: false },
]

const accountSwitchMethodOptions = [
  { label: 'MAS 自建账号切换', value: 'MAS' },
  { label: 'MAAEND 内置账号切换', value: 'MAAEND' },
]

const emulatorLoading = ref(false)
const emulatorOptions = ref<ComboBoxItem[]>([])

const controllerProtocol = computed(
  () => controllerProtocols.value[maaEndConfig.Game.ControllerType ?? '']
)
const isWinController = computed(() => controllerProtocol.value === 'Win32')
const isAdbController = computed(() => controllerProtocol.value === 'Adb')
const showManualEmulatorIndexInput = computed(
  () =>
    emulatorDeviceOptions.value.length === 0 &&
    !emulatorDeviceLoading.value &&
    Boolean(maaEndConfig.Game.EmulatorId)
)

const handleChange = async (category: string, key: string, value: unknown) => {
  if (isInitializing.value || isSaving.value) return

  isSaving.value = true
  try {
    const success = await updateScript(scriptId, {
      [category]: { [key]: value },
    })
    if (success) {
      await refreshScript()
    }
  } finally {
    isSaving.value = false
  }
}

const applyMaaEndConfig = (config: MaaEndScriptConfig) => {
  Object.assign(maaEndConfig.Info, config.Info ?? {})
  Object.assign(maaEndConfig.Run, config.Run ?? {})
  Object.assign(maaEndConfig.Game, config.Game ?? {})
}

const refreshScript = async () => {
  const scriptDetail = await getScript(scriptId)
  if (!scriptDetail) return
  applyMaaEndConfig(scriptDetail.config as MaaEndScriptConfig)
  formData.name = scriptDetail.name
}

const loadEmulatorOptions = async () => {
  emulatorLoading.value = true
  try {
    const response = await Service.getEmulatorComboxApiInfoComboxEmulatorPost()
    if (response.code === 200) {
      emulatorOptions.value = response.data || []
    }
  } finally {
    emulatorLoading.value = false
  }
}

const loadMaaEndOptions = async () => {
  maaEndOptionsLoading.value = true
  try {
    const response = await getMaaEndOptions(scriptId)
    if (response?.code !== 200) return

    controllerOptions.value = response.controllers
    controllerProtocols.value = response.controllerTypes
  } finally {
    maaEndOptionsLoading.value = false
  }
}

const loadScript = async () => {
  pageLoading.value = true
  try {
    const routeState = history.state as any
    if (routeState?.scriptData) {
      const config = routeState.scriptData.config as MaaEndScriptConfig
      formData.name = config.Info?.Name || '新建 MaaEnd 脚本'
      applyMaaEndConfig(config)
    }

    const scriptDetail = await getScript(scriptId)
    if (!scriptDetail) {
      message.error(t('edit.scriptDoesNotExist'))
      router.push('/scripts')
      return
    }

    formData.type = scriptDetail.type
    formData.name = scriptDetail.name
    applyMaaEndConfig(scriptDetail.config as MaaEndScriptConfig)

    if (maaEndConfig.Game.EmulatorId) {
      void loadEmulatorDeviceOptions(maaEndConfig.Game.EmulatorId)
    }
  } finally {
    pageLoading.value = false
  }
}

const handleControllerTypeChange = async (value: MaaEndScriptConfig['Game']['ControllerType']) => {
  if (!value) return

  const protocol = controllerProtocols.value[value]
  if (!protocol) return

  isSaving.value = true
  try {
    const gamePayload =
      protocol === 'Adb'
        ? {
            ControllerType: value,
            Path: '',
            Arguments: '',
            WaitTime: 60,
          }
        : {
            ControllerType: value,
            EmulatorId: '',
            EmulatorIndex: '',
          }

    if (protocol !== 'Adb') {
      clearEmulatorDeviceOptions()
      maaEndConfig.Game.EmulatorId = ''
      maaEndConfig.Game.EmulatorIndex = ''
    } else {
      maaEndConfig.Game.Path = ''
      maaEndConfig.Game.Arguments = ''
    }

    const success = await updateScript(scriptId, { Game: gamePayload })
    if (success) {
      await refreshScript()
    }
  } finally {
    isSaving.value = false
  }

  if (protocol === 'Adb') {
    await loadEmulatorOptions()
  }
}

const handleEmulatorSelectChange = async (emulatorId: string) => {
  maaEndConfig.Game.EmulatorIndex = ''
  if (emulatorId) {
    void loadEmulatorDeviceOptions(emulatorId)
  } else {
    clearEmulatorDeviceOptions()
  }

  isSaving.value = true
  try {
    const success = await updateScript(scriptId, {
      Game: {
        EmulatorId: emulatorId,
        EmulatorIndex: '',
      },
    })
    if (success) {
      await refreshScript()
    }
  } finally {
    isSaving.value = false
  }
}

const selectMaaEndPath = async () => {
  const path = await window.electronAPI?.selectFolder()
  if (!path) return
  maaEndConfig.Info.Path = path
  await handleChange('Info', 'Path', path)
  await loadMaaEndOptions()
}

const selectGamePath = async () => {
  const paths = await window.electronAPI?.selectFile([
    {
      name: 'Endfield.exe',
      extensions: ['exe'],
    },
  ])
  const path = paths?.[0]
  if (!path) return
  const fileName = path.split(/[\\/]/).pop()
  if (fileName?.toLowerCase() !== 'endfield.exe') {
    message.error(t('edit.pickEndfieldExe'))
    return
  }
  maaEndConfig.Game.Path = path
  await handleChange('Game', 'Path', path)
}

const cleanupConfigSession = () => {
  for (const subscriptionId of maaEndSubscriptionIds.value) {
    unsubscribe(subscriptionId)
  }
  maaEndSubscriptionIds.value = []
  maaEndTaskId.value = null
  showMaaEndConfigMask.value = false
  if (maaEndConfigTimeout) {
    window.clearTimeout(maaEndConfigTimeout)
    maaEndConfigTimeout = null
  }
}

const handleMaaEndConfig = async () => {
  try {
    maaEndConfigLoading.value = true
    cleanupConfigSession()

    const response = await Service.addTaskApiDispatchStartPost({
      taskId: scriptId,
      mode: TaskCreateIn.mode.SCRIPT_CONFIG,
    })

    if (!response?.taskId) {
      throw new Error(response?.message || '启动 MaaEnd 配置失败')
    }

    const subscriptionIds = [
      subscribe({ id: response.taskId, type: WS_TASK_NOTICE }, wsMessage => {
        const data = wsMessage.data as unknown as WSTaskNoticeData
        if (data.level === 'error') {
          message.error(`MaaEnd 配置异常: ${data.message}`)
        }
      }),
      subscribe({ id: response.taskId, type: WS_TASK_COMPLETED }, () => {
        cleanupConfigSession()
      }),
    ]

    maaEndSubscriptionIds.value = subscriptionIds
    maaEndTaskId.value = response.taskId
    showMaaEndConfigMask.value = true
    message.success(t('edit.scriptLevelMaaendConfiguration'))

    maaEndConfigTimeout = window.setTimeout(
      () => {
        cleanupConfigSession()
        message.info(t('edit.maaendConfigurationSessionTimed'))
      },
      30 * 60 * 1000
    )
  } catch (error) {
    message.error(error instanceof Error ? error.message : '启动 MaaEnd 配置失败')
  } finally {
    maaEndConfigLoading.value = false
  }
}

const handleSaveMaaEndConfig = async () => {
  try {
    if (!maaEndTaskId.value) {
      throw new Error('未找到活动配置会话')
    }

    const response = await Service.stopTaskApiDispatchStopPost({ taskId: maaEndTaskId.value })
    if (response.code !== 200) {
      throw new Error(response.message || '保存配置失败')
    }

    cleanupConfigSession()
    message.success(t('edit.maaendConfigurationSaved'))
  } catch (error) {
    message.error(error instanceof Error ? error.message : '保存配置失败')
  }
}

const handleCancel = () => {
  cleanupConfigSession()
  router.push('/scripts')
}

onMounted(async () => {
  await loadScript()
  await loadMaaEndOptions()
  await loadEmulatorOptions()
  isInitializing.value = false
})

onBeforeUnmount(() => {
  cleanupConfigSession()
})
</script>

<style scoped>
.script-edit-content {
  flex: 1;
}

.config-card {
  border-radius: 16px;
  box-shadow:
    0 4px 20px rgba(0, 0, 0, 0.08),
    0 1px 3px rgba(0, 0, 0, 0.1);
  border: 1px solid var(--ant-color-border-secondary);
  overflow: hidden;
}

.config-card :deep(.ant-card-head) {
  background: var(--ant-color-bg-container);
  border-bottom: 2px solid var(--ant-color-border-secondary);
  padding: 24px 32px;
}

.config-card :deep(.ant-card-body) {
  padding: 32px;
}

.type-tag {
  font-size: 14px;
  font-weight: 600;
  padding: 8px 16px;
  border-radius: 8px;
  border: 1px solid var(--ant-color-primary-border);
  color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
}

.maaend-tip {
  margin-bottom: 24px;
  border-radius: 8px;
}

.maaend-tip :deep(.ant-alert-description) {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.form-section {
  margin-bottom: 12px;
  animation: fadeInUp 0.6s ease-out;
}

.section-header {
  margin-bottom: 6px;
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

.path-input-group {
  display: flex;
  border-radius: 8px;
  overflow: hidden;
  border: 2px solid var(--ant-color-border);
}

.path-input {
  flex: 1;
  border: none !important;
  border-radius: 0 !important;
}

.path-button {
  border: none;
  border-radius: 0;
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-primary);
  font-weight: 600;
  padding: 0 20px;
  border-left: 1px solid var(--ant-color-border-secondary);
}

.config-form :deep(.ant-form-item) {
  margin-bottom: 24px;
}

.maaend-config-mask {
  position: fixed;
  inset: 0;
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
  border: 1px solid var(--ant-color-border);
}

.mask-icon {
  margin-bottom: 16px;
}

.mask-title {
  font-size: 18px;
  font-weight: 600;
  margin: 0 0 8px;
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
  .config-card :deep(.ant-card-body) {
    padding: 20px;
  }
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
