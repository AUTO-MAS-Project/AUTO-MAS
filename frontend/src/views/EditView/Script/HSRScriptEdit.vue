<template>
  <ScriptEditHeader script-type="HSR" :title="t('edit.editHsrScript')" @cancel="handleCancel" />

  <div class="script-edit-content">
    <a-card :title="t('edit.hsrScriptConfiguration')" :loading="pageLoading" class="config-card">
      <template #extra>
        <a-tag color="purple" class="type-tag">{{ t('edit.hsrMarch7thSra') }}</a-tag>
      </template>

      <a-alert
        v-if="capabilitySnapshot?.unavailable_reason && !visibleCapabilityWarnings.length"
        type="warning"
        show-icon
        :message="capabilitySnapshot.unavailable_reason"
        style="margin-bottom: 12px"
      />
      <a-alert
        v-for="warning in visibleCapabilityWarnings"
        :key="warning"
        type="warning"
        show-icon
        :message="warning"
        style="margin-bottom: 12px"
      />

      <a-form ref="formRef" :model="formData" layout="vertical" class="config-form">
        <!-- 脚本名称 -->
        <div class="form-section">
          <div class="section-header">
            <h3>{{ t('edit.basicInfo') }}</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="24">
              <a-form-item>
                <template #label>
                  <a-tooltip :title="t('edit.giveHsrScriptName')">
                    <span class="form-label">
                      {{ t('edit.scriptName') }}
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input
                  v-model:value="formData.infoName"
                  :placeholder="t('edit.enterScriptName')"
                  size="large"
                  @blur="handleChange('Info', 'Name', formData.infoName)"
                />
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <a-alert
          type="info"
          show-icon
          class="user-control-notice"
          :message="t('edit.runModeTaskConfiguration')"
          :description="t('edit.userPageChooseMas')"
        />

        <!-- M7A / SRA / 游戏路径 -->
        <div class="form-section">
          <div class="section-header">
            <h3>{{ t('edit.scriptGameConfiguration') }}</h3>
          </div>
          <div class="engine-path-hint">
            <a-typography-text type="secondary">
              {{ t('edit.fillingPathEnablesThat') }}
            </a-typography-text>
          </div>
          <a-row :gutter="24">
            <a-col :xs="24" :lg="8">
              <a-form-item>
                <template #label>
                  <a-tooltip :title="t('edit.turnThisOffWhen')">
                    <span class="form-label">
                      {{ t('edit.masManagesGame') }}
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-select
                  :value="hsrConfig.Game.Enabled"
                  size="large"
                  @change="handleGameEnabledChange"
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
                  <a-tooltip :title="t('edit.march7thAssistantInstallDirectory')">
                    <span class="form-label">
                      {{ t('edit.march7thPath') }}
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input-group compact class="path-input-group">
                  <a-input
                    v-model:value="hsrConfig.Info.M7APath"
                    :placeholder="t('edit.pickMarch7thFolderContains')"
                    size="large"
                    class="path-input"
                    readonly
                  />
                  <a-button size="large" class="path-button" @click="selectPath('M7APath')">
                    <template #icon>
                      <FolderOpenOutlined />
                    </template>
                    {{ t('edit.pickFolder') }}
                  </a-button>
                  <a-button
                    v-if="hsrConfig.Info.M7APath"
                    :title="t('edit.clearMarch7thPath')"
                    size="large"
                    class="path-clear-button"
                    @click="clearPath('M7APath')"
                  >
                    ×
                  </a-button>
                </a-input-group>
              </a-form-item>
            </a-col>

            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <a-tooltip :title="t('edit.starrailassistantInstallDirectoryContain')">
                    <span class="form-label">
                      {{ t('edit.sraPath') }}
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input-group compact class="path-input-group">
                  <a-input
                    v-model:value="hsrConfig.Info.SRAPath"
                    :placeholder="t('edit.pickSraFolderContains')"
                    size="large"
                    class="path-input"
                    readonly
                  />
                  <a-button size="large" class="path-button" @click="selectPath('SRAPath')">
                    <template #icon>
                      <FolderOpenOutlined />
                    </template>
                    {{ t('edit.pickFolder') }}
                  </a-button>
                  <a-button
                    v-if="hsrConfig.Info.SRAPath"
                    :title="t('edit.clearSraPath')"
                    size="large"
                    class="path-clear-button"
                    @click="clearPath('SRAPath')"
                  >
                    ×
                  </a-button>
                </a-input-group>
              </a-form-item>
            </a-col>
          </a-row>

          <a-row :gutter="24">
            <a-col :span="12" :offset="12">
              <a-form-item>
                <template #label>
                  <a-tooltip :title="t('edit.sraProfileTooltip')">
                    <span class="form-label">
                      {{ t('edit.sraProfile') }}
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-select
                  :value="hsrConfig.Info.SRAProfile || ''"
                  :options="sraProfileOptions"
                  :disabled="Boolean(sraProfileDisabledReason)"
                  :loading="sraProfilesLoading"
                  size="large"
                  style="width: 100%"
                  @change="handleSraProfileChange"
                />
                <a-typography-text
                  v-if="sraProfileDisabledReason"
                  type="secondary"
                  class="field-hint"
                >
                  {{ sraProfileDisabledReason }}
                </a-typography-text>
                <a-typography-text
                  v-else-if="sraProfiles?.fallback && sraProfiles.fallback_reason"
                  type="warning"
                  class="field-hint"
                >
                  {{ sraProfiles.fallback_reason }}
                </a-typography-text>
              </a-form-item>
            </a-col>
          </a-row>

          <a-row :gutter="24" style="margin-top: 16px">
            <a-col :xs="24" :lg="16">
              <a-form-item>
                <template #label>
                  <a-tooltip :title="t('edit.starRailGameRoot')">
                    <span class="form-label">
                      {{ t('edit.gamePath') }}
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input-group compact class="path-input-group">
                  <a-input
                    v-model:value="hsrConfig.Game.Path"
                    :placeholder="t('edit.pickStarRailInstall')"
                    size="large"
                    class="path-input"
                    readonly
                  />
                  <a-button size="large" class="path-button" @click="selectPath('Game.Path')">
                    <template #icon>
                      <FolderOpenOutlined />
                    </template>
                    {{ t('edit.pickFolder') }}
                  </a-button>
                </a-input-group>
              </a-form-item>
            </a-col>
            <a-col :xs="24" :lg="8">
              <a-form-item>
                <template #label>
                  <a-tooltip :title="t('edit.howLongMasWaits')">
                    <span class="form-label">
                      {{ t('edit.maximumGameLaunchWait') }}
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input-number
                  v-model:value="hsrConfig.Game.WaitTime"
                  :min="0"
                  :max="9999"
                  :addon-after="t('edit.seconds')"
                  size="large"
                  style="width: 100%"
                  @change="handleGameConfigChange('WaitTime', $event)"
                />
              </a-form-item>
            </a-col>
          </a-row>

          <a-row :gutter="24" style="margin-top: 16px">
            <a-col :xs="24" :lg="12">
              <a-form-item>
                <template #label>
                  <a-tooltip :title="t('edit.writtenCurrentUserS')">
                    <span class="form-label">
                      {{ t('edit.run1920x1080WindowedMode') }}
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <div class="game-toggle-option">
                  <a-switch
                    :checked="hsrConfig.Game.ForceResolution1920x1080"
                    @change="handleGameResolutionChange"
                  />
                  <a-typography-text type="secondary">{{
                    t('edit.restoreOriginalRegistryValue')
                  }}</a-typography-text>
                </div>
              </a-form-item>
            </a-col>
            <a-col :xs="24" :lg="12">
              <a-form-item>
                <template #label>
                  <a-tooltip :title="t('edit.runsOncePerUser')">
                    <span class="form-label">
                      {{ t('edit.redeemCodesRunOnly') }}
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <div class="game-toggle-option">
                  <a-switch
                    :checked="hsrConfig.Game.RedeemCodesOnlyWhenChanged"
                    @change="handleRedeemCodePolicyChange"
                  />
                  <a-typography-text type="secondary">{{
                    t('edit.runOnceNewUser')
                  }}</a-typography-text>
                </div>
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <!-- 执行限制 -->
        <div class="form-section">
          <div class="section-header">
            <h3>{{ t('edit.runLimits') }}</h3>
          </div>
          <a-row :gutter="16">
            <a-col :span="12">
              <a-form-item :label="t('edit.maximumAttemptsFailedTask')">
                <a-input-number
                  v-model:value="hsrConfig.Run.RunTimesLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @change="handleRunConfigChange('RunTimesLimit', $event)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item :label="t('edit.dailyTaskTimeoutMinutes')">
                <a-input-number
                  v-model:value="hsrConfig.Run.DailyTimeLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @change="handleRunConfigChange('DailyTimeLimit', $event)"
                />
              </a-form-item>
            </a-col>
          </a-row>
          <a-row :gutter="16">
            <a-col :span="12">
              <a-form-item :label="t('edit.weeklyTaskTimeoutMinutes')">
                <a-input-number
                  v-model:value="hsrConfig.Run.WeeklyTimeLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @change="handleRunConfigChange('WeeklyTimeLimit', $event)"
                />
              </a-form-item>
            </a-col>
          </a-row>
          <a-row :gutter="16">
            <a-col :span="12">
              <a-form-item :label="t('edit.enableLowPerformanceCompatibility')">
                <a-switch
                  v-model:checked="hsrConfig.Run.LowPerformanceMode"
                  :disabled="!hsrConfig.Info.M7APath"
                  @change="handleRunConfigChange('LowPerformanceMode', $event)"
                />
                <div class="form-item-hint">
                  {{ t('edit.appliesMarch7thDivergentUniverse') }}
                </div>
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
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import { FolderOpenOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import ScriptEditHeader from '@/components/ScriptEditHeader.vue'
import { useScriptApi } from '@/composables/useScriptApi'
import {
  filterHSRCapabilityWarnings,
  useHSRPluginApi,
  type HSRCapabilitySnapshot,
  type HSREngine,
  type HSRSRAProfilesSnapshot,
} from '@/composables/useHSRPluginApi'
import type { HSRConfig_Info, HSRConfig_Game, HSRConfig_Run } from '@/api'
import type { HSRScriptConfig } from '@/types/script'

const { t } = useI18n()

// HSR 内部非空 reactive 形态（OpenAPI 生成类型字段全部为 optional | null，
// 前端实际为非空；通过该形态消除 strict null 警告）。
type HSRConfigData = {
  Info: HSRConfig_Info
  Game: HSRConfig_Game & {
    Enabled?: boolean | null
    ForceResolution1920x1080?: boolean | null
    RedeemCodesOnlyWhenChanged?: boolean | null
  }
  Run: HSRConfig_Run
}

const logger = window.electronAPI.getLogger('HSR 脚本编辑')

const route = useRoute()
const router = useRouter()
const { getScript, updateScript } = useScriptApi()
const hsrPluginApi = useHSRPluginApi()

const pageLoading = ref(false)
const scriptId = route.params.id as string
const isInitializing = ref(true)
const isSaving = ref(false)
const capabilitySnapshot = ref<HSRCapabilitySnapshot | null>(null)
const visibleCapabilityWarnings = computed(() =>
  filterHSRCapabilityWarnings(capabilitySnapshot.value?.warnings)
)

// SRA 配置档案：%APPDATA%/SRA/configs 下的多份 json，脚本选一份供托管表单、直控与导入快照共用。
const sraProfiles = ref<HSRSRAProfilesSnapshot | null>(null)
const sraProfilesLoading = ref(false)
const sraProfilesError = ref('')

const formData = reactive({
  infoName: '',
})

const hsrConfig = reactive<HSRConfigData>({
  Info: { Name: '', M7APath: '', SRAPath: '', SRAProfile: '' },
  Game: {
    Enabled: true,
    Path: '',
    WaitTime: 60,
    ForceResolution1920x1080: false,
    RedeemCodesOnlyWhenChanged: true,
  },
  Run: {
    RunTimesLimit: 3,
    DailyTimeLimit: 20,
    WeeklyTimeLimit: 60,
    LowPerformanceMode: false,
  },
})

// 需要后端语义化校正（DPAPI 加解密、路径规范化等）的字段保存后再 GET 拉回；
// 其余纯本地赋值字段不重复请求，避免覆盖用户刚改的值。
const FIELDS_REQUIRE_REFRESH_AFTER_SAVE = new Set<string>([
  'Info.Name',
  'Info.M7APath',
  'Info.SRAPath',
  'Info.SRAProfile',
  'Game.Path',
])

const handleChange = async (category: string, key: string, value: any): Promise<boolean> => {
  if (isInitializing.value || isSaving.value) return false
  isSaving.value = true
  try {
    const updateData: any = { [category]: { [key]: value } }
    const success = await updateScript(scriptId, updateData)
    if (!success) return false
    logger.info(`配置已保存: ${category}.${key}`)
    if (FIELDS_REQUIRE_REFRESH_AFTER_SAVE.has(`${category}.${key}`)) {
      await refreshScript()
      await loadCapabilities()
      await loadSraProfiles()
    }
    return true
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存失败: ${errorMsg}`)
    return false
  } finally {
    isSaving.value = false
  }
}

const refreshScript = async () => {
  try {
    const scriptDetail = await getScript(scriptId)
    if (!scriptDetail) return
    formData.infoName = scriptDetail.name
    const cfg = scriptDetail.config as HSRScriptConfig
    if (cfg.Info) Object.assign(hsrConfig.Info, cfg.Info)
    if (cfg.Game) {
      Object.assign(hsrConfig.Game, cfg.Game)
      if (hsrConfig.Game.Enabled === undefined || hsrConfig.Game.Enabled === null) {
        hsrConfig.Game.Enabled = true
      }
      if (hsrConfig.Game.WaitTime === undefined || hsrConfig.Game.WaitTime === null) {
        hsrConfig.Game.WaitTime = 60
      }
      if (
        hsrConfig.Game.ForceResolution1920x1080 === undefined ||
        hsrConfig.Game.ForceResolution1920x1080 === null
      ) {
        hsrConfig.Game.ForceResolution1920x1080 = false
      }
      if (
        hsrConfig.Game.RedeemCodesOnlyWhenChanged === undefined ||
        hsrConfig.Game.RedeemCodesOnlyWhenChanged === null
      ) {
        hsrConfig.Game.RedeemCodesOnlyWhenChanged = true
      }
    }
    if (cfg.Run) {
      Object.assign(hsrConfig.Run, cfg.Run)
      if (hsrConfig.Run.RunTimesLimit === undefined) hsrConfig.Run.RunTimesLimit = 3
      if (hsrConfig.Run.DailyTimeLimit === undefined) hsrConfig.Run.DailyTimeLimit = 20
      if (hsrConfig.Run.WeeklyTimeLimit === undefined) hsrConfig.Run.WeeklyTimeLimit = 60
      if (hsrConfig.Run.LowPerformanceMode === undefined) hsrConfig.Run.LowPerformanceMode = false
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`刷新配置失败: ${errorMsg}`)
  }
}

const handleRunConfigChange = async (key: string, value: any) => {
  if (isInitializing.value || isSaving.value) return
  isSaving.value = true
  try {
    const updateData: any = { Run: { [key]: value } }
    const success = await updateScript(scriptId, updateData)
    if (!success) return
    logger.info(`配置已保存: Run.${key}`)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存失败: ${errorMsg}`)
  } finally {
    isSaving.value = false
  }
}

