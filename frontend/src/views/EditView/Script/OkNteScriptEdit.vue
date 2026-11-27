<template>
  <ScriptEditLayout
    :script-id="scriptId"
    :loading="pageLoading"
    :header="{ scriptType: 'OkNte', title: t('core.edit.editScript') }"
    :form="{ model: formData, rules }"
    :body-form="{ model: formData }"
    :form-label="t('core.edit.okNteScriptConfiguration')"
    @cancel="handleCancel"
  >
    <template #basic>
      <ScriptBasicInfoCard
        v-model:name="formData.name"
        @save-name="handleChange('Info', 'Name', $event)"
      >
        <template #path>
          <a-form-item name="path" :rules="rules.path">
            <template #label>
              <FieldLabelWithHint :text="t('core.edit.okNtePath')" variant="form" />
            </template>
            <PathPickerField
              v-model="formData.path"
              mode="folder"
              :placeholder="t('core.edit.pickDirectoryHoldingOk')"
              :pick-label="t('core.edit.pickDirectory')"
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
            <a-form-item :label="t('core.edit.launchType')">
              <a-radio-group
                v-model:value="oknteConfig.Game.LaunchMode"
                size="small"
                button-style="solid"
                :disabled="launchModeDisabled"
                @change="handleLaunchModeChange"
              >
                <a-radio-button value="Autoplay">
                  {{ t('core.edit.oknteLaunchDirectly') }}
                </a-radio-button>
                <a-radio-button value="LauncherUi">
                  {{ t('core.edit.oknteLaunchViaLauncher') }}
                </a-radio-button>
              </a-radio-group>
              <span v-if="showLaunchModeHint" class="control-hint">
                {{ t('core.edit.oknteLaunchModeNeedsLaunchBeforeTask') }}
              </span>
            </a-form-item>
          </a-col>
          <a-col :xs="24" :md="12">
            <a-form-item :label="t('core.edit.gamePath')">
              <BoundGamePathField />
            </a-form-item>
          </a-col>
          <a-col :xs="24" :md="12">
            <a-form-item>
              <template #label>
                <FieldLabelWithHint
                  :text="t('core.edit.launchArguments')"
                  :hint="t('core.edit.gameLaunchArgumentsNot')"
                  variant="form"
                />
              </template>
              <a-input
                v-model:value="oknteConfig.Game.Arguments"
                :placeholder="t('core.edit.enterGameLaunchArguments')"
                :disabled="!oknteConfig.Game.Enabled"
                @blur="handleChange('Game', 'Arguments', oknteConfig.Game.Arguments)"
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
                v-model:value="oknteConfig.Game.WaitTime"
                :min="0"
                :max="9999"
                style="width: 100%"
                :disabled="!oknteConfig.Game.Enabled"
                @blur="handleChange('Game', 'WaitTime', oknteConfig.Game.WaitTime)"
              />
            </a-form-item>
          </a-col>
        </a-row>

        <a-alert class="launch-mode-bubble" type="info" show-icon :message="launchModeBubble" />
        <a-row :gutter="[24, 12]" class="switch-row">
          <a-col :xs="24" :md="12">
            <SwitchTile
              v-model:checked="oknteConfig.Game.Enabled"
              :title="t('core.edit.enableGameConfiguration')"
              :description="t('core.edit.masterSwitchGameManagement')"
              @change="handleGameEnabledChange"
            />
          </a-col>
          <a-col :xs="24" :md="12">
            <SwitchTile
              v-model:checked="oknteConfig.Game.LaunchBeforeTask"
              :title="t('core.edit.launchGameBeforeTask')"
              :description="t('core.edit.whetherMasLaunchesGame')"
              :disabled="!oknteConfig.Game.Enabled"
              @change="handleChange('Game', 'LaunchBeforeTask', $event)"
            />
          </a-col>
          <a-col :xs="24" :md="12">
            <SwitchTile
              v-model:checked="oknteConfig.Game.CloseOnFinish"
              :title="t('core.edit.closeGameAfterTask')"
              :description="t('core.edit.whetherMasClosesGame')"
              @change="handleChange('Game', 'CloseOnFinish', $event)"
            />
          </a-col>
          <a-col :xs="24" :md="12">
            <SwitchTile
              v-model:checked="oknteConfig.Game.AccountSwitch"
              :title="t('core.edit.forceSwitchAccountBeforeRun')"
              :description="
                [t('core.edit.oknteAccountSwitchHint'), t('core.edit.accountSwitch16x9Only')].join(
                  ' '
                )
              "
              :disabled="!oknteConfig.Game.Enabled || !oknteConfig.Game.LaunchBeforeTask"
              @change="handleChange('Game', 'AccountSwitch', $event)"
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
          enhanced
          v-model:hard-time-limit="oknteConfig.Run.HardTimeLimit"
          v-model:daily-limit="oknteConfig.Run.ProxyTimesLimit"
          v-model:retry-limit="oknteConfig.Run.RunTimesLimit"
          v-model:timeout="oknteConfig.Run.RunTimeLimit"
          :retry-hint="t('core.edit.giveUpAfterThis')"
          :timeout-hint="t('core.edit.logThatStaysUnchanged')"
          @save="key => handleChange('Run', key, oknteConfig.Run[key])"
        />
      </SectionCard>
    </template>
  </ScriptEditLayout>
