<template>
  <div>
    <a-row :gutter="24">
      <a-col :xs="24" :sm="12">
        <a-form-item :label="t('core.edit.maaEndEssenceConfigMode')">
          <a-select
            :value="formData.Info.AutoEssenceMode"
            :options="modeOptions"
            :disabled="loading"
            @change="(value: string) => emit('save', 'Info.AutoEssenceMode', value)"
          />
        </a-form-item>
      </a-col>
      <template v-if="formData.Info.AutoEssenceMode !== 'Native'">
        <a-col :xs="24" :sm="12">
          <a-form-item :label="t('core.edit.maaEndEssenceFarmMode')">
            <div v-if="isPlanMode" class="plan-mode-display">{{ displayMenu }}</div>
            <a-select
              v-else
              :value="formData.Task.AutoEssenceMenu"
              :options="menus"
              :disabled="disabled"
              @change="(value: string) => emit('save', 'Task.AutoEssenceMenu', value)"
            />
          </a-form-item>
        </a-col>
        <a-col v-if="menu !== 'Random'" :xs="24" :sm="12">
          <a-form-item
            :label="
              t(
                menu === 'Target'
                  ? 'core.edit.maaEndEssenceWeapons'
                  : 'core.edit.maaEndEssenceLocation'
              )
            "
          >
            <div v-if="isPlanMode" class="plan-mode-display">{{ displayTask }}</div>
            <a-select
              v-else
              :value="
                menu === 'Target'
                  ? formData.Task.AutoEssenceTargetWeapons
                  : formData.Task.AutoEssenceSpecifiedLocation
              "
              :mode="menu === 'Target' ? 'multiple' : undefined"
              :options="taskOptions"
              :disabled="disabled"
              :loading="optionsLoading"
              @change="handleTaskChange"
            />
          </a-form-item>
        </a-col>
      </template>
    </a-row>
    <a-button
      v-if="formData.Info.AutoEssenceMode === 'Native'"
      :loading="configLoading"
      :disabled="loading || showConfigMask"
      @click="emit('configure')"
    >
      {{ t('core.edit.maaEndConfigureInventory') }}
    </a-button>
    <a-alert
      v-if="isPlanMode && planModeConfig && planModeConfig.SanityTaskType !== 'Essence'"
      type="info"
      show-icon
      :message="t('core.edit.maaEndEssencePlanSkipped')"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ComboBoxItem } from '@/api'
import type { MaaEndUserForm } from './userDefaults'
import {
  AUTO_ESSENCE_MENU_OPTIONS,
  getEssenceTargetWeaponOptions,
  getSanityTaskDisplayValue,
  type MaaEndSanityConfig,
  type MaaEndEssenceTargetGroup,
} from '@/utils/maaEndProtocolSpace'

const props = defineProps<{
  formData: MaaEndUserForm
  loading: boolean
  optionsLoading: boolean
  optionsLoaded: boolean
  configLoading: boolean
  showConfigMask: boolean
  essenceLocationOptions: ComboBoxItem[]
  essenceMenuOptions: ComboBoxItem[]
  essenceTargetWeaponGroups: MaaEndEssenceTargetGroup[]
  sanityModeOptions: Array<{ label: string; value: string }>
  isPlanMode: boolean
  planModeConfig: MaaEndSanityConfig | null
}>()
const emit = defineEmits<{
  save: [key: string, value: unknown]
  configure: []
}>()
const { t } = useI18n()
const formData = props.formData
const disabled = computed(() => props.loading || props.optionsLoading)
const modeOptions = computed(() => [
  ...props.sanityModeOptions,
  { label: t('core.edit.maaEndOriginalStrategy'), value: 'Native' },
])
const menus = computed(() =>
  props.essenceMenuOptions.length
    ? props.essenceMenuOptions
    : props.optionsLoaded
      ? AUTO_ESSENCE_MENU_OPTIONS.filter(option => option.value === 'Location')
      : AUTO_ESSENCE_MENU_OPTIONS
)
const key = computed(() => (props.isPlanMode ? props.planModeConfig : null))
const menu = computed(() => key.value?.AutoEssenceMenu ?? formData.Task.AutoEssenceMenu)
const displayMenu = computed(
  () => menus.value.find(option => option.value === menu.value)?.label ?? menu.value
)
const taskOptions = computed(() =>
  menu.value === 'Target'
    ? getEssenceTargetWeaponOptions(
        props.essenceTargetWeaponGroups,
        formData.Task.AutoEssenceTargetWeapons
      )
    : props.essenceLocationOptions
)
const displayTask = computed(() =>
  key.value
    ? getSanityTaskDisplayValue(key.value, props.essenceLocationOptions, [])
    : t('core.edit.maaEndPlanUnavailable')
)
const handleTaskChange = (value: string | string[]) => {
  if (disabled.value) return
  emit(
    'save',
    menu.value === 'Target' ? 'Task.AutoEssenceTargetWeapons' : 'Task.AutoEssenceSpecifiedLocation',
    value
  )
}
watch(
  [
    () => props.loading,
    () => props.optionsLoading,
    () => props.essenceLocationOptions,
    () => formData.Task.AutoEssenceMenu,
  ],
  () => {
    if (
      disabled.value ||
      props.isPlanMode ||
      formData.Info.AutoEssenceMode === 'Native' ||
      menu.value !== 'Location'
    )
      return
    const first = props.essenceLocationOptions[0]?.value
    if (
      first &&
      !props.essenceLocationOptions.some(
        option => option.value === formData.Task.AutoEssenceSpecifiedLocation
      )
    ) {
      emit('save', 'Task.AutoEssenceSpecifiedLocation', first)
    }
  },
  { immediate: true }
)
</script>

<style scoped>
.plan-mode-display {
  min-height: 40px;
  display: flex;
  align-items: center;
  color: var(--ant-color-text-secondary);
}
</style>
