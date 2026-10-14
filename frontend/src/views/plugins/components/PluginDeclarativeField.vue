<script setup lang="ts">
import SettingToggleButton from '@/components/SettingToggleButton.vue'
import { configurationFieldSpan } from '@/utils/declarativeLayout'

export type DeclarativeHint = {
  field?: string
  component?: string
  width?: number | null
  editable?: boolean
  secret?: boolean
  min?: number | null
  max?: number | null
  options?: Array<{ value?: string }>
  multiple?: boolean
}

const props = defineProps<{
  group: string
  hint: DeclarativeHint
  value: unknown
  loading?: boolean
}>()
const emit = defineEmits<{ 'update:value': [value: unknown]; action: [] }>()
const label = () => props.hint.field || ''
const component = () => (props.hint.component || 'input').toLowerCase()
const isBoolean = () =>
  ['switch', 'checkbox', 'bool', 'boolean', 'toggle-button'].includes(component())
const gridSpan = () => configurationFieldSpan(component(), props.hint.width)
</script>

<template>
  <div
    class="plugin-field form-grid-24__item form-item-vertical"
    :style="{ '--field-span': gridSpan() }"
  >
    <a-button
      v-if="component() === 'button' || component() === 'dropdown-button'"
      :disabled="props.hint.editable === false"
      :loading="loading"
      @click="emit('action')"
    >
      {{ label() }}
    </a-button>

    <template v-else>
      <label v-if="!isBoolean()" class="field-label">
        {{ label() }}
      </label>
      <a-input
        v-if="component() === 'input' || component() === 'path'"
        :value="value"
        :type="props.hint.secret ? 'password' : 'text'"
        :disabled="props.hint.editable === false"
        @update:value="emit('update:value', $event)"
      />
      <a-input-number
        v-else-if="component() === 'number'"
        :value="value as number | null | undefined"
        :min="props.hint.min ?? undefined"
        :max="props.hint.max ?? undefined"
        :disabled="props.hint.editable === false"
        style="width: 100%"
        @update:value="emit('update:value', $event)"
      />
      <a-select
        v-else-if="component() === 'select' || component() === 'ref-select'"
        :value="value"
        :options="
          (props.hint.options || []).map(option => ({ value: option.value, label: option.value }))
        "
        :mode="props.hint.multiple ? 'multiple' : undefined"
        :disabled="props.hint.editable === false"
        @update:value="emit('update:value', $event)"
      />
      <div v-else-if="isBoolean()" class="toggle-field">
        <label class="field-label">{{ label() }}</label>
        <SettingToggleButton
          :model-value="Boolean(value)"
          :disabled="props.hint.editable === false || loading"
          :loading="loading"
          @change="emit('update:value', $event)"
        />
      </div>
    </template>
  </div>
</template>

<style scoped>
.plugin-field {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.field-label {
  color: var(--ant-color-text-secondary);
}
.toggle-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.toggle-field :deep(.setting-toggle-button) {
  width: 100%;
}
.plugin-field :deep(.ant-select) {
  width: 100%;
}
</style>
