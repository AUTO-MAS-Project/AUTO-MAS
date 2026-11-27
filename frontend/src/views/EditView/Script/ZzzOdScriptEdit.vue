<template>
  <ScriptEditLayout
    :script-id="scriptId"
    :loading="pageLoading"
    :header="{ scriptType: 'ZzzOd', title: t('core.edit.editScript') }"
    :form="{ model: formData, rules }"
    :body-form="{ model: formData }"
    :form-label="t('core.edit.zzzodScriptConfiguration')"
    @cancel="handleCancel"
  >
    <template #basic>
      <ScriptBasicInfoCard
        v-model:name="formData.name"
        :name-hint="t('core.edit.zzzodScriptNameHint')"
        @save-name="handleChange('Info', 'Name', $event)"
      >
        <template #path>
          <a-form-item name="path" :rules="rules.path">
            <template #label>
              <FieldLabelWithHint
                :text="t('core.edit.zzzodRootPath')"
                :hint="t('core.edit.zzzodRootPathHint')"
                variant="form"
              />
            </template>
            <PathPickerField
              v-model="formData.path"
              mode="folder"
              :placeholder="t('core.edit.zzzodRootPathPlaceholder')"
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
                  :text="t('core.edit.zzzodGamePath')"
                  :hint="t('core.edit.zzzodGamePathHint')"
                  variant="form"
                />
              </template>
              <BoundGamePathField />
            </a-form-item>
          </a-col>
          <a-col :xs="24" :md="12">
            <a-form-item>
              <template #label>
                <FieldLabelWithHint
                  :text="t('core.edit.zzzodAccountSwitch')"
                  :hint="t('core.edit.zzzodAccountSwitchHint')"
                  variant="form"
                />
              </template>
              <a-select
                v-model:value="zzzodConfig.Game.AccountSwitch"
                :options="accountSwitchOptions"
                style="width: 100%"
                @change="handleChange('Game', 'AccountSwitch', zzzodConfig.Game.AccountSwitch)"
              >
                <!-- 逐选项悬停提示：鼠标停在哪个选项上就显示哪个的说明 -->
                <template #option="{ label, hint }">
                  <a-tooltip :title="hint" placement="right" :mouse-enter-delay="0.3">
                    <div class="account-switch-option">{{ label }}</div>
                  </a-tooltip>
                </template>
              </a-select>
              <span class="control-hint">
                {{
                  t('core.edit.accountSwitch16x9ArgHint', {
                    p0: '-screen-width 1920 -screen-height 1080',
                  })
                }}
              </span>
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="24">
          <a-col :xs="24" :md="12">
            <a-form-item>
              <template #label>
                <FieldLabelWithHint
                  :text="t('core.edit.launchArguments')"
                  :hint="t('core.edit.zzzodGameArgumentsHint')"
                  variant="form"
                />
              </template>
              <a-input
                v-model:value="zzzodConfig.Game.Arguments"
                :placeholder="t('core.edit.enterGameLaunchArguments')"
                style="width: 100%"
                :disabled="!zzzodConfig.Game.Enabled"
                @blur="handleChange('Game', 'Arguments', zzzodConfig.Game.Arguments)"
              />
            </a-form-item>
          </a-col>
          <a-col :xs="24" :md="12">
            <a-form-item>
              <template #label>
                <FieldLabelWithHint
                  :text="t('core.edit.startupWait')"
                  :hint="t('core.edit.howLongWaitAfter')"
                  variant="form"
                />
              </template>
              <a-input-number
                v-model:value="zzzodConfig.Game.WaitTime"
                :min="0"
                :max="9999"
                style="width: 100%"
                :disabled="!zzzodConfig.Game.Enabled"
                @blur="handleChange('Game', 'WaitTime', zzzodConfig.Game.WaitTime)"
              />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="[24, 12]">
          <a-col :xs="24" :md="12">
            <SwitchTile
              v-model:checked="zzzodConfig.Game.Enabled"
              :title="t('core.edit.enableGameConfiguration')"
              :description="t('core.edit.masTakesOverStarting')"
              @change="handleChange('Game', 'Enabled', zzzodConfig.Game.Enabled)"
            />
          </a-col>
          <a-col :xs="24" :md="12">
            <SwitchTile
              v-model:checked="zzzodConfig.Game.LaunchBeforeTask"
              :title="t('core.edit.launchGameBeforeTask')"
              :description="t('core.edit.zzzodLaunchBeforeTaskHint')"
              :disabled="!zzzodConfig.Game.Enabled"
              @change="handleChange('Game', 'LaunchBeforeTask', zzzodConfig.Game.LaunchBeforeTask)"
            />
          </a-col>
          <a-col :xs="24" :md="12">
            <SwitchTile
              v-model:checked="zzzodConfig.Game.CloseOnFinish"
              :title="t('core.edit.zzzodCloseGameOnFinish')"
              :description="t('core.edit.zzzodCloseGameOnFinishHint')"
              @change="handleChange('Game', 'CloseOnFinish', zzzodConfig.Game.CloseOnFinish)"
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
          v-model:hard-time-limit="zzzodConfig.Run.HardTimeLimit"
          v-model:daily-limit="zzzodConfig.Run.ProxyTimesLimit"
          v-model:retry-limit="zzzodConfig.Run.RunTimesLimit"
          v-model:timeout="zzzodConfig.Run.RunTimeLimit"
          :retry-hint="t('core.edit.zzzodRetryLimitHint')"
          :timeout-hint="t('core.edit.zzzodRunTimeoutHint')"
          enhanced
          @save="key => handleChange('Run', key, zzzodConfig.Run[key])"
        />
      </SectionCard>
    </template>

    <template #advanced>
      <!-- 实例槽管理：脚本级诊断（槽目录按安装目录归池、跨脚本共享），默认折叠 -->
      <ZzzOdSlotManage :script-id="scriptId" />
    </template>
  </ScriptEditLayout>
