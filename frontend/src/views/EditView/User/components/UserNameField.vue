<template>
  <a-form-item>
    <template #label>
      <FieldLabelWithHint
        :text="t('core.edit.username')"
        :hint="hint ?? t('core.edit.nameUsedTellUsers')"
        variant="form"
      />
    </template>
    <a-input
      v-model:value="value"
      :disabled="disabled"
      :placeholder="placeholder"
      size="large"
      :class="{ 'modern-input': enhanced }"
      @blur="emit('save', value)"
    />
  </a-form-item>
</template>
<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
defineProps<{ hint?: string; placeholder?: string; disabled?: boolean; enhanced?: boolean }>()
const value = defineModel<string>({ required: true })
const emit = defineEmits<{ save: [value: string] }>()

const { t } = useI18n()
</script>

<style scoped src="./userInfoFields.css"></style>
