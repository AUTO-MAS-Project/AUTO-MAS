<template>
  <a-form-item>
    <template #label>
      <FieldLabelWithHint :text="label" :hint="hint" variant="form" />
    </template>
    <a-input-number
      v-model:value="value"
      :min="kind === 'daily' ? 0 : 1"
      :max="9999"
      size="large"
      :class="{ 'modern-number-input': enhanced }"
      style="width: 100%"
      @blur="emit('save', value)"
      @change="emit('change', $event)"
    />
  </a-form-item>
</template>

<script setup lang="ts" generic="T extends number | null | undefined">
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'

defineProps<{
  kind: 'daily' | 'retry' | 'timeout'
  label: string
  hint: string
  enhanced?: boolean
}>()

const value = defineModel<T>({ required: true })
const emit = defineEmits<{
  save: [value: T]
  change: [value: number | string | null]
}>()
</script>

<style scoped>
.modern-number-input {
  border-radius: 8px;
}

.modern-number-input :deep(.ant-input-number) {
  border: 2px solid var(--ant-color-border);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
  transition: all 0.3s ease;
}

.modern-number-input :deep(.ant-input-number:hover) {
  border-color: var(--ant-color-primary-hover);
}

.modern-number-input :deep(.ant-input-number-focused) {
  border-color: var(--ant-color-primary);
  box-shadow: 0 0 0 4px rgba(24, 144, 255, 0.1);
}

html.dark .modern-number-input :deep(.ant-input-number-focused) {
  box-shadow: 0 0 0 4px rgba(24, 144, 255, 0.2);
}
</style>
