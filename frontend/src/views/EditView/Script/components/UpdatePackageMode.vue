<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useId } from 'vue'

const { disabled = false } = defineProps<{ disabled?: boolean }>()
const mode = defineModel<'full' | 'incremental'>({ required: true })
const emit = defineEmits<{ change: [value: 'full' | 'incremental'] }>()
const { t } = useI18n()
const selectId = useId()
</script>

<template>
  <a-form-item :label="t('core.edit.updatePackageMode')" :html-for="selectId">
    <a-select
      :id="selectId"
      v-model:value="mode"
      size="large"
      :aria-label="t('core.edit.updatePackageMode')"
      :disabled="disabled"
      :options="[
        { label: t('core.edit.updatePackageFull'), value: 'full' },
        { label: t('core.edit.updatePackageIncremental'), value: 'incremental' },
      ]"
      @change="(value: 'full' | 'incremental') => emit('change', value)"
    />
    <a-typography-text v-if="mode === 'incremental'" type="warning">
      {{ t('core.edit.updatePackageRisk') }}
    </a-typography-text>
  </a-form-item>
</template>