</template>

<script setup lang="ts">
import { ControlOutlined, ThunderboltOutlined } from '@ant-design/icons-vue'
import BoundGamePathField from '@/components/BoundGamePathField.vue'

import ScriptRunLimitsSection from './components/ScriptRunLimitsSection.vue'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import ScriptBasicInfoCard from '@/components/ScriptBasicInfoCard.vue'
import ScriptEditLayout from '@/components/ScriptEditLayout.vue'
import PathPickerField from '@/components/PathPickerField.vue'
import { SectionCard, SwitchTile } from '@/components/ui'
import ZzzOdSlotManage from './ZzzOdSlotManage.vue'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { useConfirm } from '@/composables/useConfirm'
import { useScriptApi } from '@/composables/useScriptApi'
import { useScriptSaveMutation } from '@/composables/useScriptSaveMutation'

const { t } = useI18n()
const { alert } = useConfirm()
const logger = window.electronAPI.getLogger('ZZZ-OD脚本编辑')
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

// ══ ZZZ-OD 项目结构常量（需与 app/task/ZzzOd/AutoProxy.py 的 _ZZZOD_LAUNCHERS 保持同步）══
const ZZZOD_LAUNCHER_NAMES = ['OneDragon-RuntimeLauncher.exe', 'OneDragon-Launcher.exe']

interface ZzzOdInfoForm {
  Name: string
  RootPath: string
}

interface ZzzOdRunForm {
  HardTimeLimit: number
  ProxyTimesLimit: number
  RunTimesLimit: number
  RunTimeLimit: number
}

interface ZzzOdGameForm {
  Enabled: boolean
  LaunchBeforeTask: boolean
  Path: string
  Arguments: string
  WaitTime: number
  CloseOnFinish: boolean
  AccountSwitch: '单实例切换' | '多实例切换' | 'MAS切换'
}