</template>

<script setup lang="ts">
import { ControlOutlined, ThunderboltOutlined } from '@ant-design/icons-vue'
import { SectionCard, SwitchTile } from '@/components/ui'
import BoundGamePathField from '@/components/BoundGamePathField.vue'

import ScriptRunLimitsSection from './components/ScriptRunLimitsSection.vue'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import ScriptBasicInfoCard from '@/components/ScriptBasicInfoCard.vue'
import ScriptEditLayout from '@/components/ScriptEditLayout.vue'
import PathPickerField from '@/components/PathPickerField.vue'
import { useI18n } from 'vue-i18n'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import type { RadioChangeEvent } from 'ant-design-vue/es/radio/interface'
import {
  type OkNteConfig,
  type OkNteConfig_Game,
  type OkNteConfig_Info,
  type OkNteConfig_Run,
  type OkNteConfig_Script,
} from '@/api'
import { useScriptApi } from '@/composables/useScriptApi'
import { useScriptSaveMutation } from '@/composables/useScriptSaveMutation'

const { t } = useI18n()

const logger = window.electronAPI.getLogger('OK-NTE脚本编辑')
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

const formData = reactive({
  name: '',
  get path() {
    return oknteConfig.Info.RootPath
  },
  set path(value: string) {
    oknteConfig.Info.RootPath = value
  },
})

type FormSection<T> = { [K in keyof T]-?: NonNullable<T[K]> }

type OkNteFormConfig = {
  Info: FormSection<OkNteConfig_Info>
  Script: FormSection<OkNteConfig_Script>
  Game: FormSection<OkNteConfig_Game>
  Run: FormSection<Omit<OkNteConfig_Run, 'ExecutionSession'>>
}

const oknteConfig = reactive<OkNteFormConfig>({
  Info: { Name: '', RootPath: '.' },
  Script: {
    ScriptPath: '.',
    Arguments: '',
    IfTrackProcess: true,
    TrackProcessName: '',
    TrackProcessExe: '',
    TrackProcessCmdline: '',
    ConfigPath: '.',
    ConfigPathMode: 'Folder',
    UpdateConfigMode: 'Always',
    LogPath: '.',
    LogPathFormat: '',
    LogTimeStart: 1,
    LogTimeEnd: 23,
    LogTimeFormat: '%Y-%m-%d %H:%M:%S,%f',
    SuccessLog: '',
    SuccessLogMode: 'Split',
    ErrorLog: '',
    ErrorLogMode: 'Split',
  },
  Game: {
    Enabled: false,
    LaunchBeforeTask: false,
    LaunchMode: 'Autoplay',
    Type: 'Client',
    Path: '.',
    URL: '',
    ProcessName: '',
    Arguments: '',
    WaitTime: 60,
    IfForceClose: true,
    CloseOnFinish: true,
    AccountSwitch: false,
  },
  Run: { HardTimeLimit: 120, ProxyTimesLimit: 0, RunTimesLimit: 1, RunTimeLimit: 120 },
})

