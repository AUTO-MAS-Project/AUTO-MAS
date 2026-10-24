<template>
  <ScriptEditHeader
    script-type="BetterGI"
    :title="t('edit.editScript')"
    :doc-url="MAS_DOC_URLS.scripts"
    @cancel="handleCancel"
  />

  <ConfigLockPanel :script-id="scriptId" content-class="script-edit-content">
    <a-card
      :title="t('edit.bettergiScriptConfiguration')"
      :loading="pageLoading"
      class="config-card"
    >
      <template #extra>
        <a-tag color="blue" class="type-tag">BetterGI</a-tag>
      </template>

      <a-form :model="formData" :rules="rules" layout="vertical" class="config-form">
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
                    <a-tooltip :title="t('edit.bettergiInstanceNameHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input
                  v-model:value="formData.name"
                  :placeholder="t('edit.enterScriptName')"
                  size="large"
                  class="modern-input"
                  @blur="handleChange('Info', 'Name', formData.name)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="16">
              <a-form-item name="path" :rules="rules.path">
                <template #label>
                  <span class="form-label">
                    {{ t('edit.bettergiPath') }}
                    <a-tooltip :title="t('edit.bettergiPickExeDir')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-group compact class="path-input-group">
                  <a-input
                    v-model:value="formData.path"
                    :placeholder="t('edit.bettergiPickExeDirPlaceholder')"
                    size="large"
                    class="path-input"
                    readonly
                  />
                  <a-button
                    size="large"
                    class="path-button"
                    :disabled="isSaving"
                    @click="selectRootPath"
                  >
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
                    <a-tooltip :title="t('edit.bettergiControllerHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-select
                  v-model:value="bettergiConfig.Game.Controller"
                  size="large"
                  style="width: 100%"
                  @change="handleChange('Game', 'Controller', bettergiConfig.Game.Controller)"
                >
                  <a-select-option value="电脑端-前台">
                    {{ t('edit.bettergiControllerForeground') }}
                  </a-select-option>
                  <a-select-option value="电脑端-云原神" disabled>
                    {{ t('edit.bettergiControllerCloud') }}
                  </a-select-option>
                  <a-select-option value="电脑端-桌面分身" disabled>
                    {{ t('edit.bettergiControllerDesktopClone') }}
                  </a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.bettergiCloseGameOnFinish') }}
                    <a-tooltip :title="t('edit.bettergiCloseGameOnFinishHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-select
                  v-model:value="bettergiConfig.Game.CloseOnFinish"
                  size="large"
                  style="width: 100%"
                  @change="handleChange('Game', 'CloseOnFinish', bettergiConfig.Game.CloseOnFinish)"
                >
                  <a-select-option :value="true">{{ t('edit.yes') }}</a-select-option>
                  <a-select-option :value="false">{{ t('edit.no') }}</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
          </a-row>

          <a-row :gutter="24">
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.genshinUpdateAuto') }}
                    <a-tooltip :title="t('edit.genshinUpdateAutoHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-select
                  v-model:value="bettergiConfig.Game.IfAutoUpdate"
                  size="large"
                  style="width: 100%"
                  @change="handleChange('Game', 'IfAutoUpdate', bettergiConfig.Game.IfAutoUpdate)"
                >
                  <a-select-option :value="true">{{ t('edit.yes') }}</a-select-option>
                  <a-select-option :value="false">{{ t('edit.no') }}</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.bettergiAccountSwitchMethod') }}
                    <a-tooltip :title="t('edit.bettergiAccountSwitchMethodHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-select
                  v-model:value="bettergiConfig.Run.AccountSwitchMethod"
                  size="large"
                  style="width: 100%"
                  @change="handleAccountSwitchMethodChange"
                >
                  <a-select-option value="BGI">
                    {{ t('edit.bettergiAccountSwitchMethodBgi') }}
                  </a-select-option>
                  <a-select-option value="MAS">
                    {{ t('edit.bettergiAccountSwitchMethodMas') }}
                  </a-select-option>
                </a-select>
                <span class="control-hint">{{ t('edit.accountSwitch16x9Only') }}</span>
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <div class="form-section">
          <div class="section-header">
            <h3>{{ t('edit.runConfiguration') }}</h3>
          </div>
          <ScriptHardTimeoutField
            v-model:value="bettergiConfig.Run.HardTimeLimit"
            @save="handleChange('Run', 'HardTimeLimit', bettergiConfig.Run.HardTimeLimit)"
          />
          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.runsPerDay') }}
                    <a-tooltip :title="t('edit.k0MeansNoLimit')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-number
                  v-model:value="bettergiConfig.Run.ProxyTimesLimit"
                  :min="0"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @blur="handleChange('Run', 'ProxyTimesLimit', bettergiConfig.Run.ProxyTimesLimit)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.retryLimit2') }}
                    <a-tooltip :title="t('edit.bettergiRetryLimitHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-number
                  v-model:value="bettergiConfig.Run.RunTimesLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @blur="handleChange('Run', 'RunTimesLimit', bettergiConfig.Run.RunTimesLimit)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.runTimeoutMinutes') }}
                    <a-tooltip :title="t('edit.bettergiRunTimeoutHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-number
                  v-model:value="bettergiConfig.Run.RunTimeLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @blur="handleChange('Run', 'RunTimeLimit', bettergiConfig.Run.RunTimeLimit)"
                />
              </a-form-item>
            </a-col>
          </a-row>
        </div>
      </a-form>
    </a-card>
  </ConfigLockPanel>
</template>