const handleGameConfigChange = async (key: 'WaitTime', value: number | null) => {
  if (isInitializing.value || isSaving.value) return
  const normalizedValue = value ?? 60
  hsrConfig.Game[key] = normalizedValue
  await handleChange('Game', key, normalizedValue)
}

const handleGameEnabledChange = async (value: boolean | string | number) => {
  if (isInitializing.value || isSaving.value) return
  const previousValue = hsrConfig.Game.Enabled ?? true
  const enabled = Boolean(value)
  hsrConfig.Game.Enabled = enabled
  const saved = await handleChange('Game', 'Enabled', enabled)
  if (!saved) {
    hsrConfig.Game.Enabled = previousValue
    await refreshScript()
  }
}

const handleGameResolutionChange = async (value: boolean | string | number) => {
  if (isInitializing.value || isSaving.value) return
  const enabled = Boolean(value)
  hsrConfig.Game.ForceResolution1920x1080 = enabled
  const saved = await handleChange('Game', 'ForceResolution1920x1080', enabled)
  if (!saved) await refreshScript()
}

const handleRedeemCodePolicyChange = async (value: boolean | string | number) => {
  if (isInitializing.value || isSaving.value) return
  const enabled = Boolean(value)
  hsrConfig.Game.RedeemCodesOnlyWhenChanged = enabled
  const saved = await handleChange('Game', 'RedeemCodesOnlyWhenChanged', enabled)
  if (!saved) await refreshScript()
}

