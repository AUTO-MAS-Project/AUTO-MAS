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

    <div class="behavior-group">
      <div class="behavior-row">
        <span id="startup-options-label" class="behavior-label">
          {{ t('core.setting.basic.startupOptions') }}
        </span>
        <div class="behavior-content" role="group" aria-labelledby="startup-options-label">
          <div class="behavior-options">
            <div class="behavior-option">
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
            <a-checkbox
              :checked="settings.Start?.IfMinimizeDirectly === true"
              @change="
                (event: CheckboxChangeEvent) =>
                  handleSettingChange('Start', 'IfMinimizeDirectly', event.target.checked)
              "
            >
              {{ t('core.setting.func.startMinimized') }}
            </a-checkbox>
          </div>
          <p class="behavior-hint">{{ t('core.setting.basic.startupBehaviorHint') }}</p>
        </div>
      </div>
    </div>

    <div class="behavior-group">
      <div class="behavior-row">
        <span id="minimize-behavior-label" class="behavior-label">
          {{ t('core.setting.basic.minimizeBehavior') }}
        </span>
        <a-radio-group
          :value="settings.UI?.IfToTray ?? false"
          class="behavior-options"
          aria-labelledby="minimize-behavior-label"
          @change="
            (event: RadioChangeEvent) => handleSettingChange('UI', 'IfToTray', event.target.value)
          "
        >
          <a-radio :value="true">{{ t('core.setting.basic.minToTray') }}</a-radio>
          <a-radio :value="false">{{ t('core.setting.basic.minToTaskbar') }}</a-radio>
        </a-radio-group>
      </div>
      <div class="behavior-row">
        <span id="tray-display-label" class="behavior-label">
          {{ t('core.setting.basic.trayDisplay') }}
        </span>
        <div class="behavior-option" role="group" aria-labelledby="tray-display-label">
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
      </div>
      <div class="behavior-row">
        <span id="close-behavior-label" class="behavior-label">
          {{ t('core.setting.basic.closeBehavior') }}
        </span>
        <div class="behavior-content" role="group" aria-labelledby="close-behavior-label">
          <CloseConfirmationSettings />
          <p class="behavior-hint">{{ t('core.setting.basic.closeBehaviorHint') }}</p>
        </div>
      </div>
    </div>

    <TrayMenuEditor />
  </div>
</template>

<style scoped>
.behavior-group {
  padding: 0 20px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
}

.behavior-group + .behavior-group {
  margin-top: 16px;
}

.behavior-row {
  display: grid;
  grid-template-columns: 128px minmax(0, 1fr);
  align-items: start;
  gap: 16px;
  padding: 16px 0;
}

.behavior-row + .behavior-row {
  border-top: 1px solid var(--ant-color-border-secondary);
}

.behavior-label {
  padding-top: 4px;
  color: var(--ant-color-text-secondary);
  font-size: 14px;
  font-weight: 500;
  line-height: 22px;
}

.behavior-content {
  min-width: 0;
}

.behavior-options,
.behavior-option {
  display: flex;
  align-items: center;
  min-height: 28px;
  gap: 8px;
}

.behavior-options {
  flex-wrap: wrap;
  column-gap: 24px;
  row-gap: 8px;
}

.behavior-options :deep(.ant-checkbox-wrapper),
.behavior-option :deep(.ant-checkbox-wrapper),
.behavior-options :deep(.ant-radio-wrapper) {
  margin-inline-start: 0;
  margin-inline-end: 0;
  color: var(--ant-color-text);
  font-size: 14px;
}

.behavior-hint {
  margin: 6px 0 0;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  line-height: 20px;
}

.help-icon {
  flex: 0 0 auto;
  color: var(--ant-color-text-tertiary);
  font-size: 13px;
}

@media (max-width: 760px) {
  .behavior-group {
    padding-inline: 16px;
  }

  .behavior-row {
    grid-template-columns: minmax(0, 1fr);
    gap: 8px;
  }

  .behavior-label {
    padding-top: 0;
  }
}
</style>
