<script setup lang="ts">
import { DesktopOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'
import type { CheckboxChangeEvent } from 'ant-design-vue/es/checkbox/interface'
import type { GlobalConfig } from '@/api'
import SectionCard from '@/components/ui/SectionCard.vue'
import SettingRow from '@/components/ui/SettingRow.vue'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import CloseConfirmationSettings from './CloseConfirmationSettings.vue'
import TrayMenuEditor from './TrayMenuEditor.vue'

const { settings, handleSettingChange } = defineProps<{
  settings: GlobalConfig
  handleSettingChange: (category: keyof GlobalConfig, key: string, value: any) => Promise<boolean>
}>()

const { t } = useI18n()
</script>

<template>
  <SectionCard
    class="startup-window-settings"
    :title="t('core.setting.basic.startupWindowSection')"
    :icon="DesktopOutlined"
  >
    <SettingRow
      class="startup-options-row"
      :label="t('core.setting.basic.startupOptions')"
      :hint="t('core.setting.basic.startupBehaviorHint')"
    >
      <a-checkbox
        :checked="settings.Start?.IfSelfStart === true"
        @change="
          (event: CheckboxChangeEvent) =>
            handleSettingChange('Start', 'IfSelfStart', event.target.checked)
        "
      >
        <FieldLabelWithHint
          :text="t('core.setting.func.autoStart')"
          :hint="t('core.setting.func.autoStartTip')"
        />
      </a-checkbox>
      <a-checkbox
        :checked="settings.Start?.IfMinimizeDirectly === true"
        @change="
          (event: CheckboxChangeEvent) =>
            handleSettingChange('Start', 'IfMinimizeDirectly', event.target.checked)
        "
      >
        {{ t('core.setting.func.startMinimized') }}
      </a-checkbox>
    </SettingRow>

    <SettingRow
      :label="t('core.setting.func.scheduledWakeup')"
      :hint="t('core.setting.func.scheduledWakeupTip')"
    >
      <a-switch
        :checked="settings.Start?.IfScheduledWakeUp === true"
        :aria-label="t('core.setting.func.scheduledWakeup')"
        @change="
          (checked: boolean | string | number) =>
            handleSettingChange('Start', 'IfScheduledWakeUp', !!checked)
        "
      />
    </SettingRow>

    <SettingRow :label="t('core.setting.basic.minimizeBehavior')">
      <a-segmented
        :value="settings.UI?.IfToTray === true ? 'tray' : 'taskbar'"
        :options="[
          { label: t('core.setting.basic.minToTray'), value: 'tray' },
          { label: t('core.setting.basic.minToTaskbar'), value: 'taskbar' },
        ]"
        :aria-label="t('core.setting.basic.minimizeBehavior')"
        @change="
          (value: string | number) => handleSettingChange('UI', 'IfToTray', value === 'tray')
        "
      />
    </SettingRow>

    <SettingRow
      :label="t('core.setting.basic.showTray')"
      :hint="t('core.setting.basic.showTrayTip')"
    >
      <a-switch
        :checked="settings.UI?.IfShowTray === true"
        :aria-label="t('core.setting.basic.showTray')"
        @change="
          (checked: boolean | string | number) => handleSettingChange('UI', 'IfShowTray', !!checked)
        "
      />
    </SettingRow>

    <SettingRow
      :label="t('core.setting.basic.closeConfirmation')"
      :description="t('core.setting.basic.closeBehaviorHint')"
    >
      <CloseConfirmationSettings />
    </SettingRow>

    <TrayMenuEditor />
  </SectionCard>
</template>

<style scoped>
.settings-card-grid .startup-window-settings :deep(.ui-row.startup-options-row) {
  grid-template-columns: auto minmax(0, 1fr);
}

@container (max-width: 560px) {
  .settings-card-grid .startup-window-settings :deep(.ui-row.startup-options-row) {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
