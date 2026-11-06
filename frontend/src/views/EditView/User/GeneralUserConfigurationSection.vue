<template>
  <GeneralConfigModeSelector
    :model-value="modelValue"
    :options="generalConfigModeOptions"
    :disabled="disabled"
    :saving="saving"
    :alert-message="t('core.edit.generalConfigSourceHint')"
    @change="emit('change', $event)"
  />
  <UniversalPlanSelector
    v-if="owner.userId"
    :script-id="owner.scriptId"
    :user-id="owner.userId"
    :plan-mode="planMode"
    :disabled="disabled || saving"
    @change="emit('plan-change', $event)"
  />
</template>
<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import GeneralConfigModeSelector from './GeneralConfigModeSelector.vue'
import UniversalPlanSelector from './UniversalPlanSelector.vue'
const { t } = useI18n()
defineProps<{
  modelValue: string
  planMode?: string | null
  owner: { scriptId: string; userId: string }
  disabled?: boolean
  saving?: boolean
}>()
const emit = defineEmits<{
  change: [value: string | boolean]
  'plan-change': [value: string]
}>()
// 「共享」置灰：通用脚本运行/配置始终按 per-user 目录（AutoProxy/ScriptConfig 均不区分共享来源），
// 选了也不生效——禁用并悬停说明原因
const generalConfigModeOptions: Array<{
  label: string
  value: 'shared' | 'independent' | 'native'
  title: string
  description: string
  icon: 'database' | 'setting'
  disabled?: boolean
  disabledReason?: string
}> = [
  {
    label: t('core.edit.script'),
    value: 'shared',
    title: t('core.edit.script'),
    description: t('core.edit.useScriptS'),
    icon: 'database',
    disabled: true,
    disabledReason: t('core.edit.scriptModeDisabled'),
  },
  {
    label: t('core.edit.user'),
    value: 'independent',
    title: t('core.edit.user'),
    description: t('core.edit.useThisUserS'),
    icon: 'database',
  },
  {
    label: t('core.edit.directControl'),
    value: 'native',
    title: t('core.edit.directControl'),
    description: t('core.edit.useScriptSCurrent'),
    icon: 'setting',
  },
]
</script>
