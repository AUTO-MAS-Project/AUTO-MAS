<template>
  <ScriptEditHeader
    script-type="BetterGI"
    :title="t('core.edit.editScript')"
    :doc-url="MAS_DOC_URLS.scripts"
    @cancel="handleCancel"
  />

  <ConfigLockPanel :script-id="scriptId" content-class="script-edit-content">
    <a-card
      :title="t('core.edit.bettergiScriptConfiguration')"
      :loading="pageLoading"
      class="config-card"
    >
      <template #extra>
        <a-tag color="blue" class="type-tag">BetterGI</a-tag>
      </template>

      <a-form :model="formData" :rules="rules" layout="vertical" class="config-form">
        <div class="form-section">
          <div class="section-header">
            <h3>{{ t('core.edit.basicInfo') }}</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item name="name">
                <template #label>
                  <FieldLabelWithHint
                    :text="t('core.edit.scriptName')"
                    :hint="t('core.edit.bettergiInstanceNameHint')"
                    variant="form"
                  />
                </template>
                <a-input
                  v-model:value="formData.name"
                  :placeholder="t('core.edit.enterScriptName')"
                  size="large"
                  class="modern-input"
                  @blur="handleChange('Info', 'Name', formData.name)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="16">
              <a-form-item name="path" :rules="rules.path">
                <template #label>
                  <FieldLabelWithHint
                    :text="t('core.edit.bettergiPath')"
                    :hint="t('core.edit.bettergiPickExeDir')"
                    variant="form"
                  />
                </template>
                <PathPickerField
                  v-model="formData.path"
                  mode="folder"
                  :placeholder="t('core.edit.bettergiPickExeDirPlaceholder')"
                  :pick-label="t('core.edit.pickDirectory')"
                  :disabled="isSaving"
                  @pick="selectRootPath"
                />
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <BetterGIProgramUpdateSettings
          v-model:update="bettergiConfig.Update"
          :ready="!pageLoading && !isSaving"
          @save="(key, value) => handleChange('Update', key, value)"
        />

        <div class="form-section">
          <div class="section-header">
            <h3>{{ t('core.edit.gameConfiguration') }}</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <FieldLabelWithHint
                    :text="t('core.edit.controller')"
                    :hint="t('core.edit.bettergiControllerHint')"
                    variant="form"
                  />
                </template>
                <a-select
                  v-model:value="bettergiConfig.Game.Controller"
                  size="large"
                  style="width: 100%"
                  @change="handleChange('Game', 'Controller', bettergiConfig.Game.Controller)"
                >
                  <a-select-option value="电脑端-前台">
                    {{ t('core.edit.bettergiControllerForeground') }}
                  </a-select-option>
                  <a-select-option value="电脑端-云原神" disabled>
                    {{ t('core.edit.bettergiControllerCloud') }}
                  </a-select-option>
                  <a-select-option value="电脑端-桌面分身" disabled>
                    {{ t('core.edit.bettergiControllerDesktopClone') }}
                  </a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <FieldLabelWithHint
                    :text="t('core.edit.bettergiCloseGameOnFinish')"
                    :hint="t('core.edit.bettergiCloseGameOnFinishHint')"
                    variant="form"
                  />
                </template>
                <a-select
                  v-model:value="bettergiConfig.Game.CloseOnFinish"
                  size="large"
                  style="width: 100%"
                  @change="handleChange('Game', 'CloseOnFinish', bettergiConfig.Game.CloseOnFinish)"
                >
                  <a-select-option :value="true">{{ t('core.edit.yes') }}</a-select-option>
                  <a-select-option :value="false">{{ t('core.edit.no') }}</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
          </a-row>

          <a-row :gutter="24">
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <FieldLabelWithHint
                    :text="t('core.edit.genshinUpdateAuto')"
                    :hint="t('core.edit.genshinUpdateAutoHint')"
                    variant="form"
                  />
                </template>
                <a-select
                  v-model:value="bettergiConfig.Game.IfAutoUpdate"
                  size="large"
                  style="width: 100%"
                  @change="handleChange('Game', 'IfAutoUpdate', bettergiConfig.Game.IfAutoUpdate)"
                >
                  <a-select-option :value="true">{{ t('core.edit.yes') }}</a-select-option>
                  <a-select-option :value="false">{{ t('core.edit.no') }}</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <FieldLabelWithHint
                    :text="t('core.edit.bettergiAccountSwitchMethod')"
                    :hint="t('core.edit.bettergiAccountSwitchMethodHint')"
                    variant="form"
                  />
                </template>
                <a-select
                  v-model:value="bettergiConfig.Run.AccountSwitchMethod"
                  size="large"
                  style="width: 100%"
                  @change="handleAccountSwitchMethodChange"
                >
                  <a-select-option value="BGI">
                    {{ t('core.edit.bettergiAccountSwitchMethodBgi') }}
                  </a-select-option>
                  <a-select-option value="MAS">
                    {{ t('core.edit.bettergiAccountSwitchMethodMas') }}
                  </a-select-option>
                </a-select>
                <span class="control-hint">{{ t('core.edit.accountSwitch16x9Only') }}</span>
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <div class="form-section">
          <div class="section-header">
            <h3>{{ t('core.edit.runConfiguration') }}</h3>
          </div>
          <ScriptRunLimitsSection
            v-model:hard-time-limit="bettergiConfig.Run.HardTimeLimit"
            v-model:daily-limit="bettergiConfig.Run.ProxyTimesLimit"
            v-model:retry-limit="bettergiConfig.Run.RunTimesLimit"
            v-model:timeout="bettergiConfig.Run.RunTimeLimit"
            :retry-hint="t('core.edit.bettergiRetryLimitHint')"
            :timeout-hint="t('core.edit.bettergiRunTimeoutHint')"
            @save="key => handleChange('Run', key, bettergiConfig.Run[key])"
          />
        </div>
      </a-form>
    </a-card>
  </ConfigLockPanel>
