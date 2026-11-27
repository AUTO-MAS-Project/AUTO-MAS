<template>
  <ScriptEditLayout
    :script-id="scriptId"
    :loading="pageLoading"
    :header="{
      scriptType: 'BetterGI',
      title: t('core.edit.editScript'),
      docUrl: MAS_DOC_URLS.scripts,
    }"
    :form="{ model: formData, rules }"
    :form-label="t('core.edit.bettergiScriptConfiguration')"
    @cancel="handleCancel"
  >
    <template #basic>
      <ScriptBasicInfoCard
        v-model:name="formData.name"
        :name-hint="t('core.edit.bettergiInstanceNameHint')"
        @save-name="handleChange('Info', 'Name', $event)"
      >
        <template #path>
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
        </template>
      </ScriptBasicInfoCard>
    </template>

    <template #game-config>
      <SectionCard variant="card" :title="t('core.edit.gameConfiguration')" :icon="ControlOutlined">
        <a-row :gutter="24">
          <a-col :xs="24" :md="12">
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
          <a-col :xs="24" :md="12">
            <a-form-item>
              <template #label>
                <FieldLabelWithHint
                  :text="t('core.edit.bettergiAccountSwitchMethod')"
                  :hint="t('core.edit.bettergiAccountSwitchMethodHint')"
                  variant="form"
                />
              </template>
              <a-segmented
                :value="bettergiConfig.Run.AccountSwitchMethod"
                :options="accountSwitchOptions"
                block
                @change="handleAccountSwitchMethodChange"
              />
              <span class="control-hint">{{ t('core.edit.accountSwitch16x9Only') }}</span>
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="[24, 12]">
          <a-col :xs="24" :md="12">
            <SwitchTile
              v-model:checked="bettergiConfig.Game.CloseOnFinish"
              :title="t('core.edit.bettergiCloseGameOnFinish')"
              :description="t('core.edit.bettergiCloseGameOnFinishHint')"
              @change="handleChange('Game', 'CloseOnFinish', bettergiConfig.Game.CloseOnFinish)"
            />
          </a-col>
          <a-col :xs="24" :md="12">
            <SwitchTile
              v-model:checked="bettergiConfig.Game.IfAutoUpdate"
              :title="t('core.edit.genshinUpdateAuto')"
              :description="t('core.edit.genshinUpdateAutoHint')"
              @change="handleChange('Game', 'IfAutoUpdate', bettergiConfig.Game.IfAutoUpdate)"
            />
          </a-col>
        </a-row>
      </SectionCard>
    </template>

    <template #run>
      <SectionCard
        variant="card"
        :title="t('core.edit.runConfiguration')"
        :icon="ThunderboltOutlined"
      >
        <ScriptRunLimitsSection
          v-model:hard-time-limit="bettergiConfig.Run.HardTimeLimit"
          v-model:daily-limit="bettergiConfig.Run.ProxyTimesLimit"
          v-model:retry-limit="bettergiConfig.Run.RunTimesLimit"
          v-model:timeout="bettergiConfig.Run.RunTimeLimit"
          :retry-hint="t('core.edit.bettergiRetryLimitHint')"
          :timeout-hint="t('core.edit.bettergiRunTimeoutHint')"
          enhanced
          @save="key => handleChange('Run', key, bettergiConfig.Run[key])"
        />
      </SectionCard>
    </template>

    <template #program-update>
      <ScriptTakeoverUpdateCard
        v-model:update="bettergiConfig.Update"
        :ready="!pageLoading && !isSaving"
        :title="t('core.edit.bettergiProgramUpdate')"
        :takeover-hint="t('core.edit.bettergiProgramUpdateHint')"
        @save="(key, value) => handleChange('Update', key, value)"
      />
    </template>
  </ScriptEditLayout>
</template>

<script setup lang="ts">
import { ControlOutlined, ThunderboltOutlined } from '@ant-design/icons-vue'
import ScriptTakeoverUpdateCard from './components/ScriptTakeoverUpdateCard.vue'
import type { BetterGIConfig_Update } from '@/api'
import ScriptRunLimitsSection from './components/ScriptRunLimitsSection.vue'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import PathPickerField from '@/components/PathPickerField.vue'
import ScriptBasicInfoCard from '@/components/ScriptBasicInfoCard.vue'
import ScriptEditLayout from '@/components/ScriptEditLayout.vue'
import { SectionCard, SwitchTile } from '@/components/ui'
import { MAS_DOC_URLS } from '@/utils/openExternal'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { useConfirm } from '@/composables/useConfirm'
import { useScriptApi } from '@/composables/useScriptApi'
import { useScriptSaveMutation } from '@/composables/useScriptSaveMutation'

const { t } = useI18n()
const { alert } = useConfirm()
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

const accountSwitchOptions = computed(() => [
  { label: t('core.edit.bettergiAccountSwitchMethodBgi'), value: 'BGI' },
  { label: t('core.edit.bettergiAccountSwitchMethodMas'), value: 'MAS' },
])

const handleAccountSwitchMethodChange = (value: string | number) => {
  const next = value as typeof bettergiConfig.Run.AccountSwitchMethod
  bettergiConfig.Run.AccountSwitchMethod = next
  void handleChange('Run', 'AccountSwitchMethod', next)
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
    void alert({
      tone: 'error',
      title: t('core.edit.bettergiInvalidDirectory'),
      description: t('core.edit.bettergiExeNotFound', { p0: BGI_EXE_NAME }),
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
