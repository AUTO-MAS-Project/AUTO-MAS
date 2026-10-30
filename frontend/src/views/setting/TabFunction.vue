<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed } from 'vue'
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons-vue'
import type { RadioChangeEvent } from 'ant-design-vue'
import type { CheckboxChangeEvent } from 'ant-design-vue/es/checkbox/interface'
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
  <div class="tab-content function-settings">
    <div class="form-section">
      <div class="section-header">
        <h3>{{ t('core.setting.func.featureSection') }}</h3>
      </div>
      <div class="setting-control-row retention-row">
        <span class="setting-row-label">{{ t('core.setting.func.retention') }}</span>
        <a-tooltip :title="t('core.setting.func.retentionTip')">
          <QuestionCircleOutlined class="help-icon" />
        </a-tooltip>
        <a-select
          :value="settings.Function?.HistoryRetentionTime"
          :options="historyRetentionOptions"
          class="retention-select"
          @change="(value: any) => handleSettingChange('Function', 'HistoryRetentionTime', value)"
        />
      </div>
      <div class="setting-check-list">
        <div class="setting-check-row">
          <a-checkbox
            :checked="settings.Function?.IfSilence === true"
            @change="
              (event: CheckboxChangeEvent) =>
                handleSettingChange('Function', 'IfSilence', event.target.checked)
            "
          >
            {{ t('core.setting.func.silent') }}
          </a-checkbox>
          <a-tooltip :title="t('core.setting.func.silentTip')">
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
        </div>
        <div class="setting-check-row">
          <a-checkbox
            :checked="settings.Function?.IfAllowSleep === true"
            @change="
              (event: CheckboxChangeEvent) =>
                handleSettingChange('Function', 'IfAllowSleep', event.target.checked)
            "
          >
            {{ t('core.setting.func.preventSleep') }}
          </a-checkbox>
          <a-tooltip :title="t('core.setting.func.preventSleepTip')">
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
        </div>
        <div class="setting-check-row">
          <a-checkbox
            :checked="settings.Function?.IfEnableTelemetry !== false"
            @change="
              (event: CheckboxChangeEvent) =>
                handleSettingChange('Function', 'IfEnableTelemetry', event.target.checked)
            "
          >
            {{ t('core.setting.func.telemetry') }}
          </a-checkbox>
          <a-tooltip :title="t('core.setting.func.telemetryTip')">
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
        </div>
        <div class="setting-check-row">
          <a-checkbox
            :checked="settings.Function?.IfBlockAd === true"
            @change="
              (event: CheckboxChangeEvent) =>
                handleSettingChange('Function', 'IfBlockAd', event.target.checked)
            "
          >
            {{ t('core.setting.func.blockAds') }}
          </a-checkbox>
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
      </div>
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>{{ t('core.setting.func.voiceSection') }}</h3>
      </div>
      <div class="setting-check-row">
        <a-checkbox
          :checked="settings.Voice?.Enabled === true"
          @change="
            (event: CheckboxChangeEvent) =>
              handleSettingChange('Voice', 'Enabled', event.target.checked)
          "
        >
          {{ t('core.setting.func.voiceEnable') }}
        </a-checkbox>
        <a-tooltip :title="t('core.setting.func.voiceEnableTip')">
          <QuestionCircleOutlined class="help-icon" />
        </a-tooltip>
      </div>
      <div class="setting-control-row voice-type-row">
        <span class="setting-row-label">{{ t('core.setting.func.voiceType') }}</span>
        <a-tooltip :title="t('core.setting.func.voiceTypeTip')">
          <QuestionCircleOutlined class="help-icon" />
        </a-tooltip>
        <a-radio-group
          :value="settings.Voice?.Type"
          :disabled="!settings.Voice?.Enabled"
          :aria-label="t('core.setting.func.voiceType')"
          class="setting-radio-group"
          @change="
            (event: RadioChangeEvent) => handleSettingChange('Voice', 'Type', event.target.value)
          "
        >
          <a-radio v-for="option in voiceTypeOptions" :key="option.value" :value="option.value">
            {{ option.label }}
          </a-radio>
        </a-radio-group>
      </div>
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
      <div class="setting-check-row">
        <a-checkbox
          :checked="settings.Display?.IfEnableVirtualDisplay === true"
          :disabled="vddSwitchDisabled"
          @change="
            (event: CheckboxChangeEvent) =>
              handleSettingChange('Display', 'IfEnableVirtualDisplay', event.target.checked)
          "
        >
          {{ t('core.setting.display.enable') }}
        </a-checkbox>
        <a-tooltip :title="t('core.setting.display.enableTip')">
          <QuestionCircleOutlined class="help-icon" />
        </a-tooltip>
      </div>
      <div class="setting-control-row display-mode-row">
        <span class="setting-row-label">{{ t('core.setting.display.mode') }}</span>
        <a-tooltip :title="t('core.setting.display.modeTip')">
          <QuestionCircleOutlined class="help-icon" />
        </a-tooltip>
        <a-radio-group
          :value="settings.Display?.VirtualDisplayMode"
          :disabled="!settings.Display?.IfEnableVirtualDisplay"
          :aria-label="t('core.setting.display.mode')"
          class="setting-radio-group"
          @change="
            (event: RadioChangeEvent) =>
              handleSettingChange('Display', 'VirtualDisplayMode', event.target.value)
          "
        >
          <a-radio
            v-for="option in virtualDisplayModeOptions"
            :key="option.value"
            :value="option.value"
          >
            {{ option.label }}
          </a-radio>
        </a-radio-group>
      </div>
      <div class="display-actions">
        <a-tooltip :title="t('core.setting.display.checkTip')">
          <a-button :loading="vddChecking" @click="runVirtualDisplayCheck">
            {{ t('core.setting.display.checkAction') }}
          </a-button>
        </a-tooltip>
        <a-tooltip :title="t('core.setting.display.detachTip')">
          <a-button
            danger
            :disabled="!settings.Display?.IfEnableVirtualDisplay"
            :loading="vddDetaching"
            @click="runVirtualDisplayDetach"
          >
            {{ t('core.setting.display.detachAction') }}
          </a-button>
        </a-tooltip>
      </div>
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
.setting-check-list {
  display: grid;
  gap: 8px;
}

.setting-check-row,
.setting-control-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  min-height: 28px;
}

.setting-check-row {
  width: fit-content;
  max-width: 100%;
}

.setting-row-label {
  color: var(--ant-color-text);
  font-size: 14px;
}

.retention-row {
  margin-bottom: 16px;
}

.retention-select {
  width: 160px;
}

.voice-type-row,
.display-mode-row {
  margin-top: 12px;
}

.setting-radio-group,
.display-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
}

.setting-radio-group :deep(.ant-radio-wrapper) {
  margin-inline-end: 0;
}

.display-actions {
  margin-top: 16px;
}

.help-icon {
  flex: 0 0 auto;
  color: var(--ant-color-text-tertiary);
  font-size: 13px;
}

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
