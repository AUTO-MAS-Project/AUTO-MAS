<template>
  <ScriptEditHeader script-type="HSR" :title="t('edit.editHsrScript')" @cancel="handleCancel" />

  <ConfigLockPanel :script-id="scriptId" content-class="script-edit-content">
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

        <!-- M7A / SRA / 游戏路径 -->
        <div class="form-section">
          <div class="section-header">
            <h3>{{ t('edit.scriptGameConfiguration') }}</h3>
          </div>
          <a-alert
            v-if="isCloud"
            type="info"
            show-icon
            :message="t('edit.hsrCloudIntro')"
            class="cloud-intro"
          />
          <div class="engine-path-hint">
            <a-typography-text type="secondary">
              {{ t('edit.fillingPathEnablesThat') }}
            </a-typography-text>
          </div>
          <a-row :gutter="24">
            <a-col :xs="24" :lg="8">
              <a-form-item>
                <template #label>
                  <a-tooltip :title="t('edit.hsrGamePlatformTip')">
                    <span class="form-label">
                      {{ t('edit.hsrGamePlatform') }}
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
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
                  <a-tooltip :title="t('edit.turnThisOffWhen')">
                    <span class="form-label">
                      {{ t('edit.masManagesGame') }}
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
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
                <!-- 云平台保留 SRA 路径（外部脚本更新照常），但任务不经 SRA -->
                <a-typography-text v-if="isCloud" type="secondary" class="field-hint">
                  {{ t('edit.hsrCloudNoSra') }}
                </a-typography-text>
              </a-form-item>
            </a-col>
          </a-row>

          <!-- 云·星穹铁道：付费时长、排队与登录等待，映射到三月七的 cloud_game_* -->
          <a-row v-if="isCloud" :gutter="24" style="margin-top: 16px">
            <a-col :xs="24" :lg="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">{{ t('edit.hsrCloudUsePaidTime') }}</span>
                </template>
                <div class="game-toggle-option">
                  <a-switch
                    :checked="hsrConfig.Cloud.UsePaidTime"
                    data-testid="hsr-cloud-use-paid-time"
                    @change="handleCloudConfigChange('UsePaidTime', Boolean($event))"
                  />
                  <a-typography-text type="secondary">{{
                    t('edit.hsrCloudUsePaidTimeHint')
                  }}</a-typography-text>
                </div>
              </a-form-item>
            </a-col>
            <a-col :xs="24" :lg="8">
              <a-form-item>
                <template #label>
                  <a-tooltip :title="t('edit.hsrCloudMaxQueueTip')">
                    <span class="form-label">
                      {{ t('edit.hsrCloudMaxQueue') }}
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input-number
                  v-model:value="hsrConfig.Cloud.MaxQueueMinutes"
                  :min="1"
                  :max="9999"
                  :addon-after="t('edit.hsrCloudMinutes')"
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
                  <a-tooltip :title="t('edit.hsrCloudLoginWaitTip')">
                    <span class="form-label">
                      {{ t('edit.hsrCloudLoginWait') }}
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input-number
                  v-model:value="hsrConfig.Cloud.LoginTimeoutMinutes"
                  :min="1"
                  :max="9999"
                  :addon-after="t('edit.hsrCloudMinutes')"
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

          <!-- 游戏路径、启动等待、分辨率只在 MAS 管理本地客户端时有用，否则整块不渲染 -->
          <a-row v-if="hsrConfig.Game.Enabled && !isCloud" :gutter="24" style="margin-top: 16px">
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

          <a-row
            v-if="!isCloud && (hsrConfig.Game.Enabled || hsrConfig.Info.SRAPath)"
            :gutter="24"
            style="margin-top: 16px"
          >
            <a-col v-if="hsrConfig.Game.Enabled" :xs="24" :lg="12">
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
            <!-- M7A 自带兑换码去重、不走指纹闸门，这个开关只作用于 SRA -->
            <a-col v-if="hsrConfig.Info.SRAPath" :xs="24" :lg="12">
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
          <!-- 低性能兼容只作用于三月七，没填三月七路径时不渲染 -->
          <a-row v-if="hsrConfig.Info.M7APath" :gutter="16">
            <a-col :span="12">
              <a-form-item :label="t('edit.enableLowPerformanceCompatibility')">
                <a-switch
                  v-model:checked="hsrConfig.Run.LowPerformanceMode"
                  @change="handleRunConfigChange('LowPerformanceMode', $event)"
                />
                <div class="form-item-hint">
                  {{ t('edit.appliesMarch7thDivergentUniverse') }}
                </div>
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <!-- 外部脚本更新 -->
        <div class="form-section">
          <div class="section-header">
            <h3>{{ t('edit.hsrExternalUpdate') }}</h3>
          </div>
          <div class="section-hint">{{ t('edit.hsrUpdateSectionHint') }}</div>
          <a-row :gutter="24">
            <a-col :xs="24" :lg="12">
              <a-form-item>
                <template #label>
                  <a-tooltip :title="t('edit.hsrUpdateModeTip')">
                    <span class="form-label">
                      {{ t('edit.autoUpdateMode') }}
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-select
                  v-model:value="hsrConfig.Update.AutoUpdateMode"
                  :options="autoUpdateModeOptions"
                  size="large"
                  style="width: 100%"
                  @change="handleUpdateConfigChange('AutoUpdateMode', $event)"
                />
              </a-form-item>
            </a-col>
            <a-col :xs="24" :lg="12">
              <a-form-item>
                <template #label>
                  <a-tooltip :title="t('edit.hsrUpdateChannelTip')">
                    <span class="form-label">
                      {{ t('edit.hsrUpdateChannel') }}
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-select
                  v-model:value="hsrConfig.Update.Channel"
                  :options="updateChannelOptions"
                  size="large"
                  style="width: 100%"
                  @change="handleUpdateConfigChange('Channel', $event)"
                />
              </a-form-item>
            </a-col>
          </a-row>
          <!-- 下载源按已填路径的引擎渲染；CDK 只在某个已渲染的源选了 Mirror 酱时需要 -->
          <a-row v-if="hsrConfig.Info.M7APath || hsrConfig.Info.SRAPath" :gutter="24">
            <a-col v-if="hsrConfig.Info.M7APath" :xs="24" :lg="12">
              <a-form-item>
                <template #label>
                  <a-tooltip :title="t('edit.hsrUpdateM7ASourceTip')">
                    <span class="form-label">
                      {{ t('edit.hsrUpdateM7ASource') }}
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-select
                  v-model:value="hsrConfig.Update.M7ASource"
                  :options="m7aSourceOptions"
                  size="large"
                  style="width: 100%"
                  @change="handleUpdateConfigChange('M7ASource', $event)"
                />
              </a-form-item>
            </a-col>
            <a-col v-if="hsrConfig.Info.SRAPath" :xs="24" :lg="12">
              <a-form-item>
                <template #label>
                  <a-tooltip :title="t('edit.hsrUpdateSRASourceTip')">
                    <span class="form-label">
                      {{ t('edit.hsrUpdateSRASource') }}
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-select
                  v-model:value="hsrConfig.Update.SRASource"
                  :options="sraSourceOptions"
                  size="large"
                  style="width: 100%"
                  @change="handleUpdateConfigChange('SRASource', $event)"
                />
              </a-form-item>
            </a-col>
          </a-row>
          <a-row v-if="usesMirrorChyan" :gutter="24">
            <a-col :xs="24" :lg="12">
              <a-form-item>
                <template #label>
                  <a-tooltip :title="t('edit.hsrUpdateCdkTip')">
                    <span class="form-label">
                      {{ t('edit.hsrUpdateCdk') }}
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-input-password
                  v-model:value="hsrConfig.Update.MirrorChyanCDK"
                  :placeholder="t('edit.hsrUpdateCdkPlaceholder')"
                  size="large"
                  autocomplete="off"
                  @blur="
                    handleUpdateConfigChange('MirrorChyanCDK', hsrConfig.Update.MirrorChyanCDK)
                  "
                />
                <div
                  class="form-item-hint"
                  :class="{ 'form-item-hint--warning': isCdkMissingForMirror }"
                >
                  {{
                    isCdkMissingForMirror
                      ? t('edit.hsrUpdateCdkMissing')
                      : t('edit.hsrUpdateCdkHint')
                  }}
                  <a
                    :href="MIRRORCHYAN_CDK_URL"
                    class="form-hint-link"
                    @click="handleExternalLink"
                    >{{ t('edit.hsrUpdateCdkGetLink') }}</a
                  >
                </div>
              </a-form-item>
            </a-col>
          </a-row>

          <a-form-item>
            <template #label>
              <a-tooltip :title="t('edit.hsrUpdateManualTip')">
                <span class="form-label">
                  {{ t('edit.hsrUpdateManual') }}
                  <QuestionCircleOutlined class="help-icon" />
                </span>
              </a-tooltip>
            </template>
            <a-typography-text v-if="!updateEngines.length" type="secondary">
              {{ t('edit.hsrUpdateNeedPath') }}
            </a-typography-text>
            <a-row v-else :gutter="24">
              <a-col v-for="engine in updateEngines" :key="engine" :xs="24" :lg="12">
                <div class="update-engine-card">
                  <div class="update-engine-header">
                    <span class="update-engine-name">{{ engineLabel(engine) }}</span>
                    <a-typography-text type="secondary" class="update-engine-version">
                      {{
                        t('edit.hsrUpdateInstalledVersion', {
                          version: installedVersion(engine) || t('edit.hsrUpdateVersionUnknown'),
                        })
                      }}
                    </a-typography-text>
                  </div>
                  <a-space wrap>
                    <a-button
                      :loading="updateStates[engine].checking"
                      :disabled="updateStates[engine].applying"
                      @click="runManualUpdate(engine, 'check')"
                    >
                      {{ t('edit.hsrUpdateCheckNow') }}
                    </a-button>
                    <a-button
                      type="primary"
                      :loading="updateStates[engine].applying"
                      :disabled="updateStates[engine].checking"
                      @click="runManualUpdate(engine, 'apply')"
                    >
                      {{ t('edit.hsrUpdateApplyNow') }}
                    </a-button>
                  </a-space>
                  <a-alert
                    v-if="updateStates[engine].error"
                    type="error"
                    show-icon
                    class="update-alert"
                    :message="t('edit.hsrUpdateRequestFailed', { engine: engineLabel(engine) })"
                    :description="updateStates[engine].error"
                  />
                  <a-alert
                    v-else-if="updateSummaries[engine]"
                    :type="updateSummaries[engine]!.type"
                    show-icon
                    class="update-alert"
                    :message="updateSummaries[engine]!.title"
                    :description="updateSummaries[engine]!.description || undefined"
                  />
                </div>
              </a-col>
            </a-row>
          </a-form-item>
        </div>
      </a-form>
    </a-card>
  </ConfigLockPanel>
