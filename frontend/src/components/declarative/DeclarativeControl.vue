<script setup lang="ts">
import { computed } from 'vue'
import type { Dayjs } from 'dayjs'
import { useI18n } from 'vue-i18n'
import { DownOutlined, FolderOpenOutlined } from '@ant-design/icons-vue'
import { NumberStepper } from '@/components/ui'
import { parseConfigTime, serializeConfigTime } from '@/utils/configDateTime'
import { isBrowserDevelopment } from '@/utils/environment'
import DeclarativeOrderedSelect from './DeclarativeOrderedSelect.vue'

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
    precision?: number
    step?: number
    unit?: string
    zeroLabel?: string
    options?: Option[]
    multiple?: boolean
    pathKind?: string | null
    compact?: boolean
    bordered?: boolean
    secret?: boolean
    masked?: boolean
    format?: string | null
    nullable?: boolean
    required?: boolean
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
    precision: undefined,
    step: undefined,
    unit: undefined,
    zeroLabel: undefined,
    options: () => /* 为未声明选项的控件提供独立空列表，避免组件实例共享可变默认值。 */ [],
    multiple: false,
    pathKind: null,
    bordered: true,
    secret: false,
    masked: false,
    format: null,
    nullable: true,
    widget: null,
    ordered: false,
  }
)

const emit = defineEmits<{
  'update:modelValue': [value: unknown]
  pick: []
  blur: []
  commit: []
}>()
const { t } = useI18n()

const size = computed(() => (props.compact ? 'middle' : 'large'))
const allowClear = computed(() => props.nullable && !props.required)
const maskedValue = computed(
  () => (props.masked || props.secret) && props.modelValue === '__AUTO_MAS_CONFIG_MASKED__'
)
const kind = computed(() => {
  // 声明的格式或部件可覆盖默认控件，引用字段复用选择框。
  const component = props.component
  if (props.secret || props.masked) return 'password'
  if (component === 'textarea' || props.widget === 'textarea') return 'textarea'
  if (component === 'time' || props.format === 'time') return 'time'
  if (component === 'datetime' || props.format === 'datetime') return 'datetime'
  if ((component === 'segmented' || props.widget === 'segmented') && props.options.length)
    return 'segmented'
  if (component === 'ref-select') return 'select'
  if (component === 'path' && isBrowserDevelopment()) return 'input'
  return ['switch', 'path', 'number', 'select', 'date', 'button', 'dropdown-button'].includes(
    component
  )
    ? component
    : 'input'
})

function update(value: unknown) {
  emit('update:modelValue', props.component === 'path' && value === '' ? null : value)
  if (['switch', 'select', 'segmented', 'date', 'datetime', 'time'].includes(kind.value))
    emit('commit')
}
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
</script>

<template>
  <div
    class="declarative-control"
    :class="[`declarative-control--${kind}`, { 'declarative-control--compact': compact }]"
  >
    <a-switch
      v-if="kind === 'switch'"
      :aria-label="label"
      :checked="Boolean(modelValue)"
      :disabled="disabled"
      :loading="loading"
      @update:checked="update"
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
        <a-menu>
          <!-- 直接派发声明值，避免菜单键把数字和同名字符串合并。 -->
          <a-menu-item
            v-for="(option, index) in options"
            :key="index"
            @click="update(option.value)"
          >
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
    <a-space-compact v-else-if="kind === 'path'" block :size="size">
      <a-input
        class="path-input"
        :size="size"
        :value="modelValue"
        :disabled="disabled"
        :bordered="bordered"
        readonly
        @blur="emit('blur')"
      />
      <a-button
        :size="size"
        :disabled="disabled"
        :aria-label="pathKind === 'folder' ? t('core.edit.pickDirectory') : t('core.comp.pickFile')"
        @click="emit('pick')"
      >
        <template #icon>
          <FolderOpenOutlined />
        </template>
        {{ pathKind === 'folder' ? t('core.edit.pickDirectory') : t('core.comp.pickFile') }}
      </a-button>
    </a-space-compact>
    <NumberStepper
      v-else-if="kind === 'number' && !compact"
      :model-value="typeof modelValue === 'number' ? modelValue : null"
      :disabled="disabled"
      :min="min ?? undefined"
      :max="max ?? undefined"
      :precision="precision"
      :step="step"
      :unit="unit"
      :zero-label="zeroLabel"
      :aria-label="label"
      @update:model-value="update"
      @step="emit('commit')"
      @blur="emit('blur')"
    />
    <a-input-number
      v-else-if="kind === 'number'"
      :size="size"
      :value="modelValue"
      :disabled="disabled"
      :bordered="bordered"
      :min="min ?? undefined"
      :max="max ?? undefined"
      :precision="precision"
      :step="step"
      @update:value="update"
      @step="emit('commit')"
      @blur="emit('blur')"
    />
    <a-date-picker
      v-else-if="kind === 'date'"
      :size="size"
      :value="typeof modelValue === 'string' && modelValue ? modelValue : undefined"
      value-format="YYYY-MM-DD"
      :allow-clear="allowClear"
      :disabled="disabled"
      :bordered="bordered"
      @change="update"
    />
    <a-time-picker
      v-else-if="kind === 'time'"
      :size="size"
      :value="timeValue"
      format="HH:mm"
      value-format="HH:mm"
      :allow-clear="allowClear"
      :disabled="disabled"
      :bordered="bordered"
      @change="updateTime"
    />
    <a-date-picker
      v-else-if="kind === 'datetime'"
      :size="size"
      show-time
      :value="parseConfigTime(dateValue)"
      :allow-clear="allowClear"
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
  .declarative-control--switch,
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

.path-input {
  flex: 1;
  min-width: 0;
}
</style>
