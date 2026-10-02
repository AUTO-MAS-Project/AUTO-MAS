<template>
  <a-modal
    :open="open"
    :title="t('edit.mfwHotkey')"
    :width="560"
    :keyboard="!recording"
    :mask-closable="!recording"
    destroy-on-close
    @cancel="emit('update:open', false)"
  >
    <div class="hotkey-modal">
      <div v-if="description" class="hotkey-modal-sub">{{ description }}</div>
      <template v-for="option in options" :key="option.name">
        <div class="hotkey-group-title">
          {{ option.label || option.name }}
          <span v-if="gates[option.name]" class="hotkey-group-gate">
            {{ gateText(gates[option.name]) }}
          </span>
        </div>
        <div
          v-for="field in option.hotkeys"
          :key="field.name"
          class="hotkey-row"
          :class="{ 'is-changed': isChanged(option.name, field) }"
        >
          <div class="hotkey-line">
            <a-tooltip v-if="field.description" :title="field.description">
              <span class="hotkey-label">{{ field.label || field.name }}</span>
            </a-tooltip>
            <span v-else class="hotkey-label">{{ field.label || field.name }}</span>
            <span v-if="isChanged(option.name, field)" class="hotkey-hint">
              {{ t('edit.mfwHotkeyDefaultKey', { key: displayCombo(field.default) }) }}
              <a class="hotkey-link" @click="resetField(option.name, field)">
                {{ t('edit.mfwHotkeyRestore') }}
              </a>
            </span>
            <MaaFWHotkeyInput
              :value="draft[option.name]?.[field.name] ?? ''"
              :changed="isChanged(option.name, field)"
              :error="Boolean(errorOf(option.name, field.name))"
              :label="field.label || field.name"
              @recording="value => handleRecording(option.name, field.name, value)"
              @record="result => handleRecord(option.name, field.name, result)"
            />
          </div>
          <div v-if="errorOf(option.name, field.name)" class="hotkey-error">
            {{ errorOf(option.name, field.name) }}
          </div>
        </div>
      </template>
    </div>
    <template #footer>
      <div class="hotkey-footer">
        <a-button type="link" class="hotkey-reset-all" :disabled="!anyChanged" @click="resetAll">
          {{ t('edit.mfwHotkeyRestoreAll') }}
        </a-button>
        <a-space>
          <a-button @click="emit('update:open', false)">{{ t('common.cancel') }}</a-button>
          <a-button type="primary" @click="handleSave">{{ t('edit.mfwHotkeySave') }}</a-button>
        </a-space>
      </div>
    </template>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { MaaFWOptionInfo } from '@/types/script'
import {
  displayKey,
  formatHotkey,
  parseHotkey,
  sameHotkey,
  type HotkeyEventResult,
} from '@/utils/maafwHotkey'
import MaaFWHotkeyInput from './MaaFWHotkeyInput.vue'
import { countChangedHotkeys, type MaaFWHotkeyGate, type MaaFWHotkeyMap } from './hotkeyOptions'

type HotkeyField = MaaFWOptionInfo['hotkeys'][number]

const props = defineProps<{
  open: boolean
  /** 本次展示的 hotkey option（已按生效控制器 / 资源过滤、排好序） */
  options: MaaFWOptionInfo[]
  /** 打开时各字段的生效值（存的值，没有就是默认值） */
  values: MaaFWHotkeyMap
  /** 副标题：项目 setting 的 description，没有就是空串 */
  description: string
  /** 只在某个选项分支下才生效的 option → 生效条件（组标题旁提示） */
  gates: Record<string, MaaFWHotkeyGate>
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  /** 点了保存：交回本次展示的全部字段的值，由调用方合并进 Game.Hotkeys */
  save: [values: MaaFWHotkeyMap]
}>()

const { t } = useI18n()

/** 弹窗内的草稿：取消即丢弃 */
const draft = reactive<MaaFWHotkeyMap>({})
const errors = reactive<Record<string, string>>({})
const recordingField = ref('')
const recording = computed(() => recordingField.value !== '')