</template>

<script setup lang="ts">
import ConfigLockPanel from '@/components/ConfigLockPanel.vue'
import { useI18n } from 'vue-i18n'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import { FolderOpenOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import ScriptEditHeader from '@/components/ScriptEditHeader.vue'
import type { HSRConfig_Update } from '@/api'
import { useScriptApi } from '@/composables/useScriptApi'
import { useSaveQueue } from '@/composables/useSaveQueue'
import {
  filterHSRCapabilityWarnings,
  useHSRPluginApi,
  type HSRCapabilitySnapshot,
  type HSREngine,
  type HSRSRAProfilesSnapshot,
  type HSRUpdateAction,
  type HSRUpdateResult,
} from '@/composables/useHSRPluginApi'
import type { HSRConfig_Cloud, HSRConfig_Info, HSRConfig_Game, HSRConfig_Run } from '@/api'
import type { HSRScriptConfig, ScriptDetail } from '@/types/script'
import { handleExternalLink } from '@/utils/openExternal'

const { t } = useI18n()

const MIRRORCHYAN_CDK_URL = 'https://mirrorchyan.com?source=automas_script_update'

// 外部脚本更新配置（Update 组）。选项集合与 app/models/config.py 的 HSRConfig
// 及 schema 的 Literal 一致：自动更新只有关闭 / 任务完成后两档，没有「运行前」；
// 下载源按引擎拆开，M7A 没有 AUTO-MAS 自建站。
type HSRAutoUpdateMode = 'Off' | 'AfterRun'
type HSRUpdateChannel = 'stable' | 'beta'
type HSRM7ASource = 'GitHub' | 'MirrorChyan'
type HSRSRASource = 'AutoSite' | 'GitHub' | 'MirrorChyan'
type HSRUpdateConfig = {
  AutoUpdateMode: HSRAutoUpdateMode
  Channel: HSRUpdateChannel
  M7ASource: HSRM7ASource
  SRASource: HSRSRASource
  MirrorChyanCDK: string
}

// 上面几个字面量是手写的（生成类型字段全为 optional | null，做不了非空
// reactive），因此必须钉住它们与 OpenAPI 生成类型一致：后端改了枚举而这里没跟，
// 下面的赋值会直接 typecheck 失败，而不是等用户选中一个后端不认的值才 422。
type _AssertUpdateEnums = {
  mode: HSRAutoUpdateMode extends NonNullable<HSRConfig_Update['AutoUpdateMode']>
    ? NonNullable<HSRConfig_Update['AutoUpdateMode']> extends HSRAutoUpdateMode
      ? true
      : never
    : never
  channel: HSRUpdateChannel extends NonNullable<HSRConfig_Update['Channel']>
    ? NonNullable<HSRConfig_Update['Channel']> extends HSRUpdateChannel
      ? true
      : never
    : never
  m7a: HSRM7ASource extends NonNullable<HSRConfig_Update['M7ASource']>
    ? NonNullable<HSRConfig_Update['M7ASource']> extends HSRM7ASource
      ? true
      : never
    : never
  sra: HSRSRASource extends NonNullable<HSRConfig_Update['SRASource']>
    ? NonNullable<HSRConfig_Update['SRASource']> extends HSRSRASource
      ? true
      : never
    : never
}
const _assertUpdateEnums: _AssertUpdateEnums = {
  mode: true,
  channel: true,
  m7a: true,
  sra: true,
}
void _assertUpdateEnums

const HSR_AUTO_UPDATE_MODES: readonly HSRAutoUpdateMode[] = ['Off', 'AfterRun']
const HSR_UPDATE_CHANNELS: readonly HSRUpdateChannel[] = ['stable', 'beta']
const HSR_M7A_SOURCES: readonly HSRM7ASource[] = ['GitHub', 'MirrorChyan']
const HSR_SRA_SOURCES: readonly HSRSRASource[] = ['AutoSite', 'GitHub', 'MirrorChyan']

const getDefaultUpdateConfig = (): HSRUpdateConfig => ({
  AutoUpdateMode: 'Off',
  Channel: 'stable',
  M7ASource: 'GitHub',
  SRASource: 'AutoSite',
  MirrorChyanCDK: '',
})

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
const { getScript, updateScript } = useScriptApi()
const hsrPluginApi = useHSRPluginApi()

const pageLoading = ref(false)
const scriptId = route.params.id as string
const isInitializing = ref(true)
// 保存串行队列：连续改动按序写回，不再被布尔互斥丢掉
const { enqueue } = useSaveQueue()
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
  { label: t('edit.hsrPlatformClient'), value: 'Client' },
  { label: t('edit.hsrPlatformCloud'), value: 'Cloud' },
])

