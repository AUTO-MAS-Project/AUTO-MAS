<template>
  <a-form-item>
    <template #label>
      <FieldLabelWithHint :text="label" :hint="hint" variant="form" />
    </template>
    <div
      ref="containerRef"
      class="run-limit-stepper"
      :class="{ 'run-limit-stepper--editing': editing }"
    >
      <button
        type="button"
        class="stepper-btn"
        :disabled="currentNumeric <= minValue"
        :aria-label="t('core.edit.stepperDecrease')"
        @mousedown.prevent
        @click="stepBy(-stepValue)"
      >
        <MinusOutlined />
      </button>

      <div v-if="editing" class="stepper-input-wrap">
        <a-input-number
          v-model:value="draftValue"
          :min="minValue"
          :max="MAX_VALUE"
          :precision="0"
          :controls="false"
          :bordered="false"
          class="stepper-input"
          @change="handleInputChange"
          @blur="finishEditing"
          @press-enter="handleEnter"
        />
      </div>
      <button
        v-else
        type="button"
        class="stepper-display"
        :class="{ 'stepper-display--muted': isUnlimited }"
        @click="startEditing"
      >
        <template v-if="isUnlimited">{{ t('core.edit.stepperUnlimited') }}</template>
        <template v-else>
          <span class="stepper-num">{{ currentNumeric }}</span>
          <span class="stepper-unit">{{ unitLabel }}</span>
        </template>
      </button>

      <button
        type="button"
        class="stepper-btn"
        :disabled="currentNumeric >= MAX_VALUE"
        :aria-label="t('core.edit.stepperIncrease')"
        @mousedown.prevent
        @click="stepBy(stepValue)"
      >
        <PlusOutlined />
      </button>
    </div>
  </a-form-item>
</template>

<script setup lang="ts" generic="T extends number | null | undefined">
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { MinusOutlined, PlusOutlined } from '@ant-design/icons-vue'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'

const MAX_VALUE = 9999

const props = defineProps<{
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

const { t } = useI18n()
const editing = ref(false)
const containerRef = ref<HTMLElement | null>(null)

const minValue = computed(() => (props.kind === 'daily' ? 0 : 1))
const stepValue = computed(() => (props.kind === 'timeout' ? 5 : 1))

function clampNumber(raw: unknown): number {
  const parsed =
    typeof raw === 'number' ? raw : typeof raw === 'string' && raw.trim() !== '' ? Number(raw) : NaN
  const numeric = Number.isFinite(parsed) ? Math.trunc(parsed) : minValue.value
  return Math.min(MAX_VALUE, Math.max(minValue.value, numeric))
}

const currentNumeric = computed(() => clampNumber(value.value))
const draftValue = ref<number | string | null>(currentNumeric.value)
let lastEmittedChange: number | string | null = currentNumeric.value

watch(
  () => value.value,
  next => {
    if (!editing.value) {
      const normalized = clampNumber(next)
      draftValue.value = normalized
      lastEmittedChange = normalized
    }
  }
)

const isUnlimited = computed(() => props.kind === 'daily' && currentNumeric.value === 0)
const unitLabel = computed(() => {
  if (props.kind === 'daily') return t('core.edit.stepperUnitDaily')
  if (props.kind === 'retry') return t('core.edit.stepperUnitRetry')
  return t('core.edit.stepperUnitTimeout')
})

async function startEditing() {
  draftValue.value = currentNumeric.value
  lastEmittedChange = currentNumeric.value
  editing.value = true
  await nextTick()
  const input = containerRef.value?.querySelector('input')
  input?.focus()
  input?.select()
}

function handleInputChange(next: number | string | null) {
  draftValue.value = next
  if (typeof next === 'number' && Number.isFinite(next)) {
    const clamped = clampNumber(next) as T
    value.value = clamped
    if (clamped !== lastEmittedChange) {
      lastEmittedChange = clamped as number
      emit('change', clamped as number)
    }
  }
}

function commitNormalized(next: number, { emitChangeIfChanged = true } = {}) {
  const clamped = clampNumber(next) as T
  draftValue.value = clamped as number
  value.value = clamped
  if (emitChangeIfChanged && clamped !== lastEmittedChange) {
    lastEmittedChange = clamped as number
    emit('change', clamped as number)
  }
  emit('save', clamped)
}

function stepBy(delta: number) {
  const base = editing.value ? clampNumber(draftValue.value) : currentNumeric.value
  commitNormalized(base + delta)
}

async function finishEditing() {
  // 等待 AntD InputNumber 在 blur 期间同步完修正后的 v-model 值，避免提交旧值。
  await nextTick()
  const rawInput = containerRef.value?.querySelector('input')?.value
  const candidate =
    draftValue.value !== null && draftValue.value !== ''
      ? clampNumber(draftValue.value)
      : rawInput !== undefined && rawInput.trim() !== ''
        ? clampNumber(rawInput)
        : minValue.value
  editing.value = false
  commitNormalized(candidate)
}

function handleEnter() {
  const input = containerRef.value?.querySelector('input')
  input?.blur()
}
</script>

<style scoped>
.run-limit-stepper {
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

.run-limit-stepper:hover {
  border-color: var(--ant-color-primary-hover);
}

.run-limit-stepper--editing,
.run-limit-stepper:focus-within {
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
  font-size: 13px;
  cursor: pointer;
  transition:
    background-color 0.15s ease,
    color 0.15s ease;
}

.stepper-btn:hover:not(:disabled) {
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

.stepper-display {
  flex: 1;
  min-width: 0;
  height: 100%;
  display: inline-flex;
  align-items: baseline;
  justify-content: center;
  gap: 4px;
  padding: 0 10px;
  border: 0;
  background: transparent;
  color: var(--ant-color-text);
  cursor: text;
  font-variant-numeric: tabular-nums;
}

.stepper-display--muted {
  align-items: center;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
  font-weight: 500;
}

.stepper-num {
  font-size: 15px;
  font-weight: 600;
  line-height: 34px;
  color: var(--ant-color-text);
}

.stepper-unit {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.stepper-input-wrap {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
}

.stepper-input {
  width: 100%;
  box-shadow: none !important;
}

.stepper-input :deep(.ant-input-number-input) {
  height: 34px;
  text-align: center;
  font-size: 15px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
</style>
