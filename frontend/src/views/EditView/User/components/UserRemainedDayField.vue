<template>
  <a-form-item>
    <template #label>
      <FieldLabelWithHint
        :text="t('edit.daysLeft')"
        :hint="hint ?? t('edit.daysLeftAccount1')"
        variant="form"
      />
    </template>
    <a-input-number
      v-model:value="value"
      :disabled="disabled"
      :placeholder="placeholder"
      size="large"
      :min="-1"
      :max="9999"
      style="width: 100%"
      @blur="emit('save', value)"
    />
  </a-form-item>
</template>
<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
defineProps<{ hint?: string; placeholder?: string; disabled?: boolean }>()
const value = defineModel<number>({ required: true })
const emit = defineEmits<{ save: [value: number] }>()

const { t } = useI18n()
</script>
