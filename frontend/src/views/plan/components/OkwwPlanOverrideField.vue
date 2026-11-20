<template>
  <OkwwPlanOverrideItem
    :title="label(field.name)"
    :overridden="overridden"
    :disabled="disabled"
    :hide-toggle="grouped"
    @toggle="overridden ? emit('inherit') : emit('set', defaultValue)"
  >
    <a-switch
      v-if="field.type === 'bool'"
      :checked="value === true"
      :disabled="disabled"
      @change="(value: unknown) => emit('set', value)"
    />
    <a-input-number
      v-else-if="field.type === 'number'"
      :value="Number(value)"
      :min="field.minimum ?? undefined"
      :max="field.maximum ?? undefined"
      :precision="field.integer ? 0 : undefined"
      :disabled="disabled"
      class="override-input"
      @change="(value: number | string | null) => value !== null && emit('set', Number(value))"
    />
    <NativeConfigCheckboxes
      v-else-if="field.type === 'multi_selection'"
      :value="value as string[]"
      :options="(field.options ?? []).map(value => ({ value, label: optionLabel(value) }))"
      :disabled="disabled"
      @change="emit('set', $event)"
    />
    <a-select
      v-else-if="field.type === 'select'"
      :value="value as string"
      :options="field.options?.map(value => ({ value, label: optionLabel(value) }))"
      :disabled="disabled"
      class="override-input"
      @change="(value: unknown) => emit('set', value)"
    />
    <a-input
      v-else-if="field.type === 'string'"
      :value="String(value ?? '')"
      :disabled="disabled"
      @blur="(event: FocusEvent) => emit('set', (event.target as HTMLInputElement).value)"
    />
    <template v-else>
      <a-textarea
        v-model:value="jsonDraft"
        :disabled="disabled"
        :auto-size="{ minRows: 2, maxRows: 8 }"
        @blur="saveJson"
      />
      <span v-if="jsonError" role="alert">{{ t('core.plan.oknte.invalidJson') }}</span>
    </template>
  </OkwwPlanOverrideItem>
</template>
<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { OkwwConfigField } from '@/api'
import NativeConfigCheckboxes from '@/components/NativeConfigCheckboxes.vue'
import OkwwPlanOverrideItem from './OkwwPlanOverrideItem.vue'
const props = defineProps<{
  field: OkwwConfigField
  grouped?: boolean
  labels: Record<string, string>
  defaultValue: unknown
  value: unknown
  overridden: boolean
  disabled: boolean
}>()
const emit = defineEmits<{ set: [value: unknown]; inherit: [] }>()
const { t } = useI18n()
const jsonDraft = ref('')
const jsonError = ref(false)
watch(
  () => props.value,
  value => {
    jsonDraft.value = JSON.stringify(value, null, 2) ?? ''
    jsonError.value = false
  },
  { immediate: true }
)
function label(name: string) {
  return props.labels[name] || t(`core.edit.okwwEcho.${name}`, name)
}
function optionLabel(value: string) {
  return props.labels[value] || t(`core.edit.okwwEchoOption.${value}`, value)
}
function saveJson() {
  try {
    const value: unknown = JSON.parse(jsonDraft.value)
    jsonError.value = false
    emit('set', value)
  } catch {
    jsonError.value = true
  }
}
</script>
<style scoped>
.override-input {
  width: 100%;
}
</style>
