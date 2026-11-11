<script setup lang="ts">
import { DesktopOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'
import type { CheckboxChangeEvent } from 'ant-design-vue/es/checkbox/interface'
import type { GlobalConfig } from '@/api'
import type { SettingChangeHandler } from '../settingTypes'
import SectionCard from '@/components/ui/SectionCard.vue'
import CloseBehaviorSettings from './CloseBehaviorSettings.vue'
import CloseConfirmationSettings from './CloseConfirmationSettings.vue'
import TrayMenuEditor from './TrayMenuEditor.vue'

const { settings, handleSettingChange } = defineProps<{
  settings: GlobalConfig
  handleSettingChange: SettingChangeHandler
}>()

const { t } = useI18n()
</script>

<template>
  <SectionCard
    class="startup-window-settings"
    :title="t('core.setting.basic.startupWindowSection')"
    :icon="DesktopOutlined"
  >
    <div class="settings-grid">
      <section class="settings-group">
        <h4 class="settings-group-title">{{ t('core.setting.func.startupGroup') }}</h4>

        <div class="option-list">
          <div class="option-row">
            <a-checkbox
              :checked="settings.Start?.IfSelfStart === true"
              @change="
                (event: CheckboxChangeEvent) =>
                  handleSettingChange('Start', 'IfSelfStart', event.target.checked === true)
              "
            >
              {{ t('core.setting.func.autoStart') }}
            </a-checkbox>
            <a-tooltip :title="t('core.setting.func.autoStartTip')">
              <QuestionCircleOutlined
                class="help-icon option-help"
                tabindex="0"
                :aria-label="t('core.setting.func.autoStartTip')"
              />
            </a-tooltip>
          </div>

          <div class="option-row">
            <a-checkbox
              :checked="settings.Start?.IfMinimizeDirectly === true"
              :disabled="settings.Start?.IfSelfStart !== true"
              @change="
                (event: CheckboxChangeEvent) =>
                  handleSettingChange('Start', 'IfMinimizeDirectly', event.target.checked === true)
              "
            >
              {{ t('core.setting.func.silentStart') }}
            </a-checkbox>
            <a-tooltip :title="t('core.setting.func.silentStartTip')">
              <QuestionCircleOutlined
                class="help-icon option-help"
                tabindex="0"
                :aria-label="t('core.setting.func.silentStartTip')"
              />
            </a-tooltip>
          </div>

          <div class="option-row">
            <a-checkbox
              :checked="settings.Start?.IfScheduledWakeUp === true"
              @change="
                (event: CheckboxChangeEvent) =>
                  handleSettingChange('Start', 'IfScheduledWakeUp', event.target.checked === true)
              "
            >
              {{ t('core.setting.func.scheduledWakeup') }}
            </a-checkbox>
            <a-tooltip :title="t('core.setting.func.scheduledWakeupTip')">
              <QuestionCircleOutlined
                class="help-icon option-help"
                tabindex="0"
                :aria-label="t('core.setting.func.scheduledWakeupTip')"
              />
            </a-tooltip>
          </div>
        </div>
      </section>

      <section class="settings-group">
        <h4 class="settings-group-title">{{ t('core.setting.basic.closeBehavior') }}</h4>

        <CloseBehaviorSettings />

        <div class="option-row option-row--solo">
          <CloseConfirmationSettings />
        </div>
      </section>

      <section class="settings-group settings-group--wide">
        <h4 class="settings-group-title">{{ t('core.setting.basic.trayGroup') }}</h4>

        <div class="option-list">
          <div class="option-row">
            <a-checkbox
              :checked="settings.UI?.IfShowTray === true"
              @change="
                (event: CheckboxChangeEvent) =>
                  handleSettingChange('UI', 'IfShowTray', event.target.checked === true)
              "
            >
              {{ t('core.setting.basic.showTray') }}
            </a-checkbox>
            <a-tooltip :title="t('core.setting.basic.showTrayTip')">
              <QuestionCircleOutlined
                class="help-icon option-help"
                tabindex="0"
                :aria-label="t('core.setting.basic.showTrayTip')"
              />
            </a-tooltip>
          </div>

          <div class="option-row">
            <span class="option-name">{{ t('core.setting.tray.section') }}</span>
            <a-tooltip :title="t('core.setting.tray.sectionTip')">
              <QuestionCircleOutlined
                class="help-icon option-help"
                tabindex="0"
                :aria-label="t('core.setting.tray.sectionTip')"
              />
            </a-tooltip>
            <TrayMenuEditor />
          </div>
        </div>
      </section>
    </div>
  </SectionCard>
</template>

<style scoped>
/* 宽卡片两列排布，让内容铺满卡片宽度；窄卡片回落单列。 */
.settings-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  column-gap: 40px;
}

.settings-group--wide {
  grid-column: 1 / -1;
}

@container (max-width: 520px) {
  .settings-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .settings-group--wide {
    grid-column: auto;
  }
}

.settings-group-title {
  margin: 0;
  padding: 14px 0 2px;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
  font-weight: 600;
  line-height: 20px;
}

.option-list {
  display: flex;
  flex-direction: column;
}

/* 行式设置：勾选框紧贴功能名，行间用极淡分隔线形成清单结构。 */
.option-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 42px;
  padding: 0 6px;
  margin: 0 -6px;
  border-radius: var(--ant-border-radius-sm);
  color: var(--ant-color-text);
  font-size: 14px;
  font-weight: 500;
  transition: background-color 0.2s ease;
}

.option-row:hover {
  background: var(--ant-color-fill-quaternary);
}

.option-row + .option-row,
.option-row--solo {
  border-top: 1px solid var(--ant-color-split);
}

.option-row :deep(.ant-checkbox-wrapper) {
  margin: 0;
  font-size: 14px;
  font-weight: 500;
}

.option-name {
  white-space: nowrap;
}

.option-help {
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
  cursor: help;
}

.option-help:hover {
  color: var(--ant-color-primary);
}

.startup-window-settings :deep(.tray-menu-summary) {
  padding: 2px 0 4px;
}
</style>
