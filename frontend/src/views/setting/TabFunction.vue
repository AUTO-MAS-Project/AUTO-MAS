<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed } from 'vue'
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons-vue'
import type { GlobalConfig } from '@/api'
import { useVirtualDisplaySettings } from './useVirtualDisplaySettings'
import { openExternalUrl } from '@/utils/openExternal'
import { navigateTo } from '@/router'
import FailureReplaySettings from './components/FailureReplaySettings.vue'

const { t } = useI18n()

// 指向 releases 页而不是某一版安装包的直链：直链会随上游发版失效，而且点下去直接落一个 exe，
// 用户没机会先看清自己在装什么。releases/latest 永远指向最新一版，页面上的 `-setup.exe` 就是它。
const VDD_DOWNLOAD_URL = 'https://github.com/nomi-san/parsec-vdd/releases/latest'

// 分辨率固定 1920x1080：实测只有它 Windows 给 100% 缩放，再高会被自动上缩放，
// 游戏窗口又要面对 DPI 虚拟化——而虚拟屏本来就是为了绕开这类问题。所以这里只让用户
// 选刷新率。驱动的刷新率表是 24/30/60/144/240，写 120 会被 BADMODE 拒绝。
// 选项放在 computed 里，t() 是响应式的。
const virtualDisplayModeOptions = computed(() => [
  { label: `60 Hz（${t('core.setting.display.refreshDefault')}）`, value: '1920x1080@60' },
  { label: `30 Hz（${t('core.setting.display.refreshLowPower')}）`, value: '1920x1080@30' },
])

const {
  vddDriverReady,
  vddDriverMessage,
  vddHolding,
  vddSwitchDisabled,
  vddWarning,
  vddChecking,
  vddResult,
  vddAllPassed,
  runVirtualDisplayCheck,
  vddDetaching,
  runVirtualDisplayDetach,
} = useVirtualDisplaySettings(() => settings)

function openVddDownload() {
  openExternalUrl(VDD_DOWNLOAD_URL)
}