</template>

<script setup lang="ts">
import BetterGIProgramUpdateSettings from './components/BetterGIProgramUpdateSettings.vue'
import type { BetterGIConfig_Update } from '@/api'
import ScriptRunLimitsSection from './components/ScriptRunLimitsSection.vue'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import ConfigLockPanel from '@/components/ConfigLockPanel.vue'
import ScriptEditHeader from '@/components/ScriptEditHeader.vue'
import PathPickerField from '@/components/PathPickerField.vue'
import { MAS_DOC_URLS } from '@/utils/openExternal'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { message, Modal } from 'ant-design-vue'
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
  Update: BetterGIConfig_Update
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
  Update: { TakeoverEnabled: false, Channel: 'stable', MirrorChyanCDK: '' },
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
  name: [{ required: true, message: t('core.edit.enterScriptName'), trigger: 'blur' }],
  path: [{ required: true, message: t('core.edit.bettergiPathRequired'), trigger: 'blur' }],
}))

const handleCancel = () => router.push('/scripts')

const handleAccountSwitchMethodChange = async (
  value: BetterGIScriptConfigForm['Run']['AccountSwitchMethod']
) => {
  await handleChange('Run', 'AccountSwitchMethod', value)
}

const applyRootPathDefaults = async (rootPath: string) => {
  if (!rootPath || rootPath === '.') {
    message.warning(t('core.edit.pickScriptRootDirectory'))
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
        message.success(t('core.edit.bettergiRootPathSaved'))
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
      if (!scriptApiError.value) message.error(t('core.edit.scriptDoesNotExist'))
      handleCancel()
      return
    }
    if (detail.type !== 'BetterGI') {
      message.error(t('core.edit.bettergiNotBettergiScript'))
      handleCancel()
      return
    }
    formData.name = detail.name
    const config = detail.config as Partial<BetterGIScriptConfigForm>
    Object.assign(bettergiConfig.Info, config.Info || {})
    Object.assign(bettergiConfig.Run, config.Run || {})
    Object.assign(bettergiConfig.Game, config.Game || {})
    Object.assign(bettergiConfig.Update, config.Update || {})
  } catch {
    if (!scriptApiError.value) message.error(t('core.edit.couldNotLoadScript'))
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
      title: t('core.edit.bettergiInvalidDirectory'),
      content: t('core.edit.bettergiExeNotFound', { p0: BGI_EXE_NAME }),
      okText: t('core.edit.gotIt'),
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
</style>
