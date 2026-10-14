<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { ComponentHint } from '@/api'
import DeclarativeControl from '@/components/DeclarativeControl.vue'
import { configurationFieldSpan } from '@/utils/declarativeLayout'
import { apiErrorMessage } from '@/utils/apiResult'

export type DeclarativeHint = ComponentHint
const props = defineProps<{
  group: string
  namespace: string
  hint: DeclarativeHint
  value: unknown
  options: Array<{ value: string; label: string }>
  loading?: boolean
  disabled?: boolean
}>()
const emit = defineEmits<{ 'update:value': [value: unknown]; action: [value: unknown] }>()
const { t, te } = useI18n()
const key = computed(() => `${props.namespace}.${props.group}.${props.hint.field}`)
const label = computed(() =>
  te(`${key.value}.label`) ? t(`${key.value}.label`) : props.hint.field || ''
)
const tip = computed(() => (te(`${key.value}.tip`) ? t(`${key.value}.tip`) : ''))
const isAction = computed(() => ['button', 'dropdown-button'].includes(props.hint.component || ''))
const update = (value: unknown) =>
  isAction.value ? emit('action', value) : emit('update:value', value)
const pick = async () => {
  try {
    const selected =
      props.hint.path_kind === 'folder'
        ? await window.electronAPI.selectFolder()
        : (await window.electronAPI.selectFile())?.[0]
    if (selected) emit('update:value', selected)
  } catch (error) {
    message.error(apiErrorMessage(error, t('emulator.toast.filePickerUnavailable')))
  }
}
</script>

<template>
  <div
    class="plugin-field form-grid-24__item form-item-vertical"
    :style="{ '--field-span': configurationFieldSpan(hint.component) }"
  >
    <div class="form-label-wrapper">
      <span class="form-label">{{ label }}</span>
      <a-tooltip v-if="tip" :title="tip"><QuestionCircleOutlined class="help-icon" /></a-tooltip>
    </div>
    <DeclarativeControl
      :component="hint.component"
      :label="label"
      :model-value="value"
      :disabled="disabled || hint.editable === false || loading"
      :loading="loading"
      :secret="hint.secret"
      :path-kind="hint.path_kind"
      :min="hint.min"
      :max="hint.max"
      :multiple="hint.multiple"
      :options="options"
      @update:model-value="update"
      @pick="pick"
    />
  </div>
</template>
