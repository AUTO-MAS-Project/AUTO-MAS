<template>
  <ScriptEditHeader
    script-type="HSR"
    :title="t('core.edit.editHsrScript')"
    @cancel="handleCancel"
  />

  <ConfigLockPanel :script-id="scriptId" content-class="script-edit-content">
    <a-card
      :title="t('core.edit.hsrScriptConfiguration')"
      :loading="pageLoading"
      class="config-card"
    >
      <template #extra>
        <a-tag color="purple" class="type-tag">{{ t('core.edit.hsrMarch7thSra') }}</a-tag>
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
            <h3>{{ t('core.edit.basicInfo') }}</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="24">
              <a-form-item>
                <template #label>
                  <FieldLabelWithHint
                    :text="t('core.edit.scriptName')"
                    :hint="t('core.edit.giveHsrScriptName')"
                    variant="form"
                  />
                </template>
                <a-input
                  v-model:value="formData.infoName"
                  :placeholder="t('core.edit.enterScriptName')"
                  size="large"
                  @blur="handleChange('Info', 'Name', formData.infoName)"
                />
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <!-- M7A / SRA / 游戏路径 -->
        <div class="form-section">
          <div class="section-header">
            <h3>{{ t('core.edit.scriptGameConfiguration') }}</h3>
          </div>
          <a-alert
            v-if="isCloud"
            type="info"
            show-icon
            :message="t('core.edit.hsrCloudIntro')"
            class="cloud-intro"
          />
          <div class="engine-path-hint">
            <a-typography-text type="secondary">
              {{ t('core.edit.fillingPathEnablesThat') }}
            </a-typography-text>
          </div>
          <a-row :gutter="24">
            <a-col :xs="24" :lg="8">
              <a-form-item>
                <template #label>
                  <FieldLabelWithHint
                    :text="t('core.edit.hsrGamePlatform')"
                    :hint="t('core.edit.hsrGamePlatformTip')"
                    variant="form"
                  />
                </template>
                <a-segmented
                  :value="hsrConfig.Game.Platform"
                  :options="platformOptions"
                  data-testid="hsr-game-platform"
                  @change="handlePlatformChange"
                />
              </a-form-item>
            </a-col>
            <!-- 云·星穹铁道没有本地客户端，「MAS 管理游戏」及其下属字段整块不渲染 -->
            <a-col v-if="!isCloud" :xs="24" :lg="8">
              <a-form-item>
                <template #label>
                  <FieldLabelWithHint
                    :text="t('core.edit.masManagesGame')"
                    :hint="t('core.edit.turnThisOffWhen')"
                    variant="form"
                  />
                </template>
                <a-switch
                  :checked="Boolean(hsrConfig.Game.Enabled)"
                  @change="handleGameEnabledChange"
                />
              </a-form-item>
            </a-col>
          </a-row>
          <a-row :gutter="24">
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <FieldLabelWithHint
                    :text="t('core.edit.march7thPath')"
                    :hint="t('core.edit.march7thAssistantInstallDirectory')"
                    variant="form"
                  />
                </template>
                <PathPickerField
                  v-model="hsrConfig.Info.M7APath"
                  mode="folder"
                  :placeholder="t('core.edit.pickMarch7thFolderContains')"
                  :pick-label="t('core.edit.pickFolder')"
                  @pick="selectPath('M7APath')"
                >
                  <template #after-pick>
                    <a-button
                      v-if="hsrConfig.Info.M7APath"
                      :title="t('core.edit.clearMarch7thPath')"
                      size="large"
                      class="path-clear-button"
                      @click="clearPath('M7APath')"
                    >
                      ×
                    </a-button>
                  </template>
                </PathPickerField>
              </a-form-item>
            </a-col>

            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <FieldLabelWithHint
                    :text="t('core.edit.sraPath')"
                    :hint="t('core.edit.starrailassistantInstallDirectoryContain')"
                    variant="form"
                  />
                </template>
                <PathPickerField
                  v-model="hsrConfig.Info.SRAPath"
                  mode="folder"
                  :placeholder="t('core.edit.pickSraFolderContains')"
                  :pick-label="t('core.edit.pickFolder')"
                  @pick="selectPath('SRAPath')"
                >
                  <template #after-pick>
                    <a-button
                      v-if="hsrConfig.Info.SRAPath"
                      :title="t('core.edit.clearSraPath')"
                      size="large"
                      class="path-clear-button"
                      @click="clearPath('SRAPath')"
                    >
                      ×
                    </a-button>
                  </template>
                </PathPickerField>
                <!-- 云平台保留 SRA 路径（外部脚本更新照常），但任务不经 SRA -->
                <a-typography-text v-if="isCloud" type="secondary" class="field-hint">
                  {{ t('core.edit.hsrCloudNoSra') }}
                </a-typography-text>
              </a-form-item>
            </a-col>
          </a-row>

          <!-- 云·星穹铁道：付费时长、排队与登录等待，映射到三月七的 cloud_game_* -->
          <a-row v-if="isCloud" :gutter="24" style="margin-top: 16px">
            <a-col :xs="24" :lg="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">{{ t('core.edit.hsrCloudUsePaidTime') }}</span>
                </template>
                <div class="game-toggle-option">
                  <a-switch
                    :checked="hsrConfig.Cloud.UsePaidTime"
                    data-testid="hsr-cloud-use-paid-time"
                    @change="handleCloudConfigChange('UsePaidTime', Boolean($event))"
                  />
                  <a-typography-text type="secondary">{{
                    t('core.edit.hsrCloudUsePaidTimeHint')
                  }}</a-typography-text>
                </div>
              </a-form-item>
            </a-col>
            <a-col :xs="24" :lg="8">
              <a-form-item>
                <template #label>
                  <FieldLabelWithHint
                    :text="t('core.edit.hsrCloudMaxQueue')"
                    :hint="t('core.edit.hsrCloudMaxQueueTip')"
                    variant="form"
                  />
                </template>
                <a-input-number
                  v-model:value="hsrConfig.Cloud.MaxQueueMinutes"
                  :min="1"
                  :max="9999"
                  :addon-after="t('core.edit.hsrCloudMinutes')"
                  size="large"
                  style="width: 100%"
                  data-testid="hsr-cloud-max-queue"
                  @change="handleCloudConfigChange('MaxQueueMinutes', $event ?? 60)"
                />
              </a-form-item>
            </a-col>
            <a-col :xs="24" :lg="8">
              <a-form-item>
                <template #label>
                  <FieldLabelWithHint
                    :text="t('core.edit.hsrCloudLoginWait')"
                    :hint="t('core.edit.hsrCloudLoginWaitTip')"
                    variant="form"
                  />
                </template>
                <a-input-number
                  v-model:value="hsrConfig.Cloud.LoginTimeoutMinutes"
                  :min="1"
                  :max="9999"
                  :addon-after="t('core.edit.hsrCloudMinutes')"
                  size="large"
                  style="width: 100%"
                  data-testid="hsr-cloud-login-wait"
                  @change="handleCloudConfigChange('LoginTimeoutMinutes', $event ?? 20)"
                />
              </a-form-item>
            </a-col>
          </a-row>

          <!-- SRA 配置档案只对已填 SRA 路径的客户端脚本有意义，没填或云平台不渲染 -->
          <a-row v-if="hsrConfig.Info.SRAPath && !isCloud" :gutter="24">
            <a-col :span="12" :offset="12">
              <a-form-item>
                <template #label>
                  <FieldLabelWithHint
                    :text="t('core.edit.sraProfile')"
                    :hint="t('core.edit.sraProfileTooltip')"
                    variant="form"
                  />
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

          <!-- 游戏路径、启动等待、分辨率只在 MAS 管理本地客户端时有用，否则整块不渲染 -->
          <a-row v-if="hsrConfig.Game.Enabled && !isCloud" :gutter="24" style="margin-top: 16px">
            <a-col :xs="24" :lg="16">
              <a-form-item>
                <template #label>
                  <FieldLabelWithHint
                    :text="t('core.edit.gamePath')"
                    :hint="t('core.edit.starRailGameRoot')"
                    variant="form"
                  />
                </template>
                <PathPickerField
                  v-model="hsrConfig.Game.Path"
                  mode="folder"
                  :placeholder="t('core.edit.pickStarRailInstall')"
                  :pick-label="t('core.edit.pickFolder')"
                  @pick="selectPath('Game.Path')"
                />
              </a-form-item>
            </a-col>
            <a-col :xs="24" :lg="8">
              <a-form-item>
                <template #label>
                  <FieldLabelWithHint
                    :text="t('core.edit.maximumGameLaunchWait')"
                    :hint="t('core.edit.howLongMasWaits')"
                    variant="form"
                  />
                </template>
                <a-input-number
                  v-model:value="hsrConfig.Game.WaitTime"
                  :min="0"
                  :max="9999"
                  :addon-after="t('core.edit.seconds')"
                  size="large"
                  style="width: 100%"
                  @change="handleGameConfigChange('WaitTime', $event)"
                />
              </a-form-item>
            </a-col>
          </a-row>

          <a-row
            v-if="!isCloud && (hsrConfig.Game.Enabled || hsrConfig.Info.SRAPath)"
            :gutter="24"
            style="margin-top: 16px"
          >
            <a-col v-if="hsrConfig.Game.Enabled" :xs="24" :lg="12">
              <a-form-item>
                <template #label>
                  <FieldLabelWithHint
                    :text="t('core.edit.run1920x1080WindowedMode')"
                    :hint="t('core.edit.writtenCurrentUserS')"
                    variant="form"
                  />
                </template>
                <div class="game-toggle-option">
                  <a-switch
                    :checked="hsrConfig.Game.ForceResolution1920x1080"
                    @change="handleGameResolutionChange"
                  />
                  <a-typography-text type="secondary">{{
                    t('core.edit.restoreOriginalRegistryValue')
                  }}</a-typography-text>
                </div>
              </a-form-item>
            </a-col>
            <!-- M7A 自带兑换码去重、不走指纹闸门，这个开关只作用于 SRA -->
            <a-col v-if="hsrConfig.Info.SRAPath" :xs="24" :lg="12">
              <a-form-item>
                <template #label>
                  <FieldLabelWithHint
                    :text="t('core.edit.redeemCodesRunOnly')"
                    :hint="t('core.edit.runsOncePerUser')"
                    variant="form"
                  />
                </template>
                <div class="game-toggle-option">
                  <a-switch
                    :checked="hsrConfig.Game.RedeemCodesOnlyWhenChanged"
                    @change="handleRedeemCodePolicyChange"
                  />
                  <a-typography-text type="secondary">{{
                    t('core.edit.runOnceNewUser')
                  }}</a-typography-text>
                </div>
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <!-- 执行限制 -->
        <div class="form-section">
          <div class="section-header">
            <h3>{{ t('core.edit.runLimits') }}</h3>
          </div>
          <a-row :gutter="16">
            <a-col :span="12">
              <ScriptRunLimitField
                v-model="hsrConfig.Run.ProxyTimesLimit"
                kind="daily"
                :label="t('core.edit.runsPerDayThis')"
                :hint="t('core.edit.k0MeansNoLimit')"
                @change="handleChange('Run', 'ProxyTimesLimit', $event)"
              />
            </a-col>
            <a-col :span="12">
              <a-form-item :label="t('core.edit.maximumAttemptsFailedTask')">
                <a-input-number
                  v-model:value="hsrConfig.Run.RunTimesLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @change="handleChange('Run', 'RunTimesLimit', $event)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item :label="t('core.edit.dailyTaskTimeoutMinutes')">
                <a-input-number
                  v-model:value="hsrConfig.Run.DailyTimeLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @change="handleChange('Run', 'DailyTimeLimit', $event)"
                />
              </a-form-item>
            </a-col>
          </a-row>
          <a-row :gutter="16">
            <a-col :span="12">
              <a-form-item :label="t('core.edit.weeklyTaskTimeoutMinutes')">
                <a-input-number
                  v-model:value="hsrConfig.Run.WeeklyTimeLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @change="handleChange('Run', 'WeeklyTimeLimit', $event)"
                />
              </a-form-item>
            </a-col>
          </a-row>
          <!-- 低性能兼容只作用于三月七，没填三月七路径时不渲染 -->
          <a-row v-if="hsrConfig.Info.M7APath" :gutter="16">
            <a-col :span="12">
              <a-form-item :label="t('core.edit.enableLowPerformanceCompatibility')">
                <a-switch
                  v-model:checked="hsrConfig.Run.LowPerformanceMode"
                  @change="handleChange('Run', 'LowPerformanceMode', $event)"
                />
                <div class="form-item-hint">
                  {{ t('core.edit.appliesMarch7thDivergentUniverse') }}
                </div>
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <HSRProgramUpdateSettings
          :script-id="scriptId"
          :update="hsrConfig.Update"
          :m7a-path="hsrConfig.Info.M7APath || ''"
          :sra-path="hsrConfig.Info.SRAPath || ''"
          :capability-snapshot="capabilitySnapshot"
          @change="(key, value) => handleChange('Update', key, value)"
          @updated="loadCapabilities"
        />
      </a-form>
    </a-card>
  </ConfigLockPanel>
