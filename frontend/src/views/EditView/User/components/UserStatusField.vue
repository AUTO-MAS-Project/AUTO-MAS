<template>
  <a-form-item>
    <template #label>
      <FieldLabelWithHint
        :text="t('edit.enabled')"
        :hint="hint ?? t('edit.whetherThisUserEnabled')"
        variant="form"
      />
    </template>
    <a-select
      v-model:value="value"
      :disabled="disabled"
      :placeholder="placeholder"
      size="large"
      style="width: 100%"
      @change="emit('save', $event)"
      ><a-select-option :value="true">{{ t('edit.yes') }}</a-select-option
      ><a-select-option :value="false">{{ t('edit.no') }}</a-select-option></a-select
    >
  </a-form-item>
</template>
<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
defineProps<{ hint?: string; placeholder?: string; disabled?: boolean }>()
const value = defineModel<boolean>({ required: true })
const emit = defineEmits<{ save: [value: boolean] }>()

const { t } = useI18n()
</script>