const handleChange = async (category: string, key: string, value: any): Promise<boolean> => {
  if (isInitializing.value) return false
  return enqueue(async () => {
    try {
      const updateData: any = { [category]: { [key]: value } }
      const success = await updateScript(scriptId, updateData)
      if (!success) return false
      logger.info(`配置已保存: ${category}.${key}`)
      if (FIELDS_REQUIRE_REFRESH_AFTER_SAVE.has(`${category}.${key}`)) {
        await refreshScript()
        await Promise.all([loadCapabilities(), loadSraProfiles()])
      }
      return true
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`保存失败: ${errorMsg}`)
      return false
    }
  }, `${category}.${key}`)
}

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
  // 生成类型里 Update 的每个字段都是 optional | null，这里归一成非空的本地形态；
  // 不在选项集合里的值（旧配置或损坏）回退到默认，避免下拉框显示空白。
  const update = (cfg as { Update?: Partial<Record<keyof HSRUpdateConfig, unknown>> | null }).Update
  if (update) {
    const pick = <T extends string>(value: unknown, options: readonly T[], fallback: T): T =>
      options.includes(value as T) ? (value as T) : fallback
    const defaults = getDefaultUpdateConfig()
    hsrConfig.Update.AutoUpdateMode = pick(
      update.AutoUpdateMode,
      HSR_AUTO_UPDATE_MODES,
      defaults.AutoUpdateMode
    )
    hsrConfig.Update.Channel = pick(update.Channel, HSR_UPDATE_CHANNELS, defaults.Channel)
    hsrConfig.Update.M7ASource = pick(update.M7ASource, HSR_M7A_SOURCES, defaults.M7ASource)
    hsrConfig.Update.SRASource = pick(update.SRASource, HSR_SRA_SOURCES, defaults.SRASource)
    hsrConfig.Update.MirrorChyanCDK =
      typeof update.MirrorChyanCDK === 'string' ? update.MirrorChyanCDK : ''
  }
}

