<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { SoundOutlined } from '@ant-design/icons-vue'
import type { GlobalConfig } from '@/api'
import type { SettingChangeHandler } from '../settingTypes'
import SectionCard from '@/components/ui/SectionCard.vue'
import SettingRow from '@/components/ui/SettingRow.vue'

const { settings, handleSettingChange } = defineProps<{
  settings: GlobalConfig['Voice']
  handleSettingChange: SettingChangeHandler
}>()

const { t } = useI18n()
type VoiceType = NonNullable<NonNullable<GlobalConfig['Voice']>['Type']>
const voiceTypeOptions = computed<{ label: string; value: VoiceType }[]>(() => [
  { label: t('core.setting.voice.simple'), value: 'simple' },
  { label: t('core.setting.voice.noisy'), value: 'noisy' },
])

const handleVoiceTypeChange = (value: unknown) => {
  const option = voiceTypeOptions.value.find(option => option.value === value)
  if (option) void handleSettingChange('Voice', 'Type', option.value)
}
</script>

<template>
  <!-- 语音：一个总开关 + 一个详细程度选择，关掉时类型选择跟着禁用 -->
  <SectionCard :title="t('core.setting.func.voiceSection')" :icon="SoundOutlined">
    <SettingRow
      :label="t('core.setting.func.voiceEnable')"
      :hint="t('core.setting.func.voiceEnableTip')"
    >
      <a-switch
        :checked="settings?.Enabled === true"
        :aria-label="t('core.setting.func.voiceEnable')"
        @change="
          (checked: boolean | string | number) => handleSettingChange('Voice', 'Enabled', !!checked)
        "
      />
    </SettingRow>

    <SettingRow
      :label="t('core.setting.func.voiceType')"
      :hint="t('core.setting.func.voiceTypeTip')"
    >
      <a-segmented
        :value="settings?.Type"
        :options="voiceTypeOptions"
        :disabled="!settings?.Enabled"
        :aria-label="t('core.setting.func.voiceType')"
        @change="handleVoiceTypeChange"
      />
    </SettingRow>
  </SectionCard>
</template>
