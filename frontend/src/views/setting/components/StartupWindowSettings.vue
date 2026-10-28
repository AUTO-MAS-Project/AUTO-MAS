<script setup lang="ts">
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'
import type { CheckboxChangeEvent } from 'ant-design-vue/es/checkbox/interface'
import type { RadioChangeEvent } from 'ant-design-vue/es/radio/interface'
import type { GlobalConfig } from '@/api'
import CloseConfirmationSettings from './CloseConfirmationSettings.vue'
import TrayMenuEditor from './TrayMenuEditor.vue'

const { settings, handleSettingChange } = defineProps<{
  settings: GlobalConfig
  handleSettingChange: (category: keyof GlobalConfig, key: string, value: any) => Promise<boolean>
}>()

const { t } = useI18n()
</script>

<template>
  <div class="form-section startup-window-settings">
    <div class="section-header">
      <h3>{{ t('core.setting.basic.startupWindowSection') }}</h3>
    </div>

    <div class="setting-group">
      <div class="setting-group-title">{{ t('core.setting.basic.startupOptions') }}</div>
      <div class="setting-check-list">
        <div class="setting-check-row">
          <a-checkbox
            :checked="settings.Start?.IfSelfStart === true"
            @change="
              (event: CheckboxChangeEvent) =>
                handleSettingChange('Start', 'IfSelfStart', event.target.checked)
            "
          >
            {{ t('core.setting.func.autoStart') }}
          </a-checkbox>
          <a-tooltip :title="t('core.setting.func.autoStartTip')">
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
        </div>
        <div class="setting-check-row">
          <a-checkbox
            :checked="settings.Start?.IfMinimizeDirectly === true"
            @change="
              (event: CheckboxChangeEvent) =>
                handleSettingChange('Start', 'IfMinimizeDirectly', event.target.checked)
            "
          >
            {{ t('core.setting.func.startMinimized') }}
          </a-checkbox>
          <a-tooltip :title="t('core.setting.func.startMinimizedTip')">
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
        </div>
      </div>
    </div>

    <div class="setting-group">
      <div class="setting-group-title">{{ t('core.setting.basic.windowBehavior') }}</div>
      <div class="setting-radio-heading">
        <span id="minimize-behavior-label" class="setting-row-label">
          {{ t('core.setting.basic.minimizeBehavior') }}
        </span>
        <a-tooltip :title="t('core.setting.basic.minToTrayTip')">
          <QuestionCircleOutlined class="help-icon" />
        </a-tooltip>
      </div>
      <a-radio-group
        :value="settings.UI?.IfToTray ?? false"
        class="setting-radio-group"
        aria-labelledby="minimize-behavior-label"
        @change="
          (event: RadioChangeEvent) => handleSettingChange('UI', 'IfToTray', event.target.value)
        "
      >
        <a-radio :value="true">{{ t('core.setting.basic.minToTray') }}</a-radio>
        <a-radio :value="false">{{ t('core.setting.basic.minToTaskbar') }}</a-radio>
      </a-radio-group>

      <div class="setting-check-list">
        <div class="setting-check-row">
          <a-checkbox
            :checked="settings.UI?.IfShowTray === true"
            @change="
              (event: CheckboxChangeEvent) =>
                handleSettingChange('UI', 'IfShowTray', event.target.checked)
            "
          >
            {{ t('core.setting.basic.showTray') }}
          </a-checkbox>
          <a-tooltip :title="t('core.setting.basic.showTrayTip')">
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
        </div>
        <div class="setting-check-row">
          <a-checkbox
            :checked="settings.UI?.IfHideCloseButton === true"
            @change="
              (event: CheckboxChangeEvent) =>
                handleSettingChange('UI', 'IfHideCloseButton', event.target.checked)
            "
          >
            {{ t('core.setting.basic.hideClose') }}
          </a-checkbox>
          <a-tooltip :title="t('core.setting.basic.hideCloseTip')">
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
        </div>
        <CloseConfirmationSettings />
      </div>
    </div>

    <a-collapse ghost class="tray-menu-collapse">
      <a-collapse-panel key="tray-menu" :header="t('core.setting.tray.section')">
        <TrayMenuEditor />
      </a-collapse-panel>
    </a-collapse>
  </div>
</template>

<style scoped>
.setting-group + .setting-group {
  margin-top: 20px;
}

.setting-group-title {
  margin-bottom: 8px;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
}

.setting-check-list {
  display: grid;
  gap: 4px;
  margin-top: 16px;
}

.setting-check-row,
.setting-radio-heading {
  display: flex;
  align-items: center;
  min-height: 28px;
  gap: 8px;
}

.setting-check-row :deep(.ant-checkbox-wrapper),
.setting-radio-group :deep(.ant-radio-wrapper) {
  color: var(--ant-color-text);
  font-size: 14px;
}

.setting-radio-group {
  display: grid;
  gap: 4px;
  margin-top: 4px;
}

.setting-radio-group :deep(.ant-radio-wrapper) {
  min-height: 28px;
  margin-inline-end: 0;
}

.tray-menu-collapse {
  margin-top: 16px;
}

.tray-menu-collapse :deep(.ant-collapse-header) {
  padding-left: 0;
  color: var(--ant-color-text-secondary);
}

.tray-menu-collapse :deep(.ant-collapse-content-box) {
  padding-inline: 0;
}

.tray-menu-collapse :deep(.tray-menu-section-title) {
  display: none;
}

.help-icon {
  flex: 0 0 auto;
  color: var(--ant-color-text-tertiary);
  font-size: 13px;
}

.setting-row-label {
  color: var(--ant-color-text);
  font-size: 14px;
}
</style>