// 路径选择时需校验的 exe 名（key -> exe 文件名）
const PATH_VALIDATION: Record<string, string> = {
  M7APath: 'March7th Assistant.exe',
  SRAPath: 'SRA-cli.exe',
  'Game.Path': 'StarRail.exe',
}

const joinPath = (folder: string, fileName: string) =>
  `${folder.replace(/[\\/]+$/g, '')}/${fileName}`

const selectPath = async (key: string) => {
  try {
    if (!window.electronAPI) {
      message.error(t('edit.filePickingUnavailableRun'))
      return
    }
    const path = await window.electronAPI.selectFolder()
    if (!path) return

    // 校验目录下是否存在期望的 exe；校验失败弹 Modal.warning 且不保存
    const expectedExe = PATH_VALIDATION[key]
    if (expectedExe && (key !== 'Game.Path' || hsrConfig.Game.Enabled)) {
      const exePath = joinPath(path, expectedExe)
      const exists = await window.electronAPI.fileExists(exePath)
      if (!exists) {
        Modal.warning({
          title: t('edit.invalidPath'),
          content: `所选目录下未找到 ${expectedExe}，请重新选择正确的安装目录。`,
        })
        return
      }
    }

    // M7APath / SRAPath 属于 Info 分组，Game.Path 属于 Game 分组
    if (key === 'M7APath' || key === 'SRAPath') {
      await handleChange('Info', key, path)
    } else if (key === 'Game.Path') {
      await handleChange('Game', 'Path', path)
    } else {
      logger.warn(`未知的路径 key: ${key}`)
      return
    }
    message.success(t('edit.pathSelected'))
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`选择路径失败: ${errorMsg}`)
    message.error(t('edit.couldNotPickFolder'))
  }
}