interface ZzzOdScriptConfigForm {
  Info: ZzzOdInfoForm
  Run: ZzzOdRunForm
  Game: ZzzOdGameForm
}

const formData = reactive({
  name: '',
  get path() {
    return zzzodConfig.Info.RootPath
  },
  set path(value: string) {
    zzzodConfig.Info.RootPath = value
  },
})

const zzzodConfig = reactive<ZzzOdScriptConfigForm>({
  Info: { Name: '', RootPath: '.' },
  Run: { HardTimeLimit: 120, ProxyTimesLimit: 0, RunTimesLimit: 3, RunTimeLimit: 180 },
  Game: {
    Enabled: false,
    LaunchBeforeTask: false,
    Path: '',
    Arguments: '',
    WaitTime: 60,
    CloseOnFinish: true,
    AccountSwitch: '单实例切换',
  },
})

// 账号切换方式（value 为后端 Game.AccountSwitch 取值，驱动逻辑需保持原样；label 走词表）
// hint 为逐选项悬停提示（下拉里鼠标停在哪个选项就显示哪个的说明）
const accountSwitchOptions = [
  {
    label: t('core.edit.zzzodAccountSwitchSingle'),
    value: '单实例切换',
    hint: t('core.edit.zzzodAccountSwitchSingleHint'),
  },
  {
    label: t('core.edit.zzzodAccountSwitchMulti'),
    value: '多实例切换',
    hint: t('core.edit.zzzodAccountSwitchMultiHint'),
  },
  {
    label: t('core.edit.zzzodAccountSwitchMas'),
    value: 'MAS切换',
    hint: t('core.edit.zzzodAccountSwitchMasHint'),
    disabled: true,
  },
]

const rules = computed(() => ({
  name: [{ required: true, message: t('core.edit.enterScriptName'), trigger: 'blur' }],
  path: [{ required: true, message: t('core.edit.zzzodRootPathRequired'), trigger: 'blur' }],
}))

const handleCancel = () => router.push('/scripts')

const applyRootPathDefaults = async (rootPath: string) => {
  if (!rootPath || rootPath === '.') {
    message.warning(t('core.edit.pickScriptRootDirectory'))
    return false
  }
  const norm = rootPath.replace(/\\/g, '/').replace(/\/+$/g, '')
  const previousPath = zzzodConfig.Info.RootPath
  zzzodConfig.Info.RootPath = norm

  return enqueue(async () => {
    try {
      const success = await updateScript(scriptId, {
        Info: { RootPath: norm },
      })
      if (success) {
        message.success(t('core.edit.zzzodRootPathSaved'))
        return true
      }
      zzzodConfig.Info.RootPath = previousPath
      return false
    } catch (error) {
      zzzodConfig.Info.RootPath = previousPath
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
    if (detail.type !== 'ZzzOd') {
      message.error(t('core.edit.zzzodNotZzzodScript'))
      handleCancel()
      return
    }
    formData.name = detail.name
    const config = detail.config as Partial<ZzzOdScriptConfigForm>
    Object.assign(zzzodConfig.Info, config.Info || {})
    Object.assign(zzzodConfig.Run, config.Run || {})
    Object.assign(zzzodConfig.Game, config.Game || {})
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
  // 任一启动器存在即视为有效安装目录（RuntimeLauncher / 旧安装器 Launcher）
  const launcherChecks = await Promise.all(
    ZZZOD_LAUNCHER_NAMES.map(name => window.electronAPI.fileExists(`${normalized}/${name}`))
  )
  if (!launcherChecks.some(Boolean)) {
    void alert({
      tone: 'error',
      title: t('core.edit.zzzodInvalidDirectory'),
      description: t('core.edit.zzzodLauncherNotFound', {
        p0: ZZZOD_LAUNCHER_NAMES[0],
        p1: ZZZOD_LAUNCHER_NAMES[1],
      }),
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
