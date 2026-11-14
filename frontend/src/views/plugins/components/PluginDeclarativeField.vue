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
const key = computed(
  () =>
    /* 由插件命名空间、配置分组与字段名生成当前控件的语言资源键。 */ `${props.namespace}.${props.group}.${props.hint.field}`
)
const label = computed(() =>
  /* 读取当前控件的翻译标签，缺失时展示声明字段名。 */ te(`${key.value}.label`)
    ? t(`${key.value}.label`)
    : props.hint.field || ''
)
const tip = computed(() =>
  /* 读取当前控件的翻译说明，无对应资源时不显示说明。 */ te(`${key.value}.tip`)
    ? t(`${key.value}.tip`)
    : ''
)
const isAction = computed(() =>
  /* 判断当前控件是否为按钮类动作，以区分触发操作和普通编辑。 */ [
    'button',
    'dropdown-button',
  ].includes(props.hint.component || '')
)
const update = (value: unknown) =>
  /* 按控件语义发送动作事件或字段值变更事件，由上层决定执行或保存。 */ isAction.value
    ? emit('action', value)
    : emit('update:value', value)
const pick = async () => {
  // 按路径类型打开文件或目录选择器，将选中路径提交给表单，并展示选择失败原因。
  try {
    const selected =
      props.hint.path_kind === 'folder'
        ? await window.electronAPI.selectFolder()
        : (await window.electronAPI.selectFile())?.[0]
    if (selected) emit('update:value', selected)
  } catch (error) {
    message.error(apiErrorMessage(error, t('core.emulator.toast.filePickerUnavailable')))
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
