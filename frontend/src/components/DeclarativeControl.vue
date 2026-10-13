<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { FolderOpenOutlined } from '@ant-design/icons-vue'
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
    options: () => [],
    multiple: false,
    pathKind: null,
    bordered: true,
    secret: false,
  }
)

const emit = defineEmits<{ 'update:modelValue': [value: unknown]; pick: []; blur: [] }>()
const { t } = useI18n()

const kind = computed<ControlKind>(() => {
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

const update = (value: unknown) => emit('update:modelValue', value)
const updateDate = (value: unknown) => update(value ?? '')
const selectOption = (key: string | number) => {
  const option = props.options.find(item => String(item.value) === String(key))
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
      {{ label || t('common.confirm') }}
    </a-button>
    <a-dropdown-button
      v-else-if="kind === 'dropdown-button'"
      class="declarative-control__dropdown"
      size="large"
      :disabled="disabled"
      :loading="loading"
      @click="update(true)"
    >
      {{ label || t('common.confirm') }}
      <template #overlay>
        <a-menu @click="selectOption($event.key)">
          <a-menu-item v-for="option in options" :key="String(option.value)">
            {{ option.label || String(option.value) }}
          </a-menu-item>
        </a-menu>
      </template>
    </a-dropdown-button>
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
        :aria-label="pathKind === 'folder' ? t('comp.pickDirectory') : t('comp.pickFile')"
        @click="emit('pick')"
      >
        <template #icon>
          <FolderOpenOutlined />
        </template>
        <span class="path-button-label">{{
          pathKind === 'folder' ? t('comp.pickDirectory') : t('comp.pickFile')
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
