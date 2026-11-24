<script setup lang="ts">
import { computed } from 'vue'
import type { Dayjs } from 'dayjs'
import { useI18n } from 'vue-i18n'
import { DownOutlined, FolderOpenOutlined } from '@ant-design/icons-vue'
import { parseConfigTime, serializeConfigTime } from '@/utils/configDateTime'
import { isSwitchComponent } from './declarativeLayout'
import DeclarativeOrderedSelect from './DeclarativeOrderedSelect.vue'
import SettingToggleButton from '@/components/SettingToggleButton.vue'

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
    compact?: boolean
    bordered?: boolean
    secret?: boolean
    masked?: boolean
    format?: string | null
    widget?: string | null
    ordered?: boolean
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
    masked: false,
    format: null,
    widget: null,
    ordered: false,
  }
)

const emit = defineEmits<{ 'update:modelValue': [value: unknown]; pick: []; blur: [] }>()
const { t } = useI18n()

const size = computed(() => (props.compact ? 'middle' : 'large'))
const maskedValue = computed(
  () => (props.masked || props.secret) && props.modelValue === '__AUTO_MAS_CONFIG_MASKED__'
)
const kind = computed(() => {
  // 结合声明组件类型与实际字段值选择渲染控件，兼容布尔、引用选择和其他字段别名。
  const component = props.component?.toLowerCase() ?? 'input'
  if (props.secret || props.masked) return 'password'
  if (component === 'textarea' || props.widget === 'textarea') return 'textarea'
  if (component === 'time' || props.format === 'time') return 'time'
  if (component === 'datetime' || props.format === 'datetime') return 'datetime'
  if ((component === 'segmented' || props.widget === 'segmented') && props.options.length)
    return 'segmented'
  if (isSwitchComponent(component)) return 'toggle-button'
  if (component === 'ref-select') return 'select'
  return ['path', 'number', 'select', 'date', 'button', 'dropdown-button'].includes(component)
    ? component
    : 'input'
})

const update = (value: unknown) =>
  /* 把控件值变更通过模型更新事件交给上层，持久化由表单负责。 */ emit('update:modelValue', value)
const updateDate = (value: unknown) =>
  /* 将日期清空事件规范化为空串后提交控件值变更。 */ update(value ?? '')
const dateValue = computed(() => (typeof props.modelValue === 'string' ? props.modelValue : ''))
const timeValue = computed(() =>
  dateValue.value.includes('T')
    ? parseConfigTime(dateValue.value)?.format('HH:mm')
    : dateValue.value.slice(0, 5) || undefined
)
const updateTime = (value: string | null) => {
  // datetime 字段也可声明只编辑钟点，保留原日期、秒和精度。
  const original = dateValue.value
  const date = original.includes('T') && parseConfigTime(original)
  if (!value || !date) return update(value)
  update(
    serializeConfigTime(`${date.format('YYYY-MM-DD')}T${value}:${date.format('ss')}`, original)
  )
}
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
    :class="[`declarative-control--${kind}`, { 'declarative-control--compact': compact }]"
  >
    <a-switch
      v-if="compact && kind === 'toggle-button'"
      :aria-label="label"
      :checked="Boolean(modelValue)"
      :disabled="disabled"
      :loading="loading"
      @update:checked="update"
    />
    <SettingToggleButton
      v-else-if="kind === 'toggle-button'"
      :model-value="Boolean(modelValue)"
      :disabled="disabled"
      :loading="loading"
      @change="update"
    />
    <a-button
      v-else-if="kind === 'button'"
      class="declarative-control__button"
      :size="size"
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
      <a-button :size="size" :disabled="disabled || !options.length" :loading="loading">
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
      v-else-if="kind === 'password'"
      :size="size"
      :value="maskedValue ? '' : modelValue"
      :placeholder="maskedValue ? t('core.plugins.maskedPlaceholder') : undefined"
      :disabled="disabled"
      :bordered="bordered"
      @update:value="update"
      @blur="emit('blur')"
    />
    <component
      :is="kind === 'textarea' ? 'a-textarea' : 'a-input'"
      v-else-if="kind === 'input' || kind === 'textarea'"
      :size="size"
      :value="modelValue"
      :disabled="disabled"
      :bordered="bordered"
      @update:value="update"
      @blur="emit('blur')"
    />
    <div v-else-if="kind === 'path'" class="path-input-group">
      <a-input
        class="path-input"
        :size="size"
        :value="modelValue"
        :disabled="disabled"
        :bordered="bordered"
        readonly
        @update:value="update"
        @blur="emit('blur')"
      />
      <a-button
        class="path-button"
        :size="size"
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
      :size="size"
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
      :size="size"
      :value="typeof modelValue === 'string' && modelValue ? modelValue : undefined"
      value-format="YYYY-MM-DD"
      allow-clear
      :disabled="disabled"
      :bordered="bordered"
      @change="updateDate"
    />
    <a-time-picker
      v-else-if="kind === 'time'"
      :size="size"
      :value="timeValue"
      format="HH:mm"
      value-format="HH:mm"
      :disabled="disabled"
      :bordered="bordered"
      @change="updateTime"
    />
    <a-date-picker
      v-else-if="kind === 'datetime'"
      :size="size"
      show-time
      :value="parseConfigTime(dateValue)"
      :disabled="disabled"
      :bordered="bordered"
      @change="
        (value: Dayjs | null) => update(value ? serializeConfigTime(value, dateValue) : null)
      "
    />
    <a-segmented
      v-else-if="kind === 'segmented'"
      :size="size"
      :value="options.findIndex(option => option.value === modelValue)"
      :options="
        options.map((option, index) => ({
          label: option.label ?? String(option.value),
          value: index,
        }))
      "
      :disabled="disabled"
      @update:value="(index: number) => update(options[index]?.value)"
    />
    <DeclarativeOrderedSelect
      v-else-if="kind === 'select' && multiple && ordered"
      :size="size"
      :selected="Array.isArray(modelValue) ? modelValue : []"
      :options="options"
      :disabled="disabled || loading"
      @change="update"
    />
    <a-select
      v-else
      :size="size"
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

<style scoped>
.declarative-control:not(
  .declarative-control--toggle-button,
  .declarative-control--button,
  .declarative-control--dropdown-button
),
.declarative-control > :is(.ant-input-number, .ant-picker, .ant-select) {
  width: 100%;
}

.declarative-control--compact > .ant-input-number {
  width: 92px;
  max-width: 100%;
}

.path-input-group {
  display: flex;
}

.path-input {
  flex: 1;
  min-width: 0;
}
</style>
