<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { MinusOutlined, PlusOutlined } from '@ant-design/icons-vue'

const props = withDefaults(
  defineProps<{
    modelValue: number | null | undefined
    min?: number
    max?: number
    step?: number
    precision?: number
    unit?: string
    zeroLabel?: string
    disabled?: boolean
    ariaLabel?: string
  }>(),
  {
    min: undefined,
    max: undefined,
    step: 1,
    precision: undefined,
    unit: undefined,
    zeroLabel: undefined,
    ariaLabel: undefined,
  }
)

const emit = defineEmits<{
  'update:modelValue': [value: number | null]
  change: [value: number | null]
  blur: []
}>()
const { t } = useI18n()
const focused = ref(false)
const showZeroLabel = computed(
  () => Boolean(props.zeroLabel) && props.modelValue === 0 && !focused.value
)

function update(value: number | null) {
  emit('update:modelValue', value)
  emit('change', value)
}

function decimalPlaces(value: number) {
  const [coefficient = '', exponent = '0'] = String(value).split('e')
  return Math.max(0, (coefficient.split('.')[1]?.length ?? 0) - Number(exponent))
}

function stepBy(direction: -1 | 1) {
  const base = props.modelValue ?? 0
  const next = base + direction * props.step
  const precision = props.precision ?? Math.max(decimalPlaces(base), decimalPlaces(props.step))
  const rounded = precision <= 100 ? Number(next.toFixed(precision)) : next
  const bounded = Math.min(props.max ?? Infinity, Math.max(props.min ?? -Infinity, rounded))
  if (bounded !== props.modelValue) update(bounded)
}

function blur() {
  focused.value = false
  emit('blur')
}
</script>

<template>
  <div class="number-stepper" :class="{ 'number-stepper--disabled': disabled }">
    <button
      type="button"
      class="stepper-btn"
      :disabled="disabled || (modelValue != null && min != null && modelValue <= min)"
      :aria-label="t('core.edit.stepperDecrease')"
      @mousedown.prevent
      @click="stepBy(-1)"
    >
      <MinusOutlined aria-hidden="true" />
    </button>
    <div
      class="stepper-center"
      :class="{ 'with-unit': unit && !showZeroLabel, 'with-zero-label': showZeroLabel }"
    >
      <a-input-number
        class="stepper-input"
        size="large"
        :value="modelValue"
        :controls="false"
        :bordered="false"
        :disabled="disabled"
        :min="min"
        :max="max"
        :step="step"
        :precision="precision"
        :aria-label="ariaLabel"
        :aria-valuetext="
          showZeroLabel
            ? zeroLabel
            : unit && modelValue != null
              ? `${modelValue} ${unit}`
              : undefined
        "
        @update:value="update"
        @focus="focused = true"
        @blur="blur"
      />
      <span v-if="showZeroLabel" class="stepper-zero-label" aria-hidden="true">{{
        zeroLabel
      }}</span>
      <span v-else-if="unit" class="stepper-unit" aria-hidden="true">{{ unit }}</span>
    </div>
    <button
      type="button"
      class="stepper-btn"
      :disabled="disabled || (modelValue != null && max != null && modelValue >= max)"
      :aria-label="t('core.edit.stepperIncrease')"
      @mousedown.prevent
      @click="stepBy(1)"
    >
      <PlusOutlined aria-hidden="true" />
    </button>
  </div>
</template>

<style scoped>
.number-stepper {
  display: inline-flex;
  align-items: center;
  width: 100%;
  max-width: 220px;
  height: 36px;
  border: 1px solid var(--ant-color-border);
  border-radius: var(--ant-border-radius);
  background: var(--ant-color-bg-container);
  overflow: hidden;
  transition:
    border-color 0.15s ease,
    box-shadow 0.15s ease;
}

.number-stepper:hover:not(.number-stepper--disabled) {
  border-color: var(--ant-color-primary-hover);
}

.number-stepper:focus-within {
  border-color: var(--ant-color-primary);
  box-shadow: 0 0 0 2px var(--ant-color-primary-bg);
}

.stepper-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 36px;
  height: 100%;
  padding: 0;
  border: 0;
  background: var(--ant-color-fill-quaternary);
  color: var(--ant-color-text);
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.stepper-btn:hover:not(:disabled),
.stepper-btn:focus-visible {
  background: var(--ant-color-fill-secondary);
}

.stepper-btn:disabled {
  color: var(--ant-color-text-quaternary);
  cursor: not-allowed;
}

.stepper-btn:first-child {
  border-right: 1px solid var(--ant-color-border-secondary);
}

.stepper-btn:last-child {
  border-left: 1px solid var(--ant-color-border-secondary);
}

.stepper-center {
  position: relative;
  display: grid;
  align-items: center;
  grid-template-columns: minmax(0, 1fr);
  flex: 1;
  min-width: 0;
}

.stepper-center.with-unit {
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 4px;
}

.stepper-input {
  width: 100%;
}

.stepper-input :deep(.ant-input-number-input) {
  height: 34px;
  padding-inline: 4px;
  text-align: center;
  font-size: 14px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.with-unit .stepper-input :deep(.ant-input-number-input) {
  padding-inline-end: 0;
  text-align: end;
}

.with-zero-label .stepper-input :deep(.ant-input-number-input) {
  color: transparent;
}

.stepper-zero-label {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  pointer-events: none;
  font-weight: 500;
}

.stepper-zero-label,
.stepper-unit {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  white-space: nowrap;
}

.stepper-unit {
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
