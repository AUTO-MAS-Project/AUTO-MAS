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
          <a-switch
            v-if="field.type === 'bool'"
            :checked="values[field.name] === true"
            :disabled="disabled || field.disabled"
            @change="(value: unknown) => emit('change', field.name, value)"
          />
          <a-checkbox-group
            v-else-if="field.type === 'multi_selection'"
            class="native-checkboxes"
            :value="values[field.name] as string[]"
            :disabled="disabled || field.disabled"
            :options="(field.options ?? []).map(value => ({ value, label: optionLabel(value) }))"
            @change="(value: unknown) => emit('change', field.name, value)"
          />
          <a-select
            v-else-if="field.type === 'select'"
            :value="values[field.name] as string | string[]"
            :disabled="disabled || field.disabled"
            style="width: 100%"
            :options="
              (field.options ?? []).map(value => ({
                value,
                label: optionLabel(value),
              }))
            "
            @change="(value: unknown) => emit('change', field.name, value)"
          />
          <a-input-number
            v-else-if="field.type === 'number'"
            :value="Number(values[field.name])"
            :min="field.minimum ?? undefined"
            :max="field.maximum ?? undefined"
            :precision="field.integer ? 0 : undefined"
            :disabled="disabled || field.disabled"
            style="width: 100%"
            @change="
              (value: number | string | null) => {
                if (value !== null) emit('change', field.name, Number(value))
              }
            "
          />
          <a-input
            v-else-if="field.type === 'string'"
            :value="String(values[field.name] ?? '')"
            :disabled="disabled || field.disabled"
            @blur="
              (event: FocusEvent) =>
                emit('change', field.name, (event.target as HTMLInputElement).value)
            "
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
function optionLabel(value: string) {
  return props.labels[value] || t(`${props.optionPrefix}${value}`, value)
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
.native-checkboxes {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
}
.native-checkboxes :deep(.ant-checkbox-wrapper) {
  margin-inline-start: 0;
  max-width: 100%;
  white-space: normal;
}
.native-config-field {
  min-width: 0;
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