const { settings, historyRetentionOptions, voiceTypeOptions, handleSettingChange } = defineProps<{
  settings: GlobalConfig
  historyRetentionOptions: { label: string; value: number }[]
  voiceTypeOptions: { label: string; value: string }[]
  handleSettingChange: (category: keyof GlobalConfig, key: string, value: any) => Promise<boolean>
}>()
</script>
<template>
  <div class="tab-content">
    <div class="form-section">
      <div class="section-header">
        <h3>{{ t('core.setting.func.startupSection') }}</h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('core.setting.func.autoStart') }}</span>
              <a-tooltip :title="t('core.setting.func.autoStartTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="settings.Start?.IfSelfStart"
              size="large"
              style="width: 100%"
              @change="(checked: any) => handleSettingChange('Start', 'IfSelfStart', checked)"
            >
              <a-select-option :value="true">{{ t('core.common.yes') }}</a-select-option>
              <a-select-option :value="false">{{ t('core.common.no') }}</a-select-option>
            </a-select>
          </div>
        </a-col>
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('core.setting.func.startMinimized') }}</span>
              <a-tooltip :title="t('core.setting.func.startMinimizedTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="settings.Start?.IfMinimizeDirectly"
              size="large"
              style="width: 100%"
              @change="
                (checked: any) => handleSettingChange('Start', 'IfMinimizeDirectly', checked)
              "
            >
              <a-select-option :value="true">{{ t('core.common.yes') }}</a-select-option>
              <a-select-option :value="false">{{ t('core.common.no') }}</a-select-option>
            </a-select>
          </div>
        </a-col>
      </a-row>
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>{{ t('core.setting.func.featureSection') }}</h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="8">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('core.setting.func.retention') }}</span>
              <a-tooltip :title="t('core.setting.func.retentionTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="settings.Function?.HistoryRetentionTime"
              :options="historyRetentionOptions"
              size="large"
              style="width: 100%"
              @change="
                (value: any) => handleSettingChange('Function', 'HistoryRetentionTime', value)
              "
            />
          </div>
        </a-col>
        <a-col :span="8">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('core.setting.func.silent') }}</span>
              <a-tooltip :title="t('core.setting.func.silentTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="settings.Function?.IfSilence"
              size="large"
              style="width: 100%"
              @change="(checked: any) => handleSettingChange('Function', 'IfSilence', checked)"
            >
              <a-select-option :value="true">{{ t('core.common.yes') }}</a-select-option>
              <a-select-option :value="false">{{ t('core.common.no') }}</a-select-option>
            </a-select>
          </div>
        </a-col>
        <a-col :span="8">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('core.setting.func.preventSleep') }}</span>
              <a-tooltip :title="t('core.setting.func.preventSleepTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="settings.Function?.IfAllowSleep"
              size="large"
              style="width: 100%"
              @change="(checked: any) => handleSettingChange('Function', 'IfAllowSleep', checked)"
            >
              <a-select-option :value="true">{{ t('core.common.yes') }}</a-select-option>
              <a-select-option :value="false">{{ t('core.common.no') }}</a-select-option>
            </a-select>
          </div>
        </a-col>
      </a-row>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('core.setting.func.telemetry') }}</span>
              <a-tooltip :title="t('core.setting.func.telemetryTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="settings.Function?.IfEnableTelemetry !== false"
              size="large"
              style="width: 100%"
              @change="
                (checked: any) => handleSettingChange('Function', 'IfEnableTelemetry', checked)
              "
            >
              <a-select-option :value="true">{{ t('core.common.yes') }}</a-select-option>
              <a-select-option :value="false">{{ t('core.common.no') }}</a-select-option>
            </a-select>
          </div>
        </a-col>
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('core.setting.func.blockAds') }}</span>
              <a-tooltip>
                <template #title>
                  <div style="max-width: 300px">
                    <p>{{ t('core.setting.func.blockAdsIntro') }}</p>
                    <ul style="margin: 8px 0; padding-left: 16px">
                      <li>
                        <strong>{{ t('core.emulator.type.mumu') }}</strong
                        >: {{ t('core.setting.func.blockAdsMumu') }}
                      </li>
                      <li>
                        <strong>{{ t('core.emulator.type.ldplayer') }}</strong
                        >: {{ t('core.setting.func.blockAdsLd') }}
                      </li>
                    </ul>
                  </div>
                </template>
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="settings.Function?.IfBlockAd"
              size="large"
              style="width: 100%"
              @change="(checked: any) => handleSettingChange('Function', 'IfBlockAd', checked)"
            >
              <a-select-option :value="true">{{ t('core.common.yes') }}</a-select-option>
              <a-select-option :value="false">{{ t('core.common.no') }}</a-select-option>
            </a-select>
          </div>
        </a-col>
      </a-row>
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>{{ t('core.setting.func.voiceSection') }}</h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('core.setting.func.voiceEnable') }}</span>
              <a-tooltip :title="t('core.setting.func.voiceEnableTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="settings.Voice?.Enabled"
              size="large"
              style="width: 100%"
              @change="(checked: any) => handleSettingChange('Voice', 'Enabled', checked)"
            >
              <a-select-option :value="true">{{ t('core.common.yes') }}</a-select-option>
              <a-select-option :value="false">{{ t('core.common.no') }}</a-select-option>
            </a-select>
          </div>
        </a-col>
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('core.setting.func.voiceType') }}</span>
              <a-tooltip :title="t('core.setting.func.voiceTypeTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="settings.Voice?.Type"
              :options="voiceTypeOptions"
              :disabled="!settings.Voice?.Enabled"
              size="large"
              style="width: 100%"
              @change="(value: any) => handleSettingChange('Voice', 'Type', value)"
            />
          </div>
        </a-col>
      </a-row>
    </div>

    <FailureReplaySettings :settings="settings" :handle-setting-change="handleSettingChange" />

    <div class="form-section">
      <div class="section-header">
        <h3>{{ t('core.setting.display.section') }}</h3>
      </div>
      <a-alert type="info" show-icon class="vdd-alert">
        <template #message>
          <i18n-t keypath="core.setting.display.intro" tag="span" scope="global">
            <template #driverLink>
              <a href="#" @click.prevent="openVddDownload">{{
                t('core.setting.display.introDriverLink')
              }}</a>
            </template>
          </i18n-t>
        </template>
      </a-alert>
      <a-row :gutter="24">
        <a-col :span="6">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('core.setting.display.enable') }}</span>
              <a-tooltip :title="t('core.setting.display.enableTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="settings.Display?.IfEnableVirtualDisplay"
              :disabled="vddSwitchDisabled"
              size="large"
              style="width: 100%"
              @change="
                (checked: any) => handleSettingChange('Display', 'IfEnableVirtualDisplay', checked)
              "
            >
              <a-select-option :value="true">{{ t('core.common.yes') }}</a-select-option>
              <a-select-option :value="false">{{ t('core.common.no') }}</a-select-option>
            </a-select>
          </div>
        </a-col>
        <a-col :span="6">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('core.setting.display.mode') }}</span>
              <a-tooltip :title="t('core.setting.display.modeTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="settings.Display?.VirtualDisplayMode"
              :options="virtualDisplayModeOptions"
              :disabled="!settings.Display?.IfEnableVirtualDisplay"
              size="large"
              style="width: 100%"
              @change="(value: any) => handleSettingChange('Display', 'VirtualDisplayMode', value)"
            />
          </div>
        </a-col>
        <a-col :span="6">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('core.setting.display.check') }}</span>
              <a-tooltip :title="t('core.setting.display.checkTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-button
              size="large"
              style="width: 100%"
              :loading="vddChecking"
              @click="runVirtualDisplayCheck"
            >
              {{ t('core.setting.display.checkAction') }}
            </a-button>
          </div>
        </a-col>
        <a-col :span="6">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('core.setting.display.detach') }}</span>
              <a-tooltip :title="t('core.setting.display.detachTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-button
              danger
              size="large"
              style="width: 100%"
              :disabled="!settings.Display?.IfEnableVirtualDisplay"
              :loading="vddDetaching"
              @click="runVirtualDisplayDetach"
            >
              {{ t('core.setting.display.detachAction') }}
            </a-button>
          </div>
        </a-col>
      </a-row>
      <a-row v-if="settings.Display?.IfEnableVirtualDisplay" :gutter="24" class="vdd-result-row">
        <a-col :span="24">
          <p class="vdd-holding">
            {{
              vddHolding
                ? t('core.setting.display.holdingNow', { holding: vddHolding })
                : t('core.setting.display.holdingNone')
            }}
          </p>
        </a-col>
      </a-row>
      <a-row v-if="vddWarning" :gutter="24" class="vdd-result-row">
        <a-col :span="24">
          <a-alert type="warning" show-icon :message="vddWarning">
            <template #description>
              <a href="#" @click.prevent="openVddDownload">
                {{ t('core.setting.display.download') }}
              </a>
            </template>
          </a-alert>
        </a-col>
      </a-row>

      <a-row v-if="vddResult" :gutter="24" class="vdd-result-row">
        <a-col :span="24">
          <a-alert :type="vddAllPassed ? 'success' : 'warning'" show-icon>
            <template #message>
              {{
                vddAllPassed
                  ? t('core.setting.display.checkPassed')
                  : t('core.setting.display.checkIssue')
              }}
            </template>
            <template #description>
              <p v-if="!vddAllPassed && vddResult.message" class="vdd-summary">
                {{ vddResult.message }}
              </p>
              <ul class="vdd-result-list">
                <li v-for="item in vddResult.results ?? []" :key="item.stage">
                  <CheckCircleOutlined v-if="item.passed" class="vdd-ok" />
                  <CloseCircleOutlined v-else class="vdd-fail" />
                  {{ t(`core.setting.display.stage.${item.stage}`) }} — {{ item.message }}
                </li>
              </ul>
              <p v-if="vddResult.monitors" class="vdd-monitors">
                {{ t('core.setting.display.monitors') }}: {{ vddResult.monitors }}
              </p>
              <p v-if="!(vddResult.results ?? []).some(item => item.stage === 'openable')">
                <a href="#" @click.prevent="openVddDownload">
                  {{ t('core.setting.display.download') }}
                </a>
              </p>
            </template>
          </a-alert>
        </a-col>
      </a-row>
    </div>
    <!-- 个人版编排的「并非神秘入口」已移入神秘入口，这里只留群友的「神秘入口」一个入口 -->
    <div class="flavor-entries">
      <div class="mystery-entry">
        <a-button type="text" size="small" @click="navigateTo('/settings/mystery')">
          {{ t('core.mystery.entry') }}
        </a-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.flavor-entries {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.flavor-entries :deep(.ant-btn) {
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}

.vdd-alert {
  margin-bottom: 16px;
}

.vdd-result-row {
  margin-top: 16px;
}

.vdd-summary {
  margin: 0 0 8px;
}

.vdd-result-list {
  margin: 0;
  padding-left: 0;
  list-style: none;
}

.vdd-result-list li {
  margin: 4px 0;
}

.vdd-ok {
  color: var(--ant-color-success);
}

.vdd-fail {
  color: var(--ant-color-warning);
}

.vdd-monitors {
  margin: 8px 0 0;
  word-break: break-all;
  color: var(--ant-color-text-secondary);
}

.vdd-holding {
  margin: 0;
  font-size: 13px;
  color: var(--ant-color-text-secondary);
}
</style>
