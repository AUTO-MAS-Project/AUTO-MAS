<script setup lang="ts">
import { useI18n } from 'vue-i18n'

defineProps<{ modelValue: string[]; disabled?: boolean }>()
const emit = defineEmits<{
  'update:modelValue': [value: string[]]
  change: [value: string[]]
}>()
const { t } = useI18n()

function change(value: unknown) {
  const days = value as string[]
  emit('update:modelValue', days)
  emit('change', days)
}
</script>

<template>
  <a-select
    :value="modelValue"
    mode="multiple"
    size="small"
    style="width: 100%"
    :placeholder="t('core.queue.time.selectDays')"
    :aria-label="t('core.queue.time.colDays')"
    :disabled="disabled"
    :max-tag-count="7"
    :bordered="false"
    class="days-select"
    @change="change"
  >
    <a-select-option value="Monday">{{ t('core.queue.time.Monday') }}</a-select-option>
    <a-select-option value="Tuesday">{{ t('core.queue.time.Tuesday') }}</a-select-option>
    <a-select-option value="Wednesday">{{ t('core.queue.time.Wednesday') }}</a-select-option>
    <a-select-option value="Thursday">{{ t('core.queue.time.Thursday') }}</a-select-option>
    <a-select-option value="Friday">{{ t('core.queue.time.Friday') }}</a-select-option>
    <a-select-option value="Saturday">{{ t('core.queue.time.Saturday') }}</a-select-option>
    <a-select-option value="Sunday">{{ t('core.queue.time.Sunday') }}</a-select-option>
  </a-select>
</template>

<style scoped>
/* 沿用 dev 定时列表的星期标签样式，由选择器自身持有，避免跨组件作用域失效。 */
.days-select :deep(.ant-select-selection-item) {
  background: transparent !important;
  border: none !important;
  padding-right: 4px !important;
}

.days-select :deep(.ant-select-selection-item-remove) {
  display: none !important;
}
</style>
