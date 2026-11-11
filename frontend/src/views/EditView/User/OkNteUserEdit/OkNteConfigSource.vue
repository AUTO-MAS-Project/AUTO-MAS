<template>
  <UniversalPlanSelector
    v-if="userId"
    :script-id="scriptId"
    :user-id="userId"
    :plan-mode="info.PlanMode"
    :plan-type="PLAN_CONFIG_TYPES.OKNTE"
    :disabled="disabled"
    @change="emit('plan-change', $event)"
  />
  <a-alert
    v-if="info.PlanMode !== 'Fixed'"
    type="info"
    show-icon
    :message="t('core.plan.oknte.priority')"
  />
  <GeneralConfigModeSelector
    :model-value="info.Base ?? 'shared'"
    :options="oknteConfigModeOptions"
    :disabled="disabled"
    :quick-config="info.IfQuickConfig ?? true"
    :quick-config-disabled="disabled"
    :alert-message="t('core.edit.configSourceHintBase')"
    @change="emit('base-change', $event)"
    @quick-config-change="emit('quick-change', $event)"
  />
</template>
<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { OkNteUserConfig } from '@/api'
import GeneralConfigModeSelector from '@/views/EditView/User/GeneralConfigModeSelector.vue'
import UniversalPlanSelector from '../UniversalPlanSelector.vue'
import { PLAN_CONFIG_TYPES } from '@/utils/planTypeRegistry'
const { t } = useI18n()
defineProps<{
  scriptId: string
  userId: string
  info: NonNullable<OkNteUserConfig['Info']>
  disabled: boolean
}>()
const oknteConfigModeOptions: Array<{
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
    description: t('core.edit.nativeConfigSourceDescription'),
    icon: 'setting',
  },
]

const emit = defineEmits<{
  'plan-change': [value: string]
  'base-change': [value: string]
  'quick-change': [value: boolean]
}>()
</script>
