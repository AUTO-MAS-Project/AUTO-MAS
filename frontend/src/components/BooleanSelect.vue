<template>
  <a-select :value="value ? 'on' : 'off'" @change="handleChange">
    <a-select-option value="on">{{ t('edit.yes') }}</a-select-option>
    <a-select-option value="off">{{ t('edit.no') }}</a-select-option>
  </a-select>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

defineProps<{ value: boolean }>()

const emit = defineEmits<{
  'update:value': [value: boolean]
  change: [value: boolean]
}>()

const { t } = useI18n()

// Update the Boolean model before callers save the selected value.
const handleChange = (value: unknown) => {
  if (value !== 'on' && value !== 'off') return
  const nextValue = value === 'on'
  emit('update:value', nextValue)
  emit('change', nextValue)
}
</script>