const handleRunConfigChange = async (key: string, value: any) => {
  if (isInitializing.value) return
  await enqueue(async () => {
    try {
      const updateData: any = { Run: { [key]: value } }
      const success = await updateScript(scriptId, updateData)
      if (!success) return
      logger.info(`配置已保存: Run.${key}`)
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`保存失败: ${errorMsg}`)
    }
  }, `Run.${key}`)
}

const handleUpdateConfigChange = async (key: keyof HSRUpdateConfig, value: unknown) => {
  if (isInitializing.value) return
  await enqueue(async () => {
    try {
      const updateData: any = { Update: { [key]: value } }
      const success = await updateScript(scriptId, updateData)
      if (!success) return
      logger.info(`配置已保存: Update.${key}`)
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`保存失败: ${errorMsg}`)
    }
  }, `Update.${key}`)
}

const autoUpdateModeOptions = computed(() => [
  { label: t('edit.hsrUpdateModeOff'), value: 'Off' },
  { label: t('edit.hsrUpdateModeAfterRun'), value: 'AfterRun' },
])

const updateChannelOptions = computed(() => [
  { label: t('edit.hsrUpdateChannelStable'), value: 'stable' },
  { label: t('edit.hsrUpdateChannelBeta'), value: 'beta' },
])

const m7aSourceOptions = computed(() => [
  { label: t('edit.hsrUpdateSourceGithub'), value: 'GitHub' },
  { label: t('edit.hsrUpdateSourceMirrorChyan'), value: 'MirrorChyan' },
])

