<template>
  <a-form-item>
    <template #label>
      <FieldLabelWithHint
        :text="t('edit.note')"
        :hint="hint ?? t('edit.addNoteAboutThis')"
        variant="form"
      />
    </template>
    <a-textarea
      v-model:value="value"
      :disabled="disabled"
      :placeholder="placeholder"
      :class="{ 'modern-input': enhanced }"
      :rows="rows"
      @blur="emit('save', value)"
    />
  </a-form-item>
</template>
<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
defineProps<{
  hint?: string
  placeholder?: string
  disabled?: boolean
  enhanced?: boolean
  rows?: number
}>()
const value = defineModel<string>({ required: true })
const emit = defineEmits<{ save: [value: string] }>()

const { t } = useI18n()
</script>

<style scoped src="./userInfoFields.css"></style>
