<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed } from 'vue'
import { ControlOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { GlobalConfig } from '@/api'
import type { SettingChangeHandler } from './settingTypes'
import { navigateTo } from '@/router'
import SectionCard from '@/components/ui/SectionCard.vue'
import SettingRow from '@/components/ui/SettingRow.vue'
import FailureReplaySettings from './components/FailureReplaySettings.vue'
import VoiceSettings from './components/VoiceSettings.vue'
import DesktopSessionSettings from '../desktopSession/DesktopSessionSettings.vue'

const { t } = useI18n()

const { settings, handleSettingChange } = defineProps<{
  settings: GlobalConfig
  handleSettingChange: SettingChangeHandler
}>()

type HistoryRetentionTime = NonNullable<
  NonNullable<GlobalConfig['Function']>['HistoryRetentionTime']
>
const historyRetentionOptions = computed<{ label: string; value: HistoryRetentionTime }[]>(() => [
  { label: t('core.setting.retention.d7'), value: 7 },
  { label: t('core.setting.retention.d15'), value: 15 },
  { label: t('core.setting.retention.d30'), value: 30 },
  { label: t('core.setting.retention.d60'), value: 60 },
  { label: t('core.setting.retention.d90'), value: 90 },
  { label: t('core.setting.retention.d180'), value: 180 },
  { label: t('core.setting.retention.d365'), value: 365 },
  { label: t('core.setting.retention.forever'), value: 0 },
])

const handleHistoryRetentionChange = (value: unknown) => {
  const option = historyRetentionOptions.value.find(option => option.value === value)
  if (option) void handleSettingChange('Function', 'HistoryRetentionTime', option.value)
}
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
          @change="handleHistoryRetentionChange"
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
          <span class="row-label">
            {{ t('core.setting.func.blockAds') }}
            <a-tooltip :trigger="['hover', 'focus']">
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
              <QuestionCircleOutlined
                class="help-icon"
                tabindex="0"
                :aria-label="t('core.setting.func.blockAds')"
              />
            </a-tooltip>
          </span>
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

    <FailureReplaySettings :settings="settings" :handle-setting-change="handleSettingChange" />

    <!-- 双列时卡片按序号轮流放左右列：分身排第三张落在左列，与右列的失败回放 + 语音提示高度相近 -->
    <DesktopSessionSettings :settings="settings" :handle-setting-change="handleSettingChange" />

    <VoiceSettings :settings="settings.Voice" :handle-setting-change="handleSettingChange" />

    <!-- 个人版编排的「并非神秘入口」已移入神秘入口，这里只留群友的「神秘入口」一个入口 -->
    <div class="flavor-entries">
      <a-button
        type="text"
        size="small"
        class="mystery-entry"
        @click="navigateTo('/settings/mystery')"
      >
        <span class="mystery-entry-label">{{ t('core.mystery.entry') }}</span>
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
}

.help-icon:focus-visible {
  border-radius: 3px;
  outline: 2px solid var(--ant-color-primary);
  outline-offset: 2px;
}

.help-icon {
  flex: 0 0 auto;
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
  cursor: help;
}

.flavor-entries {
  display: flex;
  justify-content: flex-end;
}

.flavor-entries :deep(.ant-btn) {
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}

.mystery-entry {
  opacity: 0;
}

.mystery-entry:hover,
.mystery-entry:focus {
  opacity: 1;
}

.mystery-entry-label {
  background-image: linear-gradient(
    90deg,
    var(--ant-color-primary),
    var(--ant-color-error),
    var(--ant-color-warning),
    var(--ant-color-success),
    var(--ant-color-primary)
  );
  background-size: 200% 100%;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  animation: mystery-entry-flow 3s linear infinite paused;
}

.mystery-entry:hover .mystery-entry-label,
.mystery-entry:focus .mystery-entry-label {
  animation-play-state: running;
}

@keyframes mystery-entry-flow {
  to {
    background-position: 200% 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .mystery-entry-label {
    animation: none;
  }
}

@media (forced-colors: active) {
  .mystery-entry-label {
    background: none;
    -webkit-text-fill-color: currentColor;
    animation: none;
  }
}
</style>
