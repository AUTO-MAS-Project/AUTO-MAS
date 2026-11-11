<script setup lang="ts">
import { DesktopOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'
import type { GlobalConfig } from '@/api'
import type { SettingChangeHandler } from '../settingTypes'
import SectionCard from '@/components/ui/SectionCard.vue'
import SettingRow from '@/components/ui/SettingRow.vue'
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
    <SettingRow
      :label="t('core.setting.func.autoStart')"
      :hint="t('core.setting.func.autoStartTip')"
    >
      <a-switch
        :checked="settings.Start?.IfSelfStart === true"
        :aria-label="t('core.setting.func.autoStart')"
        @change="
          (checked: boolean | string | number) =>
            handleSettingChange('Start', 'IfSelfStart', !!checked)
        "
      />
    </SettingRow>

    <SettingRow
      :label="t('core.setting.func.silentStart')"
      :hint="t('core.setting.func.silentStartTip')"
    >
      <a-switch
        :checked="settings.Start?.IfMinimizeDirectly === true"
        :disabled="settings.Start?.IfSelfStart !== true"
        :aria-label="t('core.setting.func.silentStart')"
        @change="
          (checked: boolean | string | number) =>
            handleSettingChange('Start', 'IfMinimizeDirectly', !!checked)
        "
      />
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

    <SettingRow :label="t('core.setting.basic.closeBehavior')">
      <CloseBehaviorSettings />
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