</template>

<script setup lang="ts">
import PathPickerField from '@/components/PathPickerField.vue'
import ScriptRunLimitField from './components/ScriptRunLimitField.vue'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import ConfigLockPanel from '@/components/ConfigLockPanel.vue'
import { useI18n } from 'vue-i18n'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import ScriptEditHeader from '@/components/ScriptEditHeader.vue'
import { useScriptApi } from '@/composables/useScriptApi'
import { useScriptSaveMutation } from '@/composables/useScriptSaveMutation'
import {
  filterHSRCapabilityWarnings,
  useHSRPluginApi,
  type HSRCapabilitySnapshot,
  type HSREngine,
  type HSRSRAProfilesSnapshot,
} from '@/composables/useHSRPluginApi'
import type { HSRConfig_Cloud, HSRConfig_Info, HSRConfig_Game, HSRConfig_Run } from '@/api'
import type { HSRScriptConfig, ScriptDetail } from '@/types/script'
import HSRProgramUpdateSettings from './components/HSRProgramUpdateSettings.vue'
import {
  getDefaultUpdateConfig,
  normalizeHSRUpdateConfig,
  type HSRUpdateConfig,
} from './hsrUpdateConfig'

const { t } = useI18n()

// HSR 内部非空 reactive 形态（OpenAPI 生成类型字段全部为 optional | null，
// 前端实际为非空；通过该形态消除 strict null 警告）。
type HSRGamePlatform = NonNullable<HSRConfig_Game['Platform']>
// 云·星穹铁道配置的本地非空形态；LastLogin 只读、只在用户页展示，这里不收也不回写。
type HSRCloudConfig = {
  UsePaidTime: boolean
  MaxQueueMinutes: number
  LoginTimeoutMinutes: number
}
type HSRCloudConfigKey = keyof HSRCloudConfig & keyof HSRConfig_Cloud