const rules = {
  name: [{ required: true, message: t('core.edit.enterScriptName'), trigger: 'blur' }],
  path: [{ required: true, message: t('core.edit.pickOkNtePath'), trigger: 'blur' }],
}

// 异环游戏路径预设锚点与启动器相对路径（直启 HTGame.exe 会卡界面，必须经启动器）
const NTE_LAUNCHER_DIR = 'NTELauncher'
const NTE_LAUNCHER_EXES = ['NTEGame.exe', 'NTEGlobalGame.exe', 'NTETWGame.exe']
const NTE_CLIENT_EXE = 'htgame.exe'

const showPathRejectModal = (title: string, content: string) => {
  Modal.error({ title, content, okText: t('core.edit.gotIt') })
}

const handleCancel = () => router.push('/scripts')

const handleGameEnabledChange = async (enabled: boolean) => {
  oknteConfig.Game.Enabled = enabled
  await handleChange('Game', 'Enabled', enabled)
}

// 启动方式取值取自生成的 schema 类型（后端 schema.py 的 Literal["Autoplay","LauncherUi"]）
type OkNteLaunchMode = NonNullable<OkNteConfig_Game['LaunchMode']>

const launchModeDisabled = computed(
  () => !oknteConfig.Game.Enabled || !oknteConfig.Game.LaunchBeforeTask || isSaving.value
)
const showLaunchModeHint = computed(
  () => oknteConfig.Game.Enabled && !oknteConfig.Game.LaunchBeforeTask
)

// 启动方式气泡：随所选方式切换，只讲这一种的利弊（替代原灰字介绍 + 底部蓝条）
const launchModeBubble = computed(() =>
  oknteConfig.Game.LaunchMode === 'LauncherUi'
    ? t('core.edit.oknteLaunchBubbleLauncherUi')
    : t('core.edit.oknteLaunchBubbleAutoplay')
)

// 已保存成功的启动方式：保存失败时回滚到它。radio-group 的 change 只在用户操作时触发，
// 回滚赋值不会再触发保存，因此不需要 Okww 那套 persisted/requested 哨兵。
let persistedLaunchMode: OkNteLaunchMode = 'Autoplay'

const handleLaunchModeChange = async (event: RadioChangeEvent) => {
  const value = event.target.value as OkNteLaunchMode
  const previous = persistedLaunchMode
  const success = await enqueue(async () => {
    try {
      const ok = await updateScript(scriptId, { Game: { LaunchMode: value } })
      if (!ok) oknteConfig.Game.LaunchMode = previous
      return ok
    } catch (err) {
      oknteConfig.Game.LaunchMode = previous
      logger.error(err instanceof Error ? err.message : String(err))
      return false
    }
  }).catch(() => false)
  if (!success) {
    message.error(t('core.edit.launchTypeSaveFailed'))
    return
  }
  persistedLaunchMode = value
  logger.info(`配置已保存: Game.LaunchMode=${value}`)
}

const buildAutoPaths = async (rootPath: string) => {
  const norm = rootPath.replace(/\\/g, '/').replace(/\/+$/g, '')
  // 独立 body 包与启动器安装都使用 EXE 所在运行目录存放配置和日志。
  const isBody = await window.electronAPI.fileExists(`${norm}/_internal`)
  const runtimeDir = isBody ? norm : `${norm}/data/apps/ok-nte/working`
  return {
    rootPath: norm,
    scriptPath: `${norm}/ok-nte.exe`,
    configPath: `${runtimeDir}/configs`,
    logPath: `${runtimeDir}/logs/ok-script.log`,
  }
}

