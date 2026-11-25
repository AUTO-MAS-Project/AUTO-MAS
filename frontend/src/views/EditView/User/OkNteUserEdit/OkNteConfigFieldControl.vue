<template>
  <!-- list 类型：多选 -->
  <a-select
    v-if="field.type === 'list'"
    :value="modelValue"
    mode="multiple"
    style="width: 100%"
    :placeholder="t('core.edit.pleaseChoose')"
    :options="options"
    :disabled="disabled"
    @change="emit('change', $event)"
  />
  <DeclarativeControl
    v-else
    class="oknte-field-control"
    compact
    :component="component"
    :label="field.label || field.name"
    :model-value="modelValue"
    :disabled="disabled"
    :options="options"
    :min="field.min"
    :max="field.max"
    :precision="field.type === 'int' ? 0 : undefined"
    :step="field.type === 'float' ? field.step || 0.1 : undefined"
    @update:model-value="change"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import DeclarativeControl from '@/components/declarative/DeclarativeControl.vue'

const props = defineProps<{
  field: {
    name: string
    label: string
    type: string
    options: string[] | null
    min: number | null
    max: number | null
    step: number | null
  }
  modelValue: unknown
  optionLabels: Record<string, string>
  disabled: boolean
}>()
const emit = defineEmits<{ change: [value: unknown] }>()
const { t } = useI18n()

const components: Record<string, string> = {
  bool: 'switch',
  select: 'select',
  int: 'number',
  float: 'number',
}
const component = computed(() => components[props.field.type] ?? 'input')
const options = computed(() =>
  (props.field.options ?? []).map(value => ({ value, label: props.optionLabels[value] || value }))
)

function change(value: unknown) {
  if (component.value === 'number' && value === null) return
  emit('change', value)
}
</script>

<style scoped>
.oknte-field-control.declarative-control--compact :deep(.ant-input-number) {
  width: 100%;
}
</style>