const fieldKey = (optionName: string, fieldName: string) => `${optionName}\u0000${fieldName}`

const resetDraft = () => {
  for (const key of Object.keys(draft)) delete draft[key]
  for (const key of Object.keys(errors)) delete errors[key]
  for (const [optionName, fields] of Object.entries(props.values)) {
    draft[optionName] = { ...fields }
  }
  recordingField.value = ''
}

watch(
  () => props.open,
  value => {
    if (value) resetDraft()
  },
  { immediate: true }
)

const displayCombo = (value: string | null | undefined) =>
  parseHotkey(value).map(displayKey).join(' + ')

const gateText = (gate: MaaFWHotkeyGate) =>
  gate.switchOn
    ? t('edit.mfwHotkeyNeedsSwitch', { option: gate.option })
    : t('edit.mfwHotkeyNeedsCase', { option: gate.option, case: gate.caseLabel })

const isChanged = (optionName: string, field: HotkeyField) =>
  !sameHotkey(draft[optionName]?.[field.name] ?? '', field.default ?? '')

const anyChanged = computed(() => countChangedHotkeys(props.options, draft) > 0)

const errorOf = (optionName: string, fieldName: string) =>
  errors[fieldKey(optionName, fieldName)] ?? ''

const setValue = (optionName: string, fieldName: string, value: string) => {
  if (!draft[optionName]) draft[optionName] = {}
  draft[optionName][fieldName] = value
}

const resetField = (optionName: string, field: HotkeyField) => {
  setValue(optionName, field.name, formatHotkey(parseHotkey(field.default ?? '')))
  delete errors[fieldKey(optionName, field.name)]
}

const resetAll = () => {
  for (const option of props.options) {
    for (const field of option.hotkeys ?? []) resetField(option.name, field)
  }
}

const handleRecording = (optionName: string, fieldName: string, value: boolean) => {
  const key = fieldKey(optionName, fieldName)
  if (value) {
    recordingField.value = key
    delete errors[key]
  } else if (recordingField.value === key) {
    recordingField.value = ''
  }
}

const handleRecord = (
  optionName: string,
  fieldName: string,
  result: Exclude<HotkeyEventResult, { kind: 'ignored' } | { kind: 'modifier-only' }>
) => {
  const key = fieldKey(optionName, fieldName)
  if (result.kind === 'combo') {
    delete errors[key]
    setValue(optionName, fieldName, formatHotkey(result.keys))
    return
  }
  // 录制失败：值不变，框变红 + 行下提示
  errors[key] =
    result.kind === 'too-many-modifiers'
      ? t('edit.mfwHotkeyTooManyModifiers')
      : t('edit.mfwHotkeyUnsupported')
}

const handleSave = () => {
  const values: MaaFWHotkeyMap = {}
  for (const option of props.options) {
    values[option.name] = { ...draft[option.name] }
  }
  emit('save', values)
  emit('update:open', false)
}
</script>

<style scoped>
.hotkey-modal-sub {
  padding: 0 0 8px;
  color: var(--ant-color-text-secondary);
}

.hotkey-group-title {
  padding: 12px 0 6px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
  color: var(--ant-color-text);
  font-weight: 700;
}

.hotkey-group-gate {
  margin-left: 8px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  font-weight: 400;
}

.hotkey-row {
  padding: 4px 0;
}

.hotkey-line {
  display: flex;
  align-items: center;
  gap: 12px;
}

.hotkey-label {
  flex: 1;
  min-width: 0;
  color: var(--ant-color-text);
}

.hotkey-hint {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  white-space: nowrap;
}

.hotkey-link {
  color: var(--ant-color-primary);
}

.hotkey-error {
  padding-top: 2px;
  color: var(--ant-color-error);
  font-size: 12px;
  line-height: 1.5;
  text-align: right;
}

.hotkey-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 8px;
}

.hotkey-reset-all {
  padding: 0;
}
</style>
