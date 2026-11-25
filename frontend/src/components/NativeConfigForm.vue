<template>
  <div class="native-config-shell">
    <div class="native-config-fields">
      <div
        v-for="field in visibleFields"
        :key="field.name"
        class="native-config-field"
        :class="{ 'native-config-field--multiple': field.type === 'multi_selection' }"
      >
        <a-form-item
          :label="label(field.name)"
          :validate-status="errors[field.name] ? 'error' : undefined"
          :help="errors[field.name]"
          :extra="
            hints[field.name] ?? (field.disabled ? t('core.edit.okwwPlanManaged') : undefined)
          "
        >
          <DeclarativeControl
            v-if="field.type === 'bool' || field.type === 'select'"
            compact
            :component="field.type === 'bool' ? 'switch' : field.type"
            :label="label(field.name)"
            :model-value="field.type === 'bool' ? values[field.name] === true : values[field.name]"
            :disabled="disabled || field.disabled"
            :options="optionsFor(field)"
            @update:model-value="emit('change', field.name, $event)"
          />
          <NativeConfigCheckboxes
            v-else-if="field.type === 'multi_selection'"
            :value="values[field.name] as string[]"
            :disabled="disabled || field.disabled"
            :options="optionsFor(field)"
            @change="(value: unknown) => emit('change', field.name, value)"
          />
          <DeclarativeControl
            v-else-if="field.type === 'number'"
            component="number"
            compact
            :model-value="Number(values[field.name])"
            :min="field.minimum"
            :max="field.maximum"
            :precision="field.integer ? 0 : undefined"
            :disabled="disabled || field.disabled"
            @update:model-value="$event !== null && emit('change', field.name, Number($event))"
          />
          <DeclarativeControl
            v-else-if="field.type === 'string'"
            component="input"
            compact
            :model-value="drafts[field.name] ?? String(values[field.name] ?? '')"
            :disabled="disabled || field.disabled"
            @update:model-value="drafts[field.name] = $event as string"
            @blur="saveString(field.name)"
          />
          <a-textarea
            v-else
            :value="drafts[field.name] ?? JSON.stringify(values[field.name], null, 2)"
            :disabled="disabled || field.disabled"
            :auto-size="{ minRows: 2, maxRows: 8 }"
            @change="
              (event: Event) => (drafts[field.name] = (event.target as HTMLTextAreaElement).value)
            "
            @blur="saveJson(field.name)"
          />
        </a-form-item>
      </div>
    </div>
  </div>
</template>
<script setup lang="ts">
import { computed, reactive } from 'vue'
import { useI18n } from 'vue-i18n'
import { DeclarativeControl } from '@/components/declarative'
import NativeConfigCheckboxes from './NativeConfigCheckboxes.vue'
import type { NativeConfigField } from '@/types/nativeConfig'
const props = withDefaults(
  defineProps<{
    hints?: Record<string, string>
    labels: Record<string, string>
    fields: NativeConfigField[]
    values: Record<string, unknown>
    disabled: boolean
    labelPrefix: string
    optionPrefix: string
  }>(),
  { hints: () => ({}) }
)
const emit = defineEmits<{ change: [name: string, value: unknown] }>()
const { t } = useI18n()
const drafts = reactive<Record<string, string>>({})
const errors = reactive<Record<string, string>>({})
const visibleFields = computed(() =>
  props.fields.filter(
    field => !field.parent || field.choices?.includes(String(props.values[field.parent]))
  )
)
function label(name: string) {
  return props.labels[name] || t(`${props.labelPrefix}${name}`, name)
}
function optionsFor(field: NativeConfigField) {
  return (field.options ?? []).map(value => ({
    value,
    label: props.labels[value] || t(`${props.optionPrefix}${value}`, value),
  }))
}
function saveString(name: string) {
  if (!(name in drafts)) return
  const value = drafts[name]!
  delete drafts[name]
  emit('change', name, value)
}
function saveJson(name: string) {
  if (!(name in drafts)) return
  try {
    const value: unknown = JSON.parse(drafts[name]!)
    errors[name] = ''
    delete drafts[name]
    emit('change', name, value)
  } catch {
    errors[name] = t('core.plan.oknte.invalidJson')
  }
}
</script>

<style scoped>
.native-config-shell {
  width: 100%;
  min-width: 0;
  container-type: inline-size;
  container-name: native-config;
}
.native-config-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  column-gap: 24px;
}
.native-config-field--multiple {
  grid-column: 1 / -1;
}
.native-config-field {
  min-width: 0;
}
.native-config-field :deep(.declarative-control--compact > .ant-input-number) {
  width: 100%;
}
.native-config-fields :deep(.ant-form-item-label) {
  white-space: normal;
}
.native-config-fields :deep(.ant-form-item-label > label) {
  height: auto;
}
@container native-config (max-width: 640px) {
  .native-config-fields {
    grid-template-columns: minmax(0, 1fr);
  }
}
@media (max-width: 768px) {
  .native-config-fields {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