const handleCancel = () => {
  router.push('/scripts')
}

// 清空路径：保存空字符串到后端；任务映射在用户页按用户维护。
const clearPath = async (key: string) => {
  if (key === 'M7APath' || key === 'SRAPath') {
    await handleChange('Info', key, '')
    hsrConfig.Info![key] = ''
  }
}

const loadSraProfiles = async () => {
  if (!hsrConfig.Info.SRAPath) {
    sraProfiles.value = null
    sraProfilesError.value = ''
    return
  }
  sraProfilesLoading.value = true
  try {
    sraProfiles.value = await hsrPluginApi.getSraProfiles(scriptId)
    sraProfilesError.value = ''
  } catch (error) {
    sraProfiles.value = null
    sraProfilesError.value = error instanceof Error ? error.message : String(error)
  } finally {
    sraProfilesLoading.value = false
  }
}

// 「自动」始终可选，其余选项来自档案目录；已配置但文件已不存在的档案也列出来，
// 否则下拉会显示成一个空值，用户看不出自己配过什么。
const sraProfileOptions = computed(() => {
  const snapshot = sraProfiles.value
  const options = [
    { value: '', label: t('edit.sraProfileAuto', { name: snapshot?.auto_id || 'Default' }) },
    ...(snapshot?.profiles ?? []).map(profile => ({ value: profile.id, label: profile.id })),
  ]
  const configured = hsrConfig.Info.SRAProfile || ''
  if (configured && !options.some(option => option.value === configured)) {
    options.push({ value: configured, label: configured })
  }
  return options
})

