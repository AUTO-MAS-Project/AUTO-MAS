<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { SettingsCategory, SettingsViewModel } from '@/types/settings'
import SettingGroupRenderer from './components/SettingGroupRenderer.vue'
import {
  settingFieldLabels,
  settingFieldTips,
  settingOptionLabels,
} from './components/settingUiText'

const props = defineProps<{
  settings: SettingsViewModel
  handleSettingChange: (category: SettingsCategory, key: string, value: unknown) => Promise<boolean>
}>()

const { t } = useI18n()
const hints = computed(() => props.settings.uiHints)
</script>

<template>
  <div class="tab-content">
    <div class="form-section">
      <div class="section-header">
        <h3>{{ t('setting.func.startupSection') }}</h3>
      </div>
      <SettingGroupRenderer
        group="start"
        category="Start"
        :settings="props.settings"
        :hints="hints"
        :label-keys="settingFieldLabels.start"
        :tip-keys="settingFieldTips.start"
        :handle-setting-change="props.handleSettingChange"
      />
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>{{ t('setting.func.featureSection') }}</h3>
      </div>
      <SettingGroupRenderer
        group="function"
        category="Function"
        :settings="props.settings"
        :hints="hints"
        :label-keys="settingFieldLabels.function"
        :tip-keys="settingFieldTips.function"
        :option-labels="settingOptionLabels.function"
        :handle-setting-change="props.handleSettingChange"
      />
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>{{ t('setting.func.voiceSection') }}</h3>
      </div>
      <SettingGroupRenderer
        group="voice"
        category="Voice"
        :settings="props.settings"
        :hints="hints"
        :label-keys="settingFieldLabels.voice"
        :tip-keys="settingFieldTips.voice"
        :option-labels="settingOptionLabels.voice"
        :disabled-fields="{ type: props.settings.Voice?.Enabled !== true }"
        :handle-setting-change="props.handleSettingChange"
      />
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>{{ t('setting.display.section') }}</h3>
      </div>
      <SettingGroupRenderer
        group="display"
        category="Display"
        :settings="props.settings"
        :hints="hints"
        :label-keys="settingFieldLabels.display"
        :tip-keys="settingFieldTips.display"
        :option-labels="settingOptionLabels.display"
        :disabled-fields="{
          virtual_display_mode: props.settings.Display?.IfEnableVirtualDisplay !== true,
        }"
        :handle-setting-change="props.handleSettingChange"
      />
    </div>
  </div>
</template>