type HSRConfigData = {
  Info: HSRConfig_Info
  Game: HSRConfig_Game & {
    Platform: HSRGamePlatform
    Enabled?: boolean | null
    ForceResolution1920x1080?: boolean | null
    RedeemCodesOnlyWhenChanged?: boolean | null
  }
  Cloud: HSRCloudConfig
  Run: HSRConfig_Run
  Update: HSRUpdateConfig
}

const getDefaultCloudConfig = (): HSRCloudConfig => ({
  UsePaidTime: false,
  MaxQueueMinutes: 60,
  LoginTimeoutMinutes: 20,
})

const logger = window.electronAPI.getLogger('HSR 脚本编辑')

const route = useRoute()
const router = useRouter()
const { getScript, error: scriptApiError } = useScriptApi()
const hsrPluginApi = useHSRPluginApi()

const pageLoading = ref(false)
const scriptId = route.params.id as string
const isInitializing = ref(true)
// 保存串行队列：连续改动按序写回，不再被布尔互斥丢掉
const { saveField: handleChange } = useScriptSaveMutation({
  scriptId,
  isInitializing,
  logger,
  afterFieldSave: async (category, key) => {
    if (FIELDS_REQUIRE_REFRESH_AFTER_SAVE.has(`${category}.${key}`)) {
      await refreshScript()
      await Promise.all([loadCapabilities(), loadSraProfiles()])
    }
  },
})
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
    Platform: 'Client',
    Enabled: true,
    Path: '',
    WaitTime: 60,
    ForceResolution1920x1080: false,
    RedeemCodesOnlyWhenChanged: true,
  },
  Cloud: getDefaultCloudConfig(),
  Run: {
    ProxyTimesLimit: 0,
    RunTimesLimit: 3,
    DailyTimeLimit: 20,
    WeeklyTimeLimit: 60,
    LowPerformanceMode: false,
  },
  Update: getDefaultUpdateConfig(),
})

