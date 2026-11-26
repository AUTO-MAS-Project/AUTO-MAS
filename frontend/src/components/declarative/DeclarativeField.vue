<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import type { DeclarativeHint, DeclarativeOption } from '@/composables/useDeclarativeOptions'
import DeclarativeControl from './DeclarativeControl.vue'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import { SwitchTile } from '@/components/ui'
import { apiErrorMessage } from '@/utils/apiResult'

const props = withDefaults(
  defineProps<{
    group: string
    namespace: string
    hint: DeclarativeHint
    value: unknown
    options: Required<DeclarativeOption>[]
    loading?: boolean
    disabled?: boolean
    error?: string
    disabledReason?: string
    tile?: boolean
    tableCell?: boolean
    retry?: () => void
  }>(),
  { error: undefined, disabledReason: undefined, retry: undefined }
)
const emit = defineEmits<{ 'update:value': [value: unknown]; action: [value: unknown]; blur: [] }>()
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
    if (selected) emit('update:value', selected)
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
    <SwitchTile
      v-if="tile && !tableCell"
      :title="label"
      :description="tip || undefined"
      :checked="Boolean(value)"
      :disabled="disabled || hint.editable === false || loading"
      :loading="loading"
      @change="update"
    />
    <div v-else class="declarative-field-body">
      <FieldLabelWithHint v-if="!tableCell" :text="label" :hint="tip" variant="form" />
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
        :multiple="hint.multiple"
        :options="options"
        @update:model-value="update"
        @pick="pick"
        @blur="emit('blur')"
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
  gap: 6px;
  min-width: 0;
  overflow-wrap: anywhere;
}
.declarative-field > .ant-btn {
  justify-self: start;
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