const sraSourceOptions = computed(() => [
  { label: t('edit.hsrUpdateSourceAutoSite'), value: 'AutoSite' },
  { label: t('edit.hsrUpdateSourceGithub'), value: 'GitHub' },
  { label: t('edit.hsrUpdateSourceMirrorChyan'), value: 'MirrorChyan' },
])

// 已渲染的下载源（对应引擎填了路径）里有一个选了 Mirror 酱，才需要 CDK 输入框。
const usesMirrorChyan = computed(
  () =>
    (Boolean(hsrConfig.Info.M7APath) && hsrConfig.Update.M7ASource === 'MirrorChyan') ||
    (Boolean(hsrConfig.Info.SRAPath) && hsrConfig.Update.SRASource === 'MirrorChyan')
)

// 选了 Mirror 酱却没填 CDK：后端会报错跳过，不会替用户改走 GitHub，输入框下方直接提醒。
const isCdkMissingForMirror = computed(
  () => usesMirrorChyan.value && !hsrConfig.Update.MirrorChyanCDK.trim()
)

// 手动检查 / 更新：自动更新只在任务完成后触发，首次启用要跑满一轮，
// 所以这组按钮是必需入口，不是锦上添花。只对已填路径的引擎显示。
type HSRUpdateEngineState = {
  checking: boolean
  applying: boolean
  result: HSRUpdateResult | null
  error: string
}

const createUpdateEngineState = (): HSRUpdateEngineState => ({
  checking: false,
  applying: false,
  result: null,
  error: '',
})

const updateStates = reactive<Record<HSREngine, HSRUpdateEngineState>>({
  M7A: createUpdateEngineState(),
  SRA: createUpdateEngineState(),
})

const updateEngines = computed<HSREngine[]>(() => {
  const engines: HSREngine[] = []
  if (hsrConfig.Info.M7APath) engines.push('M7A')
  if (hsrConfig.Info.SRAPath) engines.push('SRA')
  return engines
})

const engineLabel = (engine: HSREngine) =>
  engine === 'M7A' ? t('edit.hsrUpdateEngineM7A') : t('edit.hsrUpdateEngineSRA')

