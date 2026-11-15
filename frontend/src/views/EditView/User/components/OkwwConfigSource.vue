<template>
  <UniversalPlanSelector
    :script-id="scriptId"
    :user-id="userId"
    :plan-mode="info.PlanMode"
    :plan-type="PLAN_CONFIG_TYPES.OKWW"
    :disabled="disabled"
    @change="emit('plan-change', $event)"
  />

  <GeneralConfigModeSelector
    :model-value="info.Base ?? 'shared'"
    :options="okwwConfigModeOptions"
    :disabled="disabled"
    :saving="saving"
    :quick-config="info.IfQuickConfig ?? true"
    :quick-config-disabled="disabled || initializing"
    :alert-message="t('core.edit.configSourceHintBase')"
    :show-gui-hint="false"
    @change="emit('base-change', $event)"
    @quick-config-change="emit('quick-change', $event)"
  />
</template>
<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { OkwwUserConfig } from '@/api'
import UniversalPlanSelector from '../UniversalPlanSelector.vue'
import GeneralConfigModeSelector from '../GeneralConfigModeSelector.vue'
import { PLAN_CONFIG_TYPES } from '@/utils/planTypeRegistry'
const { t } = useI18n()
defineProps<{
  scriptId: string
  userId: string
  info: NonNullable<OkwwUserConfig['Info']>
  disabled: boolean
  saving: boolean
  initializing: boolean
}>()
const emit = defineEmits<{
  'plan-change': [value: string]
  'base-change': [value: boolean | string]
  'quick-change': [value: boolean]
}>()
const okwwConfigModeOptions: Array<{
  label: string
  value: 'shared' | 'independent' | 'native'
  title: string
  description: string
  icon: 'file' | 'database' | 'setting'
}> = [
  {
    label: t('core.edit.script'),
    value: 'shared',
    title: t('core.edit.script'),
    description: t('core.edit.useSharedScriptLevel'),
    icon: 'file',
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
    description: t('core.edit.useExistingOkwwConfiguration'),
    icon: 'setting',
  },
]
</script>
