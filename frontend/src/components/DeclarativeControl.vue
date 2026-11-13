<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { DownOutlined, FolderOpenOutlined } from '@ant-design/icons-vue'
import SettingToggleButton from './SettingToggleButton.vue'

type ControlKind =
  | 'input'
  | 'path'
  | 'number'
  | 'select'
  | 'date'
  | 'toggle-button'
  | 'button'
  | 'dropdown-button'
type Option = { value?: string | number | boolean; label?: string }

const props = withDefaults(
  defineProps<{
    component?: string
    label?: string
    modelValue?: unknown
    disabled?: boolean
    loading?: boolean
    min?: number | null
    max?: number | null
    options?: Option[]
    multiple?: boolean
    pathKind?: string | null
    bordered?: boolean
    secret?: boolean
  }>(),
  {
    component: 'input',
    label: '',
    modelValue: undefined,
    disabled: false,
    loading: false,
    min: null,
    max: null,
    options: () => /* 为未声明选项的控件提供独立空列表，避免组件实例共享可变默认值。 */ [],
    multiple: false,
    pathKind: null,
    bordered: true,
    secret: false,
  }
)

const emit = defineEmits<{ 'update:modelValue': [value: unknown]; pick: []; blur: [] }>()
const { t } = useI18n()

const kind = computed<ControlKind>(() => {
  // 结合声明组件类型与实际字段值选择渲染控件，兼容布尔、引用选择和其他字段别名。
  const component = props.component?.toLowerCase()
  if (
    component === 'bool' ||
    component === 'boolean' ||
    component === 'checkbox' ||
    component === 'toggle-button'
  ) {
    return 'toggle-button'
  }
  if (component === 'switch') return 'toggle-button'
  if (component === 'ref-select') return 'select'
  if (
    component === 'path' ||
    component === 'number' ||
    component === 'select' ||
    component === 'date' ||
    component === 'button' ||
    component === 'dropdown-button'
  ) {
    return component
  }
  return 'input'
})

const update = (value: unknown) =>
  /* 把控件值变更通过模型更新事件交给上层，持久化由表单负责。 */ emit('update:modelValue', value)
const updateDate = (value: unknown) =>
  /* 将日期清空事件规范化为空串后提交控件值变更。 */ update(value ?? '')
const selectOption = (key: string | number) => {
  // 根据下拉选择键找回声明中的原始值类型，再向上层提交。
  const option = props.options.find(
    item =>
      /* 以字符串形式比较选项键，兼容下拉控件返回的数字或文本标识。 */ String(item.value) ===
      String(key)
  )
  update(option?.value ?? key)
}
</script>

<template>
  <div
    class="declarative-control"
    :class="[`declarative-control--${kind}`, { 'declarative-control--disabled': disabled }]"
  >
    <SettingToggleButton
      v-if="kind === 'toggle-button'"
      :model-value="Boolean(modelValue)"
      :disabled="disabled"
      :loading="loading"
      @change="update"
    />
    <a-button
      v-else-if="kind === 'button'"
      class="declarative-control__button"
      block
      size="large"
      :disabled="disabled"
      :loading="loading"
      @click="update(true)"
    >
      {{ label || t('core.common.confirm') }}
    </a-button>
    <a-dropdown
      v-else-if="kind === 'dropdown-button'"
      class="declarative-control__dropdown"
      :trigger="['click']"
      :disabled="disabled || loading || !options.length"
    >
      <a-button block size="large" :disabled="disabled || !options.length" :loading="loading">
        {{ label || t('core.common.confirm') }} <DownOutlined />
      </a-button>
      <template #overlay>
        <a-menu @click="selectOption($event.key)">
          <a-menu-item v-for="option in options" :key="String(option.value)">
            {{ option.label || String(option.value) }}
          </a-menu-item>
        </a-menu>
      </template>
    </a-dropdown>
    <a-input-password
      v-else-if="kind === 'input' && secret"
      size="large"
      :value="modelValue"
      :disabled="disabled"
      :bordered="bordered"
      @update:value="update"
      @blur="emit('blur')"
    />
    <a-input
      v-else-if="kind === 'input'"
      size="large"
      :value="modelValue"
      :disabled="disabled"
      :bordered="bordered"
      @update:value="update"
      @blur="emit('blur')"
    />
    <div v-else-if="kind === 'path'" class="path-input-group">
      <a-input
        class="path-input"
        size="large"
        :value="modelValue"
        :disabled="disabled"
        :bordered="bordered"
        readonly
        @update:value="update"
        @blur="emit('blur')"
      />
      <a-button
        class="path-button"
        size="large"
        :disabled="disabled"
        :aria-label="pathKind === 'folder' ? t('core.edit.pickDirectory') : t('core.comp.pickFile')"
        @click="emit('pick')"
      >
        <template #icon>
          <FolderOpenOutlined />
        </template>
        <span class="path-button-label">{{
          pathKind === 'folder' ? t('core.edit.pickDirectory') : t('core.comp.pickFile')
        }}</span>
      </a-button>
    </div>
    <a-input-number
      v-else-if="kind === 'number'"
      size="large"
      :value="modelValue"
      :disabled="disabled"
      :bordered="bordered"
      :min="min ?? undefined"
      :max="max ?? undefined"
      @update:value="update"
      @blur="emit('blur')"
    />
    <a-date-picker
      v-else-if="kind === 'date'"
      size="large"
      :value="typeof modelValue === 'string' && modelValue ? modelValue : undefined"
      value-format="YYYY-MM-DD"
      allow-clear
      :disabled="disabled"
      :bordered="bordered"
      @change="updateDate"
    />
    <a-select
      v-else
      size="large"
      :value="modelValue"
      :mode="multiple ? 'multiple' : undefined"
      :disabled="disabled"
      :bordered="bordered"
      :options="options"
      :loading="loading"
      @update:value="update"
    />
  </div>
</template>
