<template>
  <a-form-item class="override-field" :class="{ 'override-field--inherited': !overridden }">
    <template #label>
      <a-space
        ><span>{{ field.label || field.name }}</span
        ><a-button
          :type="overridden ? 'primary' : 'default'"
          size="small"
          :aria-label="t(overridden ? 'core.plan.oknte.overridden' : 'core.plan.oknte.inherit')"
          :aria-pressed="overridden"
          :disabled="disabled"
          @click="toggleOverride"
          >{{ t(overridden ? 'core.plan.oknte.overridden' : 'core.plan.oknte.inherit') }}</a-button
        ></a-space
      >
    </template>
    <template v-if="overridden">
      <a-switch
        v-if="field.type === 'bool'"
        :checked="value === true"
        :disabled="disabled"
        :checked-children="t('core.plan.oknte.on')"
        :un-checked-children="t('core.plan.oknte.off')"
        @change="(value: unknown) => emit('set', value)"
      />
      <a-input-number
        v-else-if="field.type === 'int' || field.type === 'float'"
        class="override-input"
        :value="typeof value === 'number' ? value : undefined"
        :min="field.min ?? undefined"
        :max="field.max ?? undefined"
        :step="field.step ?? 1"
        :disabled="disabled"
        @change="(value: number | null) => value !== null && emit('set', value)"
      />
      <a-select
        v-else-if="field.type === 'select' || (field.type === 'list' && field.options?.length)"
        class="override-input"
        :mode="field.type === 'list' ? 'multiple' : undefined"
        :value="selectValue"
        :options="(field.options ?? []).map(value => ({ value, label: value }))"
        :disabled="disabled"
        @change="(value: unknown) => emit('set', value)"
      />
      <template v-else-if="field.type === 'object' || field.type === 'list'">
        <a-textarea
          v-model:value="jsonDraft"
          :disabled="disabled"
          :auto-size="{ minRows: 2, maxRows: 8 }"
          @blur="saveJson"
        />
        <span v-if="jsonError" role="alert">{{ t('core.plan.oknte.invalidJson') }}</span>
      </template>
      <a-input
        v-else
        :value="String(value ?? '')"
        :disabled="disabled"
        @change="(event: Event) => emit('set', (event.target as HTMLInputElement).value)"
      />
    </template>
  </a-form-item>
</template>
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { OverrideField } from '../oknteOverrideTypes'
const props = defineProps<{
  field: OverrideField
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
function toggleOverride() {
  if (props.overridden) emit('inherit')
  else emit('set', props.field.value)
}
function saveJson() {
  try {
    const parsed: unknown = JSON.parse(jsonDraft.value)
    if (
      props.field.type === 'list'
        ? !Array.isArray(parsed)
        : parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)
    )
      throw new Error('shape')
    jsonError.value = false
    emit('set', parsed)
  } catch {
    jsonError.value = true
  }
}
const selectValue = computed(() =>
  Array.isArray(props.value)
    ? props.value.filter((value): value is string => typeof value === 'string')
    : typeof props.value === 'string'
      ? props.value
      : undefined
)
</script>
<style scoped>
.override-input {
  width: 100%;
}
.override-field {
  margin-bottom: 16px;
}
.override-field:last-child {
  margin-bottom: 0;
}
.override-field--inherited :deep(.ant-form-item-control) {
  display: none;
}
.override-field--inherited :deep(.ant-form-item-label) {
  padding-bottom: 0;
}
</style>