<script setup lang="ts">
import ScriptHardTimeoutField from '@/views/EditView/Script/components/ScriptHardTimeoutField.vue'
import ConfigLockPanel from '@/components/ConfigLockPanel.vue'
import ScriptEditHeader from '@/components/ScriptEditHeader.vue'
import { MAS_DOC_URLS } from '@/utils/openExternal'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { message, Modal } from 'ant-design-vue'
import { FolderOpenOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import { useScriptApi } from '@/composables/useScriptApi'
import { useScriptSaveMutation } from '@/composables/useScriptSaveMutation'

const { t } = useI18n()
const logger = window.electronAPI.getLogger('BetterGI脚本编辑')
const route = useRoute()
const router = useRouter()
const { getScript, updateScript, error: scriptApiError } = useScriptApi()

const scriptId = route.params.id as string
const pageLoading = ref(true)
// 保存串行队列：连续改动按序写回，不再被布尔互斥丢掉
const isInitializing = ref(true)
const {
  isSaving,
  enqueue,
  saveField: handleChange,
} = useScriptSaveMutation({ scriptId, isInitializing, logger })

// ══ BetterGI 项目结构常量（需与 app/task/BetterGI/AutoProxy.py 中的 _BGI_REL_* 保持同步）══
const BGI_EXE_NAME = 'BetterGI.exe'

interface BetterGIInfoForm {
  Name: string
  RootPath: string
}

interface BetterGIRunForm {
  HardTimeLimit: number
  ProxyTimesLimit: number
  RunTimesLimit: number
  RunTimeLimit: number
  UseAdmin: boolean
  AccountSwitchMethod: 'BGI' | 'MAS'
}

interface BetterGIGameForm {
  Controller: string
  CloseOnFinish: boolean
  IfAutoUpdate: boolean
}

interface BetterGIScriptConfigForm {
  Info: BetterGIInfoForm
  Run: BetterGIRunForm
  Game: BetterGIGameForm
}

const formData = reactive({
  name: '',
  get path() {
    return bettergiConfig.Info.RootPath
  },
  set path(value: string) {
    bettergiConfig.Info.RootPath = value
  },
})

const bettergiConfig = reactive<BetterGIScriptConfigForm>({
  Info: { Name: '', RootPath: '.' },
  Run: {
    HardTimeLimit: 120,
    ProxyTimesLimit: 0,
    RunTimesLimit: 3,
    RunTimeLimit: 10,
    UseAdmin: true,
    AccountSwitchMethod: 'MAS',
  },
  Game: {
    Controller: '电脑端-前台',
    CloseOnFinish: true,
    IfAutoUpdate: false,
  },
})

const rules = computed(() => ({
  name: [{ required: true, message: t('edit.enterScriptName'), trigger: 'blur' }],
  path: [{ required: true, message: t('edit.bettergiPathRequired'), trigger: 'blur' }],
}))

const handleCancel = () => router.push('/scripts')

const handleAccountSwitchMethodChange = async (
  value: BetterGIScriptConfigForm['Run']['AccountSwitchMethod']
) => {
  await handleChange('Run', 'AccountSwitchMethod', value)
}

const applyRootPathDefaults = async (rootPath: string) => {
  if (!rootPath || rootPath === '.') {
    message.warning(t('edit.pickScriptRootDirectory'))
    return false
  }
  const norm = rootPath.replace(/\\/g, '/').replace(/\/+$/g, '')
  const previousPath = bettergiConfig.Info.RootPath
  bettergiConfig.Info.RootPath = norm

  return enqueue(async () => {
    try {
      const success = await updateScript(scriptId, {
        Info: { RootPath: norm },
      })
      if (success) {
        message.success(t('edit.bettergiRootPathSaved'))
        return true
      }
      bettergiConfig.Info.RootPath = previousPath
      return false
    } catch (error) {
      bettergiConfig.Info.RootPath = previousPath
      throw error
    }
  })
}

const loadScript = async () => {
  pageLoading.value = true
  isInitializing.value = true
  try {
    const detail = await getScript(scriptId)
    if (!detail) {
      if (!scriptApiError.value) message.error(t('edit.scriptDoesNotExist'))
      handleCancel()
      return
    }
    if (detail.type !== 'BetterGI') {
      message.error(t('edit.bettergiNotBettergiScript'))
      handleCancel()
      return
    }
    formData.name = detail.name
    const config = detail.config as Partial<BetterGIScriptConfigForm>
    Object.assign(bettergiConfig.Info, config.Info || {})
    Object.assign(bettergiConfig.Run, config.Run || {})
    Object.assign(bettergiConfig.Game, config.Game || {})
  } catch {
    if (!scriptApiError.value) message.error(t('edit.couldNotLoadScript'))
  } finally {
    isInitializing.value = false
    pageLoading.value = false
  }
}

const selectRootPath = async () => {
  const picked = await window.electronAPI.selectFolder()
  if (!picked) return
  const normalized = picked.replace(/\\/g, '/')
  const exePath = `${normalized}/${BGI_EXE_NAME}`
  const exists = await window.electronAPI.fileExists(exePath)
  if (!exists) {
    Modal.error({
      title: t('edit.bettergiInvalidDirectory'),
      content: t('edit.bettergiExeNotFound', { p0: BGI_EXE_NAME }),
      okText: t('edit.gotIt'),
    })
    return
  }
  formData.path = normalized
  await applyRootPathDefaults(normalized)
}

onMounted(loadScript)
</script>

<style scoped src="@/styles/scriptEditForm.css"></style>

<style scoped>
.section-header {
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.control-hint {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  font-weight: 400;
  color: var(--ant-color-text-tertiary);
}

.path-input-group {
  border: 1px solid var(--ant-color-border);
}

.path-input {
  min-width: 0;
}

.path-button {
  flex-shrink: 0;
}
</style>