// 能力快照里的 adapters 可能是数组或字典，两种形态都取一遍。
const installedVersion = (engine: HSREngine): string => {
  const adapters = capabilitySnapshot.value?.adapters
  const list = Array.isArray(adapters) ? adapters : Object.values(adapters ?? {})
  const adapter = list.find(item => item?.engine === engine)
  return adapter?.version?.trim() || ''
}

type HSRUpdateSummary = {
  type: 'success' | 'info' | 'warning' | 'error'
  title: string
  description: string
}

const describeUpdateResult = (
  engine: HSREngine,
  result: HSRUpdateResult | null
): HSRUpdateSummary | null => {
  if (!result) return null
  const name = engineLabel(engine)
  const unknown = t('edit.hsrUpdateVersionUnknown')
  const current = result.current_version?.trim() || unknown
  const latest = result.latest_version?.trim() || unknown
  if (result.updated) {
    return {
      type: 'success',
      title: t('edit.hsrUpdateDone', { engine: name, version: latest }),
      description: result.message,
    }
  }
  if (!result.checked) {
    return {
      type: 'error',
      title: t('edit.hsrUpdateCheckFailed', { engine: name }),
      description: result.message,
    }
  }
  if (!result.update_available) {
    return {
      type: 'success',
      title: t('edit.hsrUpdateUpToDate', { engine: name, version: current }),
      description: result.message,
    }
  }
  if (!result.installable) {
    // 有新版但装不了：多半是 CDK 问题，和「可更新」明确区分开。
    return {
      type: 'warning',
      title: t('edit.hsrUpdateNotInstallable', { engine: name, version: latest }),
      description: result.message || t('edit.hsrUpdateNotInstallableHint'),
    }
  }
  return {
    type: 'info',
    title: t('edit.hsrUpdateAvailable', { engine: name, latest, current }),
    description: result.message,
  }
}

const updateSummaries = computed<Record<HSREngine, HSRUpdateSummary | null>>(() => ({
  M7A: describeUpdateResult('M7A', updateStates.M7A.result),
  SRA: describeUpdateResult('SRA', updateStates.SRA.result),
}))

const runManualUpdate = async (engine: HSREngine, action: HSRUpdateAction) => {
  const state = updateStates[engine]
  if (state.checking || state.applying) return
  if (action === 'check') state.checking = true
  else state.applying = true
  state.error = ''
  try {
    const result = await hsrPluginApi.runEngineUpdate(scriptId, engine, action)
    state.result = result
    const summary = describeUpdateResult(engine, result)
    if (summary) {
      if (summary.type === 'success') message.success(summary.title)
      else if (summary.type === 'warning') message.warning(summary.title)
      else if (summary.type === 'error') message.error(summary.title)
      else message.info(summary.title)
    }
    // 装完后能力快照里的已安装版本会变，拉一次让「已安装」跟上。
    if (result.updated) await loadCapabilities()
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`${engine} ${action} 更新请求失败: ${errorMsg}`)
    state.result = null
    state.error = errorMsg
    message.error(
      `${t('edit.hsrUpdateRequestFailed', { engine: engineLabel(engine) })}: ${errorMsg}`
    )
  } finally {
    state.checking = false
    state.applying = false
  }
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

// 清空路径：保存空字符串到后端；任务映射在用户页维护（脚本来源写脚本级，用户来源写用户级）。
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

// 下拉只在填了 SRA 路径时渲染，这里只剩「档案目录读不到」这类原因
const sraProfileDisabledReason = computed(() => {
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
    // 直接用这次拿到的结果填表, 不再重复 GET 一次; 能力快照与 SRA 档案互不依赖, 并行拉
    applyScriptDetail(scriptDetail)
    await Promise.all([loadCapabilities(), loadSraProfiles()])
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

.form-item-hint--warning {
  color: var(--ant-color-warning);
}

.form-hint-link {
  margin-left: 4px;
  color: var(--ant-color-primary);
  text-decoration: underline;
}

.form-hint-link:hover {
  color: var(--ant-color-primary-hover);
}

.update-engine-card {
  padding: 12px 16px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
  margin-bottom: 12px;
}

.update-engine-header {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 8px 12px;
  margin-bottom: 10px;
}

.update-engine-name {
  font-weight: 600;
  color: var(--ant-color-text);
}

.update-engine-version {
  font-size: 12px;
}

.update-alert {
  margin-top: 12px;
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