const applyRootPathDefaults = async (rootPath: string) => {
  if (!rootPath || rootPath === '.') {
    message.warning(t('core.edit.pickScriptRootDirectory'))
    return
  }
  const { rootPath: norm, scriptPath, configPath, logPath } = await buildAutoPaths(rootPath)
  const scriptDefaults = {
    ScriptPath: scriptPath,
    ConfigPathMode: 'Folder' as const,
    ConfigPath: configPath,
    UpdateConfigMode: 'Always' as const,
    LogPath: logPath,
    LogPathFormat: '',
    IfTrackProcess: true,
    // 留空交给后端按实际本体识别，自动更新切换运行方式后无需重新选目录。
    TrackProcessName: '',
    TrackProcessExe: '',
    TrackProcessCmdline: '',
  }
  await enqueue(async () => {
    const success = await updateScript(scriptId, {
      Info: { RootPath: norm },
      Script: scriptDefaults,
    })
    if (success) {
      oknteConfig.Info.RootPath = norm
      Object.assign(oknteConfig.Script, scriptDefaults)
      message.success(t('core.edit.okNtePathMatched'))
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
    if (detail.type !== 'OkNte') {
      message.error(t('core.edit.scriptTypeNotOk'))
      handleCancel()
      return
    }
    formData.name = detail.name
    const config = detail.config as OkNteConfig
    Object.assign(oknteConfig.Info, config.Info || {})
    Object.assign(oknteConfig.Script, config.Script || {})
    Object.assign(oknteConfig.Game, config.Game || {})
    // schema 字段可选：后端旧配置没有 LaunchMode，回落到默认「直接启动（静默 /autoplay）」
    oknteConfig.Game.LaunchMode = config.Game?.LaunchMode ?? 'Autoplay'
    persistedLaunchMode = oknteConfig.Game.LaunchMode
    Object.assign(oknteConfig.Run, config.Run || {})

    // 旧配置 Game.Path 存的是 HTGame.exe：展示层自动升级为同安装根下的启动器
    // （运行时后端也会按同一规则反推，此处仅为回显正确）
    const gamePath = (oknteConfig.Game.Path || '').replace(/\\/g, '/')
    if (oknteConfig.Game.Enabled && gamePath.toLowerCase().endsWith(`/${NTE_CLIENT_EXE}`)) {
      const clientIdx = gamePath.toLowerCase().lastIndexOf('/client/')
      if (clientIdx !== -1) {
        const installRoot = gamePath.substring(0, clientIdx)
        const candidates = [
          `${installRoot}/NTEGlobalLauncher.exe`,
          ...NTE_LAUNCHER_EXES.map(exe => `${installRoot}/${NTE_LAUNCHER_DIR}/${exe}`),
        ]
        for (const candidate of candidates) {
          if (await window.electronAPI.fileExists(candidate)) {
            oknteConfig.Game.Path = candidate
            break
          }
        }
      }
    }
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
  const exePath = normalized + '/ok-nte.exe'
  if (!(await window.electronAPI.fileExists(exePath))) {
    showPathRejectModal(
      '所选目录无效',
      '所选目录下未找到 ok-nte.exe，请选择包含 ok-nte.exe 的 OK-NTE 脚本根目录。'
    )
    return
  }
  await applyRootPathDefaults(normalized)
}

const saveGameLauncher = async (path: string) => {
  await enqueue(async () => {
    if (await updateScript(scriptId, { Game: { Path: path, Type: 'Client' } })) {
      oknteConfig.Game.Path = path
      oknteConfig.Game.Type = 'Client'
      message.success(t('core.edit.gamePathMatchedHtgame'))
    }
  })
}

onMounted(loadScript)
</script>

<style scoped src="@/styles/scriptEditForm.css"></style>

<style scoped>
.switch-row {
  margin-bottom: 12px;
}

.launch-mode-bubble {
  margin-bottom: 12px;
}
</style>
