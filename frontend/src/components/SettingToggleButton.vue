<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const props = withDefaults(
  defineProps<{
    modelValue?: boolean
    disabled?: boolean
    loading?: boolean
    size?: 'small' | 'middle' | 'large'
  }>(),
  { modelValue: false, disabled: false, loading: false, size: 'large' }
)

const emit = defineEmits<{ 'update:modelValue': [value: boolean]; change: [value: boolean] }>()
const { t } = useI18n()
const label = computed(() => t(props.modelValue ? 'comp.enabled' : 'comp.disabled'))
const toggle = () => {
  if (props.disabled || props.loading) return
  const value = !props.modelValue
  emit('update:modelValue', value)
  emit('change', value)
}
</script>

<template>
  <a-button
    class="setting-toggle-button"
    :class="{ 'setting-toggle-button--on': modelValue }"
    :disabled="disabled"
    :loading="loading"
    :size="size"
    :aria-pressed="modelValue"
    @click="toggle"
  >
    {{ label }}
  </a-button>
</template>

<style scoped>
.setting-toggle-button {
  min-width: 60px;
  border-radius: 6px;
  border-color: var(--ant-color-error);
  color: var(--ant-color-error);
  background: var(--ant-color-bg-container);
  font-weight: 600;
}

.setting-toggle-button.ant-btn-lg {
  min-width: 88px;
}

.setting-toggle-button.ant-btn:not(.setting-toggle-button--on):not(:disabled):is(
    :hover,
    :focus-visible
  ) {
  border-color: var(--ant-color-error);
  color: var(--ant-color-error);
}

.setting-toggle-button--on {
  border-color: var(--ant-color-primary);
  color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
}

.setting-toggle-button.ant-btn:not(.setting-toggle-button--on):disabled {
  border-color: var(--ant-color-error);
  color: var(--ant-color-error);
  background: var(--ant-color-bg-container);
}

.setting-toggle-button.ant-btn.setting-toggle-button--on:is(:hover, :focus-visible, :disabled) {
  border-color: var(--ant-color-primary);
  color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
}

.setting-toggle-button:disabled {
  opacity: 0.6;
}
</style>
