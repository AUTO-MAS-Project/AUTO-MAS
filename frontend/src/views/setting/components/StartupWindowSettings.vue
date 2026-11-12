<script setup lang="ts">
import { DesktopOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'
import type { CheckboxChangeEvent } from 'ant-design-vue/es/checkbox/interface'
import type { GlobalConfig } from '@/api'
import type { SettingChangeHandler } from '../settingTypes'
import SectionCard from '@/components/ui/SectionCard.vue'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import CloseConfirmationSettings from './CloseConfirmationSettings.vue'
import TrayMenuEditor from './TrayMenuEditor.vue'

const { settings, handleSettingChange } = defineProps<{
  settings: GlobalConfig
  handleSettingChange: SettingChangeHandler
}>()

const { t } = useI18n()

const startupOptions = [
  {
    key: 'IfScheduledWakeUp',
    label: 'core.setting.func.scheduledWakeup',
    hint: 'core.setting.func.scheduledWakeupTip',
  },
  {
    key: 'IfSelfStart',
    label: 'core.setting.func.autoStart',
    hint: 'core.setting.func.autoStartTip',
  },
  {
    key: 'IfMinimizeDirectly',
    label: 'core.setting.func.silentStart',
    hint: 'core.setting.func.silentStartTip',
  },
] as const
</script>

<template>
  <SectionCard
    class="startup-window-settings"
    :title="t('core.setting.basic.startupWindowSection')"
    :icon="DesktopOutlined"
  >
    <div class="settings-columns">
      <section class="setting-group">
        <h4 class="setting-group-title">{{ t('core.setting.func.startupGroup') }}</h4>

        <div
          v-for="option in startupOptions"
          :key="option.key"
          class="setting-item"
          :class="{ 'setting-item--nested': option.key === 'IfMinimizeDirectly' }"
        >
          <a-checkbox
            :checked="settings.Start?.[option.key] === true"
            @change="
              (event: CheckboxChangeEvent) =>
                handleSettingChange('Start', option.key, event.target.checked === true)
            "
          >
            {{ t(option.label) }}
          </a-checkbox>
          <FieldLabelWithHint class="setting-help" :hint="t(option.hint)" variant="form" />
        </div>
      </section>

      <section class="setting-group">
        <h4 class="setting-group-title">{{ t('core.setting.basic.closeBehavior') }}</h4>

        <CloseConfirmationSettings />
      </section>

      <section class="setting-group setting-group--wide">
        <h4 class="setting-group-title">{{ t('core.setting.basic.trayGroup') }}</h4>

        <div class="setting-item">
          <a-checkbox
            :checked="settings.UI?.IfShowTray === true"
            @change="
              (event: CheckboxChangeEvent) =>
                handleSettingChange('UI', 'IfShowTray', event.target.checked === true)
            "
          >
            {{ t('core.setting.basic.showTray') }}
          </a-checkbox>
          <FieldLabelWithHint
            class="setting-help"
            :hint="t('core.setting.basic.showTrayTip')"
            variant="form"
          />
        </div>

        <div class="setting-item setting-item--fill">
          <span class="setting-item-label">{{ t('core.setting.tray.section') }}</span>
          <FieldLabelWithHint
            class="setting-help"
            :hint="t('core.setting.tray.sectionTip')"
            variant="form"
          />
          <TrayMenuEditor class="setting-item-fill" />
        </div>
      </section>
    </div>
  </SectionCard>
</template>

<style scoped>
/* 两列：启动 / 关闭时并排，托盘跨两列。分组标题负责分区，列内不再画线。 */
.settings-columns {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  column-gap: 48px;
  row-gap: 12px;
}

.setting-group--wide {
  grid-column: 1 / -1;
}

@container (max-width: 520px) {
  .settings-columns {
    grid-template-columns: minmax(0, 1fr);
  }

  .setting-group--wide {
    grid-column: auto;
  }
}

.setting-group-title {
  margin: 0;
  padding: 8px 0 2px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.02em;
  line-height: 18px;
}

.setting-item {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 36px;
  color: var(--ant-color-text);
  font-size: 14px;
  font-weight: 500;
}

/* 静默启动缩进展示，区别启动来源与启动方式。 */
.setting-item--nested {
  padding-left: 24px;
}

.setting-item--fill {
  width: 100%;
  min-width: 0;
}

.setting-item-fill {
  flex: 1;
  min-width: 0;
}

.setting-item :deep(.ant-checkbox-wrapper) {
  margin: 0;
  font-size: 14px;
  font-weight: 500;
}

.setting-item-label {
  color: var(--ant-color-text);
  font-size: 14px;
  font-weight: 500;
  white-space: nowrap;
}

.setting-help {
  flex: 0 0 auto;
}

.setting-help :deep(.help-icon) {
  color: var(--ant-color-text-quaternary);
}

.setting-help :deep(.help-icon:hover) {
  color: var(--ant-color-primary);
}
</style>