// 需要后端语义化校正（DPAPI 加解密、路径规范化等）的字段保存后再 GET 拉回；
// 其余纯本地赋值字段不重复请求，避免覆盖用户刚改的值。
const FIELDS_REQUIRE_REFRESH_AFTER_SAVE = new Set<string>([
  'Info.Name',
  'Info.M7APath',
  'Info.SRAPath',
  'Info.SRAProfile',
  'Game.Path',
  // 平台切换后能力快照（引擎分配提示）随之变化
  'Game.Platform',
])

// 云·星穹铁道只用三月七，客户端相关字段整块不渲染
const isCloud = computed(() => hsrConfig.Game.Platform === 'Cloud')

const platformOptions = computed(() => [
  { label: t('core.edit.hsrPlatformClient'), value: 'Client' },
  { label: t('core.edit.hsrPlatformCloud'), value: 'Cloud' },
])

const refreshScript = async () => {
  try {
    const scriptDetail = await getScript(scriptId)
    if (!scriptDetail) return
    applyScriptDetail(scriptDetail)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`刷新配置失败: ${errorMsg}`)
  }
}

const applyScriptDetail = (scriptDetail: ScriptDetail) => {
  formData.infoName = scriptDetail.name
  const cfg = scriptDetail.config as HSRScriptConfig
  if (cfg.Info) Object.assign(hsrConfig.Info, cfg.Info)
  if (cfg.Game) {
    Object.assign(hsrConfig.Game, cfg.Game)
    if (hsrConfig.Game.Platform !== 'Cloud') hsrConfig.Game.Platform = 'Client'
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
  if (cfg.Cloud) {
    const defaults = getDefaultCloudConfig()
    hsrConfig.Cloud.UsePaidTime = Boolean(cfg.Cloud.UsePaidTime ?? defaults.UsePaidTime)
    hsrConfig.Cloud.MaxQueueMinutes = cfg.Cloud.MaxQueueMinutes ?? defaults.MaxQueueMinutes
    hsrConfig.Cloud.LoginTimeoutMinutes =
      cfg.Cloud.LoginTimeoutMinutes ?? defaults.LoginTimeoutMinutes
  }
  if (cfg.Run) {
    Object.assign(hsrConfig.Run, cfg.Run)
    if (hsrConfig.Run.RunTimesLimit === undefined) hsrConfig.Run.RunTimesLimit = 3
    if (hsrConfig.Run.DailyTimeLimit === undefined) hsrConfig.Run.DailyTimeLimit = 20
    if (hsrConfig.Run.WeeklyTimeLimit === undefined) hsrConfig.Run.WeeklyTimeLimit = 60
    if (hsrConfig.Run.LowPerformanceMode === undefined) hsrConfig.Run.LowPerformanceMode = false
  }
  Object.assign(hsrConfig.Update, normalizeHSRUpdateConfig(cfg.Update))
}

const handleGameConfigChange = async (key: 'WaitTime', value: number | null) => {
  if (isInitializing.value) return
  const normalizedValue = value ?? 60
  hsrConfig.Game[key] = normalizedValue
  await handleChange('Game', key, normalizedValue)
}

const handlePlatformChange = async (value: string | number) => {
  if (isInitializing.value) return
  const next: HSRGamePlatform = value === 'Cloud' ? 'Cloud' : 'Client'
  const previous = hsrConfig.Game.Platform
  if (next === previous) return
  hsrConfig.Game.Platform = next
  const saved = await handleChange('Game', 'Platform', next)
  if (!saved) {
    hsrConfig.Game.Platform = previous
    await refreshScript()
  }
}

const handleCloudConfigChange = async (key: HSRCloudConfigKey, value: boolean | number) => {
  if (isInitializing.value) return
  ;(hsrConfig.Cloud as Record<HSRCloudConfigKey, boolean | number>)[key] = value
  const saved = await handleChange('Cloud', key, value)
  if (!saved) await refreshScript()
}

const handleGameEnabledChange = async (value: boolean | string | number) => {
  if (isInitializing.value) return
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
  if (isInitializing.value) return
  const enabled = Boolean(value)
  hsrConfig.Game.ForceResolution1920x1080 = enabled
  const saved = await handleChange('Game', 'ForceResolution1920x1080', enabled)
  if (!saved) await refreshScript()
}

const handleRedeemCodePolicyChange = async (value: boolean | string | number) => {
  if (isInitializing.value) return
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
      message.error(t('core.edit.filePickingUnavailableRun'))
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
          title: t('core.edit.invalidPath'),
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
    message.success(t('core.edit.pathSelected'))
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`选择路径失败: ${errorMsg}`)
    message.error(t('core.edit.couldNotPickFolder'))
  }
}

