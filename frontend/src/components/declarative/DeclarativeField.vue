<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import type { DeclarativeHint, DeclarativeOption } from '@/composables/useDeclarativeOptions'
import DeclarativeControl from './DeclarativeControl.vue'
import { createDeclarativeI18n, type DeclarativeI18nScope } from './declarativeI18n'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import { apiErrorMessage } from '@/utils/apiResult'

const props = withDefaults(
  defineProps<{
    group: string
    namespace: string
    scope: DeclarativeI18nScope
    hint: DeclarativeHint
    value: unknown
    options: Required<DeclarativeOption>[]
    loading?: boolean
    disabled?: boolean
    error?: string
    disabledReason?: string
    tableCell?: boolean
    retry?: () => void
    inlineAction?: {
      group: string
      hint: DeclarativeHint
      options: Required<DeclarativeOption>[]
      loading: boolean
      run: (value: unknown) => void
    }
  }>(),
  { error: undefined, disabledReason: undefined, retry: undefined, inlineAction: undefined }
)
const emit = defineEmits<{
  'update:value': [value: unknown]
  action: [value: unknown]
  blur: []
  commit: []
}>()
const { t, te, locale } = useI18n()
const i18n = computed(() =>
  createDeclarativeI18n(t, te, locale.value, props.namespace, props.scope)
)
// 字段和行内动作分别使用所属分组的翻译，缺失时展示声明字段名。
function fieldLabel(group: string, hint: DeclarativeHint) {
  return i18n.value.config(`${group}.${hint.field}.label`) ?? hint.field ?? ''
}
const label = computed(() => fieldLabel(props.group, props.hint))
const tip = computed(() => i18n.value.tip(props.group, props.hint))
const stepper = computed(() => {
  if (props.tableCell || props.scope !== 'script' || props.group !== 'Run') return undefined
  switch (props.hint.field) {
    case 'GameUpdateTimeLimit':
    case 'HardTimeLimit':
    case 'RunTimeLimit':
      return { unit: t('core.edit.stepperUnitTimeout'), step: 5 }
    case 'ProxyTimesLimit':
      return {
        unit: t('core.edit.stepperUnitDaily'),
        zeroLabel: t('core.edit.stepperUnlimited'),
        step: 1,
      }
    case 'RunTimesLimit':
      return { unit: t('core.edit.stepperUnitRetry'), step: 1 }
    default:
      return undefined
  }
})
const pathHint = computed(() =>
  props.hint.component === 'path' && props.hint.path_must_exist
    ? t('core.plugins.pathMustExistHint')
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
    const extensions = props.hint.path_extensions
    const filters = extensions?.length ? [{ name: label.value, extensions }] : undefined
    const selected =
      props.hint.path_kind === 'folder'
        ? await window.electronAPI.selectFolder()
        : (await window.electronAPI.selectFile(filters))?.[0]
    if (selected) {
      emit('update:value', selected)
      emit('commit')
    }
  } catch (error) {
    message.error(apiErrorMessage(error, t('core.emulator.toast.filePickerUnavailable')))
  }
}
</script>

<template>
  <div
    class="declarative-field"
    :aria-label="label"
    :title="tableCell ? tip || undefined : undefined"
  >
    <FieldLabelWithHint v-if="!tableCell" :text="label" :hint="tip" variant="form" />
    <div class="declarative-field-body" :class="{ 'with-action': inlineAction }">
      <DeclarativeControl
        :compact="tableCell"
        :component="hint.component"
        :label="label"
        :model-value="value"
        :disabled="disabled || hint.editable === false || loading"
        :loading="loading"
        :secret="hint.secret"
        :masked="hint.masked"
        :format="hint.format"
        :widget="hint.widget"
        :ordered="hint.ordered"
        :path-kind="hint.path_kind"
        :min="hint.min"
        :max="hint.max"
        :precision="hint.precision"
        :step="stepper?.step ?? hint.step"
        :unit="stepper?.unit"
        :zero-label="stepper?.zeroLabel"
        :multiple="hint.multiple"
        :options="options"
        @update:model-value="update"
        @pick="pick"
        @blur="emit('blur')"
        @commit="emit('commit')"
      />
      <DeclarativeControl
        v-if="inlineAction"
        :compact="tableCell"
        :component="inlineAction.hint.component"
        :label="fieldLabel(inlineAction.group, inlineAction.hint)"
        :options="inlineAction.options"
        :loading="inlineAction.loading"
        :disabled="disabled || inlineAction.loading || inlineAction.hint.editable !== true"
        @update:model-value="inlineAction.run"
      />
    </div>
    <p v-if="error" class="field-error" role="alert">{{ error }}</p>
    <p v-else-if="disabledReason" class="field-reason">{{ disabledReason }}</p>
    <p v-else-if="pathHint" class="field-reason">{{ pathHint }}</p>
    <a-button v-if="retry" size="small" type="link" :loading="loading" @click="retry">
      {{ t('core.common.retry') }}
    </a-button>
  </div>
</template>

<style scoped>
.declarative-field,
.declarative-field-body {
  display: grid;
  align-content: start;
  gap: 8px;
  min-width: 0;
  overflow-wrap: anywhere;
}
.declarative-field:has(> .field-label + .declarative-field-body > .declarative-control--switch) {
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  column-gap: 12px;
  min-height: 36px;
  padding-block: 4px;
}
.declarative-field > :is(.field-error, .field-reason, .ant-btn) {
  grid-column: 1 / -1;
}
.declarative-field > .ant-btn {
  justify-self: start;
}
.declarative-field-body.with-action {
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
}
.field-error,
.field-reason {
  margin: 0;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  line-height: 20px;
}
.field-error {
  color: var(--ant-color-error);
}
</style>
