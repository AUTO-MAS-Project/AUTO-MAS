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
      <div class="hotkey-modal-combo" :class="{ 'is-error': invalidCount > 0 }">
        {{ comboNote }}
      </div>
      <!-- 列表定高、内部滚动：键位多的项目也不会把弹窗撑出屏幕 -->
      <div class="hotkey-modal-list">
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
                <span class="hotkey-label">
                  {{ field.label || field.name }}
                  <span v-if="rowComboTag(field)" class="hotkey-combo-tag">{{
                    rowComboTag(field)
                  }}</span>
                </span>
              </a-tooltip>
              <span v-else class="hotkey-label">
                {{ field.label || field.name }}
                <span v-if="rowComboTag(field)" class="hotkey-combo-tag">{{
                  rowComboTag(field)
                }}</span>
              </span>
              <span v-if="isChanged(option.name, field)" class="hotkey-hint">
                {{ t('edit.mfwHotkeyDefaultKey', { key: displayCombo(field.default) }) }}
                <a class="hotkey-link" @click="resetField(option.name, field)">
                  {{ t('edit.mfwHotkeyRestore') }}
                </a>
              </span>
              <MaaFWHotkeyInput
                :value="draft[option.name]?.[field.name] ?? ''"
                :changed="isChanged(option.name, field)"
                :error="Boolean(errorOf(option.name, field.name)) || isInvalid(option.name, field)"
                :label="field.label || field.name"
                @recording="value => handleRecording(option.name, field.name, value)"
                @record="result => handleRecord(option.name, field, result)"
              />
            </div>
            <div v-if="errorOf(option.name, field.name)" class="hotkey-error">
              {{ errorOf(option.name, field.name) }}
            </div>
          </div>
        </template>
      </div>
    </div>
    <template #footer>
      <div class="hotkey-footer">
        <div class="hotkey-footer-left">
          <a-button type="link" class="hotkey-reset-all" :disabled="!anyChanged" @click="resetAll">
            {{ t('edit.mfwHotkeyRestoreAll') }}
          </a-button>
          <!-- 上面列出在目录里扫到的外壳配置（注明目录），下面总能另选目录：导入项目时记下的
               来源目录之后不再更新，挪走了或平时用的是另一份外壳就从这里选 -->
          <a-dropdown :trigger="['click']">
            <a-button type="link" class="hotkey-reset-all">
              {{ t('edit.mfwHotkeyImport') }}
              <DownOutlined />
            </a-button>
            <template #overlay>
              <a-menu>
                <a-menu-item-group
                  v-if="shownCandidates.length > 0"
                  :title="t('edit.mfwHotkeyImportFrom', { dir: shownDir })"
                >
                  <a-menu-item
                    v-for="candidate in shownCandidates"
                    :key="candidate.id"
                    @click="applyImport(candidate)"
                  >
                    {{ candidate.source }} · {{ candidate.name }}
                    <a-tag v-if="candidate.active" color="green" class="hotkey-import-tag">
                      {{ t('edit.mfwHotkeyImportLastUsed') }}
                    </a-tag>
                  </a-menu-item>
                </a-menu-item-group>
                <a-menu-divider v-if="shownCandidates.length > 0" />
                <a-menu-item key="__pick-dir" @click="pickImportDirectory">
                  <FolderOpenOutlined />
                  {{ t('edit.mfwHotkeyImportPickDir') }}
                </a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>
        </div>
        <a-space>
          <a-button @click="emit('update:open', false)">{{ t('common.cancel') }}</a-button>
          <a-button type="primary" :disabled="invalidCount > 0" @click="handleSave">
            {{ t('edit.mfwHotkeySave') }}
          </a-button>
        </a-space>
      </div>
    </template>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { DownOutlined, FolderOpenOutlined } from '@ant-design/icons-vue'
import { useMaaFWShellInstanceApi } from '@/composables/useMaaFWShellInstanceApi'
import type { MaaFWOptionInfo } from '@/types/script'
import {
  displayKey,
  formatHotkey,
  parseHotkey,
  sameHotkey,
  type HotkeyEventResult,
} from '@/utils/maafwHotkey'
import MaaFWHotkeyInput from './MaaFWHotkeyInput.vue'
import {
  countChangedHotkeys,
  hotkeyComboSummary,
  hotkeyModifierProblem,
  type MaaFWHotkeyGate,
  type MaaFWHotkeyMap,
} from './hotkeyOptions'
import {
  collectHotkeyImportCandidates,
  importHotkeyValues,
  type MaaFWHotkeyImportCandidate,
} from './hotkeyImport'

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
  /** 「从项目导入」的候选（外壳实例里的键位，已限定到本次展示的字段、相同的已合并）；没有就是空数组 */
  importCandidates: MaaFWHotkeyImportCandidate[]
  /** 上面这些候选是在哪个目录扫到的（导入项目时记下的来源目录，或兜底的内嵌副本） */
  importDir: string
  /** 脚本 ID：「选择其他目录」按它去扫用户选的目录 */
  scriptId: string
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