const sraProfileDisabledReason = computed(() => {
  if (!hsrConfig.Info.SRAPath) return t('edit.sraProfileNeedPath')
  if (sraProfilesError.value) {
    return t('edit.sraProfileLoadFailed', { reason: sraProfilesError.value })
  }
  const snapshot = sraProfiles.value
  if (snapshot && !snapshot.available) return snapshot.unavailable_reason || ''
  return ''
})

const handleSraProfileChange = async (value: unknown) => {
  const next = typeof value === 'string' ? value : ''
  const previous = hsrConfig.Info.SRAProfile || ''
  hsrConfig.Info.SRAProfile = next
  const saved = await handleChange('Info', 'SRAProfile', next)
  if (!saved) hsrConfig.Info.SRAProfile = previous
}

const loadCapabilities = async () => {
  try {
    capabilitySnapshot.value = await hsrPluginApi.getCapabilities(scriptId)
  } catch (error) {
    const configuredEngines: HSREngine[] = []
    if (hsrConfig.Info.M7APath) configuredEngines.push('M7A')
    if (hsrConfig.Info.SRAPath) configuredEngines.push('SRA')
    capabilitySnapshot.value = {
      revision: 0,
      available: configuredEngines.length > 0,
      unavailable_reason: configuredEngines.length ? null : '未配置 M7A 或 SRA 路径',
      candidate_engines: configuredEngines,
      configured_engines: configuredEngines,
      effective_engines: configuredEngines,
      supported_modes: ['managed', 'direct'],
      adapters: [],
      tasks: [],
      warnings: [
        `HSR 能力端点不可用，已回退到内置脚本配置：${
          error instanceof Error ? error.message : String(error)
        }`,
      ],
    }
  }
}

