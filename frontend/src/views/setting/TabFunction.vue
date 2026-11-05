<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed } from 'vue'
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ControlOutlined,
  DesktopOutlined,
  QuestionCircleOutlined,
  SoundOutlined,
} from '@ant-design/icons-vue'
import type { GlobalConfig } from '@/api'
import { useVirtualDisplaySettings } from './useVirtualDisplaySettings'
import { openExternalUrl } from '@/utils/openExternal'
import { navigateTo } from '@/router'
import SectionCard from '@/components/ui/SectionCard.vue'
import SettingRow from '@/components/ui/SettingRow.vue'
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
    <!-- 功能：历史保留时长 + 四个全局开关，一项一行 -->
    <SectionCard :title="t('core.setting.func.featureSection')" :icon="ControlOutlined">
      <SettingRow
        :label="t('core.setting.func.retention')"
        :hint="t('core.setting.func.retentionTip')"
      >
        <a-select
          :value="settings.Function?.HistoryRetentionTime"
          :options="historyRetentionOptions"
          class="retention-select"
          :aria-label="t('core.setting.func.retention')"
          @change="(value: any) => handleSettingChange('Function', 'HistoryRetentionTime', value)"
        />
      </SettingRow>

      <SettingRow :label="t('core.setting.func.silent')" :hint="t('core.setting.func.silentTip')">
        <a-switch
          :checked="settings.Function?.IfSilence === true"
          :aria-label="t('core.setting.func.silent')"
          @change="
            (checked: boolean | string | number) =>
              handleSettingChange('Function', 'IfSilence', !!checked)
          "
        />
      </SettingRow>

      <SettingRow
        :label="t('core.setting.func.preventSleep')"
        :hint="t('core.setting.func.preventSleepTip')"
      >
        <a-switch
          :checked="settings.Function?.IfAllowSleep === true"
          :aria-label="t('core.setting.func.preventSleep')"
          @change="
            (checked: boolean | string | number) =>
              handleSettingChange('Function', 'IfAllowSleep', !!checked)
          "
        />
      </SettingRow>

      <SettingRow
        :label="t('core.setting.func.telemetry')"
        :hint="t('core.setting.func.telemetryTip')"
      >
        <a-switch
          :checked="settings.Function?.IfEnableTelemetry !== false"
          :aria-label="t('core.setting.func.telemetry')"
          @change="
            (checked: boolean | string | number) =>
              handleSettingChange('Function', 'IfEnableTelemetry', !!checked)
          "
        />
      </SettingRow>

      <!-- 拦广告的支持范围带列表，ⓘ 里放富文本，其余说明仍走 SettingRow 的 hint -->
      <SettingRow>
        <template #label>
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
            <span class="row-label" tabindex="0">
              {{ t('core.setting.func.blockAds') }}
              <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
            </span>
          </a-tooltip>
        </template>
        <a-switch
          :checked="settings.Function?.IfBlockAd === true"
          :aria-label="t('core.setting.func.blockAds')"
          @change="
            (checked: boolean | string | number) =>
              handleSettingChange('Function', 'IfBlockAd', !!checked)
          "
        />
      </SettingRow>
    </SectionCard>

    <!-- 语音：一个总开关 + 一个详细程度选择，关掉时类型选择跟着禁用 -->
    <SectionCard :title="t('core.setting.func.voiceSection')" :icon="SoundOutlined">
      <SettingRow
        :label="t('core.setting.func.voiceEnable')"
        :hint="t('core.setting.func.voiceEnableTip')"
      >
        <a-switch
          :checked="settings.Voice?.Enabled === true"
          :aria-label="t('core.setting.func.voiceEnable')"
          @change="
            (checked: boolean | string | number) =>
              handleSettingChange('Voice', 'Enabled', !!checked)
          "
        />
      </SettingRow>

      <SettingRow
        :label="t('core.setting.func.voiceType')"
        :hint="t('core.setting.func.voiceTypeTip')"
      >
        <a-segmented
          :value="settings.Voice?.Type"
          :options="voiceTypeOptions"
          :disabled="!settings.Voice?.Enabled"
          :aria-label="t('core.setting.func.voiceType')"
          @change="(value: any) => handleSettingChange('Voice', 'Type', value)"
        />
      </SettingRow>
    </SectionCard>

    <FailureReplaySettings :settings="settings" :handle-setting-change="handleSettingChange" />

    <!-- 虚拟显示器：驱动下载入口收进卡片头部，操作按钮与检测结果留在卡片内 -->
    <SectionCard :title="t('core.setting.display.section')" :icon="DesktopOutlined">
      <template #actions>
        <a-button type="link" size="small" class="header-link" @click="openVddDownload">
          {{ t('core.setting.display.download') }}
        </a-button>
      </template>

      <!-- 原 intro 是一整段告警，正文只留驱动这一句，来龙去脉收进 ⓘ -->
      <p class="card-note">
        <a-tooltip>
          <template #title>
            <i18n-t keypath="core.setting.display.intro" tag="span" scope="global">
              <template #driverLink>{{ t('core.setting.display.introDriverLink') }}</template>
            </i18n-t>
          </template>
          <span class="card-note-hint" tabindex="0">
            {{ t('core.setting.display.introDriverLink') }}
            <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
          </span>
        </a-tooltip>
      </p>

      <SettingRow
        :label="t('core.setting.display.enable')"
        :hint="t('core.setting.display.enableTip')"
      >
        <a-switch
          :checked="settings.Display?.IfEnableVirtualDisplay === true"
          :disabled="vddSwitchDisabled"
          :aria-label="t('core.setting.display.enable')"
          @change="
            (checked: boolean | string | number) =>
              handleSettingChange('Display', 'IfEnableVirtualDisplay', !!checked)
          "
        />
      </SettingRow>

      <SettingRow :label="t('core.setting.display.mode')" :hint="t('core.setting.display.modeTip')">
        <a-segmented
          :value="settings.Display?.VirtualDisplayMode"
          :options="virtualDisplayModeOptions"
          :disabled="!settings.Display?.IfEnableVirtualDisplay"
          :aria-label="t('core.setting.display.mode')"
          @change="(value: any) => handleSettingChange('Display', 'VirtualDisplayMode', value)"
        />
      </SettingRow>

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

      <p v-if="settings.Display?.IfEnableVirtualDisplay" class="vdd-holding card-note">
        {{
          vddHolding
            ? t('core.setting.display.holdingNow', { holding: vddHolding })
            : t('core.setting.display.holdingNone')
        }}
      </p>

      <a-alert v-if="vddWarning" type="warning" show-icon class="vdd-result">
        <template #message>{{ vddWarning }}</template>
        <template #description>
          <a href="#" @click.prevent="openVddDownload">
            {{ t('core.setting.display.download') }}
          </a>
        </template>
      </a-alert>

      <a-alert
        v-if="vddResult"
        :type="vddAllPassed ? 'success' : 'warning'"
        show-icon
        class="vdd-result"
      >
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
    </SectionCard>

    <!-- 个人版编排的「并非神秘入口」已移入神秘入口，这里只留群友的「神秘入口」一个入口 -->
    <div class="flavor-entries">
      <a-button type="text" size="small" @click="navigateTo('/settings/mystery')">
        {{ t('core.mystery.entry') }}
      </a-button>
    </div>
  </div>
</template>

<style scoped>
.retention-select {
  width: 220px;
}

/* 行标签沿用 SettingRow 的 form 级排版，供富文本 ⓘ 的行使用 */
.row-label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--ant-color-text);
  font-size: 14px;
  font-weight: 600;
  cursor: help;
}

.row-label:focus-visible {
  border-radius: 3px;
  outline: 2px solid var(--ant-color-primary);
  outline-offset: 2px;
}

.help-icon {
  flex: 0 0 auto;
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
}

.card-note {
  margin: 0 0 8px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  line-height: 1.6;
}

.card-note-hint {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: help;
}

.card-note-hint:focus-visible {
  border-radius: 3px;
  outline: 2px solid var(--ant-color-primary);
  outline-offset: 2px;
}

.header-link {
  padding: 0;
  height: auto;
}

.display-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 0 8px;
}

.vdd-holding {
  margin: 0;
}

.vdd-result {
  margin-top: 12px;
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

.flavor-entries {
  display: flex;
  justify-content: flex-end;
}

.flavor-entries :deep(.ant-btn) {
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}
</style>