const MODIFIER_EXAMPLES = ['', 'Ctrl + E', 'Ctrl + Shift + E']

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

// 组合键与项目 pipeline 要的修饰键个数不符（录进来的或之前存的）：框变红、常驻说明变红、
// 不让保存；说明就是上面那行，不再逐行重复。
const isInvalid = (optionName: string, field: HotkeyField) =>
  hotkeyModifierProblem(parseHotkey(draft[optionName]?.[field.name]), field.modifierCount) !== null
const invalidCount = computed(
  () =>
    props.options.flatMap(option =>
      (option.hotkeys ?? []).filter(field => isInvalid(option.name, field))
    ).length
)

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

// 常驻说明：这个项目的键位支不支持组合键（由项目 pipeline 用到的修饰键占位符决定）
const comboSummary = computed(() => hotkeyComboSummary(props.options))
const comboNote = computed(() => {
  const summary = comboSummary.value
  if (summary.kind === 'none') return t('edit.mfwHotkeyNoCombo')
  if (summary.kind === 'all') {
    return t('edit.mfwHotkeyAllCombo', {
      n: summary.count,
      example: MODIFIER_EXAMPLES[summary.count] ?? MODIFIER_EXAMPLES[2],
    })
  }
  return t('edit.mfwHotkeySomeCombo')
})
const rowComboTag = (field: HotkeyField) =>
  comboSummary.value.kind === 'mixed' && (field.modifierCount ?? 0) > 0
    ? t('edit.mfwHotkeyComboTag', { n: field.modifierCount })
    : ''

const handleRecord = (
  optionName: string,
  field: HotkeyField,
  result: Exclude<HotkeyEventResult, { kind: 'ignored' } | { kind: 'modifier-only' }>
) => {
  const key = fieldKey(optionName, field.name)
  if (result.kind === 'combo') {
    // 修饰键个数不符也先记下：由 isInvalid 标红并拦住保存，改对或「恢复」即解除
    delete errors[key]
    setValue(optionName, field.name, formatHotkey(result.keys))
    return
  }
  // 录不出键（不支持的键、超过两个修饰键）：值不变，框变红 + 行下提示
  errors[key] =
    result.kind === 'too-many-modifiers'
      ? t('edit.mfwHotkeyTooManyModifiers')
      : t('edit.mfwHotkeyUnsupported')
}

// 「选择其他目录」读到的候选：这次弹窗里有效，关掉再开回到默认目录
const pickedImport = ref<{ dir: string; candidates: MaaFWHotkeyImportCandidate[] } | null>(null)
watch(
  () => props.open,
  value => {
    if (value) pickedImport.value = null
  }
)
const shownCandidates = computed(() => pickedImport.value?.candidates ?? props.importCandidates)
const shownDir = computed(() => pickedImport.value?.dir ?? props.importDir)

const { pickShellInstanceDirectory } = useMaaFWShellInstanceApi()
const pickImportDirectory = async () => {
  let picked: Awaited<ReturnType<typeof pickShellInstanceDirectory>>
  try {
    picked = await pickShellInstanceDirectory(props.scriptId)
  } catch (error) {
    message.error(error instanceof Error ? error.message : String(error))
    return
  }
  if (!picked) return
  const { dir } = picked
  const candidates = collectHotkeyImportCandidates(picked.instances, props.options)
  if (candidates.length === 0) {
    message.warning(t('edit.mfwHotkeyImportNoConfig'))
    return
  }
  pickedImport.value = { dir, candidates }
  // 只有一份就直接填；几份不同的留在「从项目导入」下拉里让用户挑
  if (candidates.length === 1) applyImport(candidates[0])
  else message.info(t('edit.mfwHotkeyImportPickOne', { n: candidates.length }))
}

// 从项目导入：只填草稿，点「保存」才写；与默认相同 / 不同 / 修饰键个数不符照常显示
const applyImport = (candidate: MaaFWHotkeyImportCandidate) => {
  const { values, applied, skipped } = importHotkeyValues(props.options, candidate.hotkeys)
  for (const [optionName, fields] of Object.entries(values)) {
    for (const [fieldName, value] of Object.entries(fields)) {
      setValue(optionName, fieldName, value)
      delete errors[fieldKey(optionName, fieldName)]
    }
  }
  const text = t('edit.mfwHotkeyImported', { n: applied })
  if (skipped > 0) message.warning(text + t('edit.mfwHotkeyImportSkipped', { m: skipped }))
  else message.success(text)
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

.hotkey-modal-combo {
  padding: 0 0 4px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}

.hotkey-modal-combo.is-error {
  color: var(--ant-color-error);
}

.hotkey-modal-list {
  height: 440px;
  max-height: calc(100vh - 340px);
  margin-right: -12px;
  padding-right: 12px;
  overflow-y: auto;
  scrollbar-gutter: stable;
}

.hotkey-combo-tag {
  margin-left: 6px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
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

.hotkey-footer-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.hotkey-reset-all {
  padding: 0;
}

.hotkey-import-tag {
  margin-inline: 8px 0;
}
</style>
