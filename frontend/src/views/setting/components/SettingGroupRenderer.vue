<script setup lang="ts">
import { computed, reactive } from 'vue'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import type { ComponentHint, UiHintsMap } from '@/api'
import DeclarativeControl from '@/components/DeclarativeControl.vue'
import type { SettingsCategory, SettingsViewModel } from '@/types/settings'
import { settingsViewKey } from '@/types/settings'
import { configurationFieldSpan } from '@/utils/declarativeLayout'

type Option = { value: string | number | boolean; label: string }

const props = withDefaults(
  defineProps<{
    group: string
    category: SettingsCategory
    settings: SettingsViewModel
    hints?: UiHintsMap
    include?: string[]
    exclude?: string[]
    disabledFields?: Record<string, boolean>
    hiddenFields?: Record<string, boolean>
    labelKeys?: Record<string, string>
    tipKeys?: Record<string, string>
    optionLabels?: Record<string, Record<string, string>>
    handleSettingChange: (
      category: SettingsCategory,
      key: string,
      value: unknown
    ) => Promise<boolean>
  }>(),
  {
    hints: undefined,
    include: undefined,
    exclude: () => [],
    disabledFields: () => ({}),
    hiddenFields: () => ({}),
    labelKeys: () => ({}),
    tipKeys: () => ({}),
    optionLabels: () => ({}),
  }
)

const { t } = useI18n()

const drafts = reactive<Record<string, unknown>>({})
const pending = reactive<Record<string, boolean>>({})

const groupData = computed<Record<string, unknown>>(() => {
  const value = props.settings[props.category]
  return value && typeof value === 'object' ? (value as Record<string, unknown>) : {}
})

const sourceHints = computed<ComponentHint[]>(() => props.hints?.[props.group] ?? [])
const fieldHints = computed(() =>
  sourceHints.value.filter(hint => {
    const field = hint.field
    if (
      !field ||
      props.exclude.includes(field) ||
      (props.include && !props.include.includes(field))
    ) {
      return false
    }
    return !props.hiddenFields[field]
  })
)

const componentName = (hint: ComponentHint) => hint.component ?? 'input'

const fieldSpan = (hint: ComponentHint) => configurationFieldSpan(componentName(hint))

const viewField = (field: string) => settingsViewKey(props.group, field)
const fieldValue = (field: string) =>
  Object.prototype.hasOwnProperty.call(drafts, field)
    ? drafts[field]
    : groupData.value[viewField(field)]

const labelFor = (field: string) => {
  const key = props.labelKeys[field]
  return key ? t(key) : field
}
const tipFor = (field: string) => {
  const key = props.tipKeys[field]
  return key ? t(key) : undefined
}

const coerceOption = (field: string, value: string | number | boolean) => {
  const current = fieldValue(field)
  if (typeof current === 'number' && typeof value === 'string' && value !== '') return Number(value)
  if (typeof current === 'boolean' && typeof value === 'string') return value === 'true'
  return value
}

const optionsFor = (hint: ComponentHint): Option[] => {
  const field = hint.field ?? ''
  return (hint.options ?? []).map(option => {
    const value = option.value
    const optionLabel = props.optionLabels[field]?.[value]
    return {
      value: coerceOption(field, value),
      label: optionLabel ? t(optionLabel) : value,
    }
  })
}

const isDeferred = (hint: ComponentHint) =>
  ['input', 'path', 'number'].includes(componentName(hint).toLowerCase())

const save = async (field: string, value: unknown) => {
  if (pending[field]) return
  pending[field] = true
  try {
    const saved = await props.handleSettingChange(props.category, viewField(field), value)
    if (saved) delete drafts[field]
  } finally {
    pending[field] = false
  }
}

const update = (hint: ComponentHint, value: unknown) => {
  const field = hint.field
  if (!field) return
  if (isDeferred(hint)) {
    drafts[field] = value
    return
  }
  void save(field, value)
}

const blur = (hint: ComponentHint) => {
  const field = hint.field
  if (!field || !Object.prototype.hasOwnProperty.call(drafts, field)) return
  void save(field, drafts[field])
}

const pickPath = (hint: ComponentHint) => {
  const field = hint.field
  if (!field || !window.electronAPI) return

  void (async () => {
    try {
      const selected =
        hint.path_kind === 'file'
          ? ((await window.electronAPI.selectFile())?.[0] ?? null)
          : await window.electronAPI.selectFolder()
      if (selected) await save(field, selected)
    } catch (error) {
      message.error(t('comp.couldNotPickFile'))
      console.error('配置路径选择失败', error)
    }
  })()
}
</script>

<template>
  <div class="form-grid-24 setting-group-grid">
    <div
      v-for="hint in fieldHints"
      :key="hint.field"
      class="form-grid-24__item setting-group-field"
      :style="{ '--field-span': fieldSpan(hint) }"
    >
      <div class="form-item-vertical">
        <div class="form-label-wrapper">
          <span class="form-label">{{ labelFor(hint.field ?? '') }}</span>
          <a-tooltip v-if="tipFor(hint.field ?? '')" :title="tipFor(hint.field ?? '')">
            <QuestionCircleOutlined class="help-icon" />
          </a-tooltip>
        </div>
        <DeclarativeControl
          :component="hint.component"
          :label="labelFor(hint.field ?? '')"
          :model-value="fieldValue(hint.field ?? '')"
          :disabled="
            hint.editable === false ||
            disabledFields[hint.field ?? ''] === true ||
            pending[hint.field ?? ''] === true
          "
          :loading="pending[hint.field ?? ''] === true"
          :secret="hint.secret === true"
          :min="hint.min"
          :max="hint.max"
          :options="optionsFor(hint)"
          :multiple="hint.multiple === true"
          @update:model-value="update(hint, $event)"
          @blur="blur(hint)"
          @pick="pickPath(hint)"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.setting-group-grid {
  width: 100%;
}

.setting-group-field {
  min-width: 0;
}
</style>