const handleCancel = () => {
  router.push('/scripts')
}

// 清空路径：保存空字符串到后端；任务映射在用户页维护（shared 来源写脚本级，independent 来源写用户级）。
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
    { value: '', label: t('core.edit.sraProfileAuto', { name: snapshot?.auto_id || 'Default' }) },
    ...(snapshot?.profiles ?? []).map(profile => ({ value: profile.id, label: profile.id })),
  ]
  const configured = hsrConfig.Info.SRAProfile || ''
  if (configured && !options.some(option => option.value === configured)) {
    options.push({ value: configured, label: configured })
  }
  return options
})

// 下拉只在填了 SRA 路径时渲染，这里只剩「档案目录读不到」这类原因
const sraProfileDisabledReason = computed(() => {
  if (sraProfilesError.value) {
    return t('core.edit.sraProfileLoadFailed', { reason: sraProfilesError.value })
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
      if (!scriptApiError.value) message.error(t('core.edit.scriptDoesNotExist'))
      router.push('/scripts')
      return
    }
    // 直接用这次拿到的结果填表, 不再重复 GET 一次; 能力快照与 SRA 档案互不依赖, 并行拉
    applyScriptDetail(scriptDetail)
    await Promise.all([loadCapabilities(), loadSraProfiles()])
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载脚本失败: ${errorMsg}`)
    if (!scriptApiError.value) message.error(t('core.edit.couldNotLoadScript'))
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

.cloud-intro {
  margin-bottom: 12px;
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

.path-input-group :deep(.path-input.ant-input) {
  flex: 1;
  border: none;
  border-radius: 0;
  background: var(--ant-color-bg-container);
}

.path-input-group :deep(.path-input.ant-input:focus) {
  box-shadow: none;
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
