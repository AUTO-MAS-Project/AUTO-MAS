<script setup lang="ts">
import { computed } from 'vue'
import { DesktopOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'
import type { GlobalConfig } from '@/api'
import type { SettingChangeHandler } from '../settingTypes'
import SectionCard from '@/components/ui/SectionCard.vue'
import SettingRow from '@/components/ui/SettingRow.vue'
import CloseConfirmationSettings from './CloseConfirmationSettings.vue'
import TrayMenuEditor from './TrayMenuEditor.vue'

const { settings, handleSettingChange } = defineProps<{
  settings: GlobalConfig
  handleSettingChange: SettingChangeHandler
}>()

const { t } = useI18n()

type StartKey = 'IfSelfStart' | 'IfScheduledWakeUp' | 'IfMinimizeDirectly'

const startValue = (key: StartKey) => settings.Start?.[key] === true
const setStart = (key: StartKey, value: boolean) =>
  handleSettingChange('Start', key, value)

// 静默启动只在自启或定时唤醒拉起时生效（main.ts：isAutoStart && IfMinimizeDirectly）。
// 两个入口都关着时它不会起作用，禁用而不是让用户拨一个没有效果的开关。
const silentAvailable = computed(
  () => settings.Start?.IfSelfStart === true || settings.Start?.IfScheduledWakeUp === true
)
</script>

<template>
  <SectionCard
    class="startup-window-settings"
    :title="t('core.setting.basic.startupWindowSection')"
    :icon="DesktopOutlined"
  >
    <section class="setting-group">
      <h4 class="setting-group-title">{{ t('core.setting.func.startupGroup') }}</h4>

      <SettingRow
        :label="t('core.setting.func.autoStart')"
        :hint="t('core.setting.func.autoStartTip')"
      >
        <a-switch
          :checked="startValue('IfSelfStart')"
          :aria-label="t('core.setting.func.autoStart')"
          @change="setStart('IfSelfStart', $event === true)"
        />
      </SettingRow>

      <SettingRow
        child
        :disabled="!silentAvailable"
        :label="t('core.setting.func.silentStart')"
        :description="t('core.setting.func.silentStartTip')"
      >
        <a-switch
          :checked="startValue('IfMinimizeDirectly')"
          :disabled="!silentAvailable"
          :aria-label="t('core.setting.func.silentStart')"
          @change="setStart('IfMinimizeDirectly', $event === true)"
        />
      </SettingRow>

      <SettingRow
        :label="t('core.setting.func.scheduledWakeup')"
        :hint="t('core.setting.func.scheduledWakeupTip')"
      >
        <a-switch
          :checked="startValue('IfScheduledWakeUp')"
          :aria-label="t('core.setting.func.scheduledWakeup')"
          @change="setStart('IfScheduledWakeUp', $event === true)"
        />
      </SettingRow>
    </section>

    <section class="setting-group">
      <h4 class="setting-group-title">{{ t('core.setting.basic.closeBehavior') }}</h4>
      <CloseConfirmationSettings />
    </section>

    <section class="setting-group">
      <h4 class="setting-group-title">{{ t('core.setting.basic.trayGroup') }}</h4>

      <SettingRow
        :label="t('core.setting.basic.showTray')"
        :hint="t('core.setting.basic.showTrayTip')"
      >
        <a-switch
          :checked="settings.UI?.IfShowTray === true"
          :aria-label="t('core.setting.basic.showTray')"
          @change="handleSettingChange('UI', 'IfShowTray', $event === true)"
        />
      </SettingRow>

      <TrayMenuEditor />
    </section>
  </SectionCard>
</template>

<style scoped>
/* A 版：单列行式。分组标题用正文色/13px 承担分区，行分隔交给 SettingRow 自己画。 */
.setting-group-title {
  margin: 6px 0 0;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
  color: var(--ant-color-text);
  font-size: 13px;
  font-weight: 600;
  line-height: 20px;
}

.setting-group + .setting-group {
  margin-top: 10px;
}
</style>
