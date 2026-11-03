<script setup lang="ts">
import { PoweroffOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'
import type { CheckboxChangeEvent } from 'ant-design-vue/es/checkbox/interface'
import type { RadioChangeEvent } from 'ant-design-vue/es/radio/interface'
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
    :icon="PoweroffOutlined"
  >
    <SettingRow
      :label="t('core.setting.basic.startupOptions')"
      :description="t('core.setting.basic.startupBehaviorHint')"
      stacked
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

    <SettingRow :label="t('core.setting.basic.minimizeBehavior')">
      <a-radio-group
        :value="settings.UI?.IfToTray ?? false"
        :aria-label="t('core.setting.basic.minimizeBehavior')"
        @change="
          (event: RadioChangeEvent) => handleSettingChange('UI', 'IfToTray', event.target.value)
        "
      >
        <a-radio :value="true">{{ t('core.setting.basic.minToTray') }}</a-radio>
        <a-radio :value="false">{{ t('core.setting.basic.minToTaskbar') }}</a-radio>
      </a-radio-group>
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
