<template>
  <section
    ref="editorElement"
    class="baah-editor"
    role="dialog"
    :aria-label="title"
    @keydown.esc.stop="$emit('escape')"
  >
    <div class="baah-editor-title">{{ title }}</div>
    <a-form layout="vertical" class="baah-editor-form">
      <a-form-item :label="t('core.plan.baah.rowState')">
        <a-radio-group
          :value="state"
          :disabled="saving"
          @update:value="$emit('update:state', $event)"
        >
          <a-radio-button v-for="option in stateOptions" :key="option.value" :value="option.value">
            {{ option.label }}
          </a-radio-button>
        </a-radio-group>
      </a-form-item>
      <template v-if="state === 'on'">
        <a-form-item
          v-for="(part, index) in spec.parts"
          :key="part.hintKey"
          :label="t(part.hintKey)"
        >
          <a-select
            :value="values[index]"
            :options="partOptions(part.hintKey, part.min, values[index])"
            :aria-label="t(part.hintKey)"
            :disabled="saving"
            @update:value="updatePart(index, $event)"
          />
        </a-form-item>
      </template>
      <p v-else class="baah-editor-hint">
        {{ t(state === 'off' ? 'core.plan.baah.skipToday' : 'core.plan.baah.upstreamSettings') }}
      </p>
      <a-alert
        v-if="saveError"
        type="error"
        show-icon
        :message="t('core.plan.baah.saveFailed')"
        :description="saveErrorReason || undefined"
      >
        <template #action>
          <a-button size="small" :loading="saving" @click="$emit('retry')">{{
            t('core.plan.baah.retry')
          }}</a-button>
        </template>
      </a-alert>
    </a-form>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  BAAH_KEY_FIELD_BY_NAME,
  partOptionMax,
  type BAAHFieldState,
  type BAAHKeyFieldName,
} from '@/utils/baahPlanKey'
import { baahRegionLabel } from './baahPlanDisplay'

const { t } = useI18n()
const props = defineProps<{
  field: BAAHKeyFieldName
  dayTitle: string
  state: BAAHFieldState
  values: number[]
  saving: boolean
  saveError: boolean
  saveErrorReason: string
}>()
const emit = defineEmits<{
  'update:state': [value: BAAHFieldState]
  'update:values': [value: number[]]
  retry: []
  escape: []
}>()
const editorElement = ref<HTMLElement | null>(null)
const spec = computed(() => BAAH_KEY_FIELD_BY_NAME[props.field])
const title = computed(() => `${t(spec.value.labelKey)} · ${props.dayTitle}`)
const stateOptions = computed(() => [
  { value: 'on', label: t('core.plan.baah.stateOn') },
  { value: 'off', label: t('core.plan.baah.stateOff') },
  { value: 'auto', label: t('core.plan.baah.stateAuto') },
])

const partOptions = (hintKey: string, min: number, current: number) => {
  const options = Array.from({ length: partOptionMax(hintKey, props.field) }, (_, index) => ({
    value: index + 1,
    label:
      hintKey === 'core.plan.baah.partRegion' ? baahRegionLabel(index + 1, t) : String(index + 1),
  }))
  if (min === -1)
    options.unshift({
      value: -1,
      label: t(
        hintKey === 'core.plan.baah.partTimes'
          ? 'core.plan.baah.timesMax'
          : 'core.plan.baah.stageHighest'
      ),
    })
  if (hintKey === 'core.plan.baah.partTimes')
    options.splice(1, 0, { value: 0, label: t('core.plan.baah.timesNumber', { value: 0 }) })
  // 已存的合法大数照样能看见、保存，预设下拉范围不能截断旧配置。
  if (
    hintKey !== 'core.plan.baah.partRegion' &&
    hintKey !== 'core.plan.baah.partAcademy' &&
    !options.some(option => option.value === current)
  )
    options.push({
      value: current,
      label:
        hintKey === 'core.plan.baah.partRegion' ? baahRegionLabel(current, t) : String(current),
    })
  return options
}
const updatePart = (index: number, value: number) => {
  const values = [...props.values]
  values[index] = value
  emit('update:values', values)
}
onMounted(async () => {
  await nextTick()
  editorElement.value?.querySelector<HTMLInputElement>('input[type="radio"]:checked')?.focus()
})
</script>

<style scoped>
.baah-editor {
  display: flex;
  flex-direction: column;
  width: min(320px, calc(100vw - 48px));
  max-height: calc(100dvh - 80px);
  color: var(--ant-color-text);
}
.baah-editor-title {
  margin-bottom: 14px;
  font-weight: 600;
}
.baah-editor-form {
  min-height: 0;
  overflow-y: auto;
}
.baah-editor-form :deep(.ant-form-item) {
  margin-bottom: 14px;
}
.baah-editor-hint {
  color: var(--ant-color-text-secondary);
}
</style>