onMounted(async () => {
  pageLoading.value = true
  try {
    const scriptDetail = await getScript(scriptId)
    if (!scriptDetail) {
      message.error(t('edit.scriptDoesNotExist'))
      router.push('/scripts')
      return
    }
    await refreshScript()
    await loadCapabilities()
    await loadSraProfiles()
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载脚本失败: ${errorMsg}`)
    message.error(t('edit.couldNotLoadScript'))
    router.push('/scripts')
  } finally {
    pageLoading.value = false
    isInitializing.value = false
  }
})
</script>

<style scoped>
.script-edit-content {
  flex: 1;
}

.config-card {
  border-radius: 16px;
  box-shadow: none;
  border: 1px solid var(--ant-color-border-secondary);
  overflow: hidden;
}

.type-tag {
  font-size: 14px;
  font-weight: 600;
  padding: 8px 16px;
  border-radius: 8px;
  border: none;
}

.config-form {
  max-width: none;
}

.engine-path-hint {
  margin-bottom: 16px;
}

.user-control-notice {
  margin-bottom: 20px;
}

.form-section {
  margin-bottom: 12px;
}

.section-header {
  margin-bottom: 6px;
}

.section-header h3::before {
  background: var(--ant-color-primary);
}

.section-hint {
  color: var(--ant-color-text-secondary);
  font-size: 14px;
  margin: 4px 0 12px 0;
}

.field-hint {
  display: block;
  margin-top: 6px;
  font-size: 13px;
}

.game-toggle-option {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 40px;
}

.form-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: var(--ant-color-text);
  font-size: 14px;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
  cursor: help;
  transition: color 0.3s ease;
}

.help-icon:hover {
  color: var(--ant-color-primary);
}

.path-input-group {
  display: flex;
  border-radius: 8px;
  overflow: hidden;
  border: 2px solid var(--ant-color-border);
  transition: all 0.3s ease;
}

.path-input-group:hover {
  border-color: var(--ant-color-primary-hover);
}

.path-input-group:focus-within {
  border-color: var(--ant-color-primary);
  box-shadow: 0 0 0 4px var(--ant-color-primary-bg);
}

.path-input-group :deep(.path-input.ant-input) {
  flex: 1;
  border: none;
  border-radius: 0;
  background: var(--ant-color-bg-container);
}

.path-input-group :deep(.path-input.ant-input:focus) {
  box-shadow: none;
}

.path-button {
  border: none;
  border-radius: 0;
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-primary);
  font-weight: 600;
  padding: 0 20px;
  transition: all 0.3s ease;
  border-left: 1px solid var(--ant-color-border-secondary);
}

.path-button:hover {
  background: var(--ant-color-primary);
  color: white;
  transform: none;
}

.path-clear-button {
  border: none;
  border-radius: 0;
  background: var(--ant-color-error-bg);
  color: var(--ant-color-error);
  font-weight: 700;
  font-size: 18px;
  padding: 0 16px;
  transition: all 0.3s ease;
  border-left: 1px solid var(--ant-color-border-secondary);
  min-width: 48px;
}

.path-clear-button:hover {
  background: var(--ant-color-error);
  color: white;
}
</style>
