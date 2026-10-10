<template>
  <div class="maafw-option-editor">
    <div v-if="showOptionToolbar" class="option-toolbar">
      <a-input
        v-model:value="optionSearchQuery"
        allow-clear
        :placeholder="t('edit.searchSettings')"
        class="option-search"
      />
    </div>

    <a-empty
      v-if="filteredOptions.length === 0"
      class="option-empty"
      :description="
        optionSearchQuery ? t('edit.maafwNoMatchingSettings') : t('edit.maafwNoConfigurableOptions')
      "
    />

    <!-- 按项目在 interface 里声明的顺序平铺，不按控件类型重新分组 -->
    <template v-else>
      <div v-for="option in filteredOptions" :key="option.name" class="option-item">
        <div class="option-label">
          <img
            v-if="resolveMaaFWAssetUrl(option.icon)"
            :src="resolveMaaFWAssetUrl(option.icon)"
            alt=""
            width="18"
            height="18"
            class="option-icon"
            @error="hideBrokenMaaFWIcon"
            @load="showLoadedMaaFWIcon"
          />
          <span>{{ getOptionLabel(option) }}</span>
          <a-tooltip v-if="option.description" :title="option.description">
            <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
          </a-tooltip>
        </div>

        <a-radio-group
          v-if="option.type === 'switch'"
          :value="getStringValue(option)"
          :disabled="props.disabled"
          class="option-radio-group"
          @change="handleChoiceChange(option.name, $event)"
        >
          <a-radio
            v-for="caseItem in getDisplayCases(option)"
            :key="caseItem.name"
            :value="caseItem.name"
          >
            {{ getCaseLabel(caseItem) }}
          </a-radio>
        </a-radio-group>

        <a-select
          v-else-if="option.type === 'select' || option.type === 'scan_select'"
          :value="getStringValue(option)"
          :disabled="props.disabled"
          class="option-control"
          :placeholder="t('edit.pleaseChoose')"
          @change="handleSelectChange(option.name, $event)"
        >
          <a-select-option
            v-for="caseItem in option.cases"
            :key="caseItem.name"
            :value="caseItem.name"
          >
            {{ getCaseLabel(caseItem) }}
          </a-select-option>
        </a-select>

        <a-checkbox-group
          v-else-if="option.type === 'checkbox'"
          :value="getStringListValue(option)"
          :disabled="props.disabled"
          class="option-checkbox-group"
          @change="handleCheckboxChange(option.name, $event)"
        >
          <a-checkbox
            v-for="caseItem in option.cases"
            :key="caseItem.name"
            :value="caseItem.name"
            :disabled="isCheckboxCaseLocked(option, getStringListValue(option), caseItem.name)"
          >
            {{ getCaseLabel(caseItem) }}
          </a-checkbox>
        </a-checkbox-group>

        <div v-else-if="option.type === 'input'" class="input-group">
          <!-- 带说明的字段占满整行：说明跟着选项区宽度排，别挤在半栏里 -->
          <a-form-item
            v-for="inputItem in option.inputs"
            :key="inputItem.name"
            class="input-form-item"
            :class="{ 'input-form-item-wide': Boolean(inputItem.description) }"
          >
            <template #label>
              <span class="input-label">
                <img
                  v-if="resolveMaaFWAssetUrl(inputItem.icon)"
                  :src="resolveMaaFWAssetUrl(inputItem.icon)"
                  alt=""
                  width="18"
                  height="18"
                  class="input-icon"
                  @error="hideBrokenMaaFWIcon"
                  @load="showLoadedMaaFWIcon"
                />
                <span>{{ getInputLabel(inputItem) }}</span>
              </span>
            </template>
            <div v-if="isPasswordInput(inputItem)" class="password-field">
              <!-- 草稿只存在本组件里：已保存的值只有密文，不回显，失焦 / 回车才提交 -->
              <a-input-password
                :value="getPasswordDraft(option.name, inputItem.name)"
                :disabled="props.disabled"
                :placeholder="getPasswordPlaceholder(option, inputItem)"
                autocomplete="new-password"
                class="option-control"
                @update:value="setPasswordDraft(option.name, inputItem.name, $event)"
                @blur="commitPasswordDraft(option.name, inputItem)"
                @press-enter="commitPasswordDraft(option.name, inputItem)"
              />
              <a-button
                v-if="hasStoredSecret(getStoredInputText(option, inputItem.name))"
                type="link"
                size="small"
                :disabled="props.disabled"
                @click="clearPassword(option.name, inputItem)"
              >
                {{ t('edit.maafwPasswordClear') }}
              </a-button>
            </div>
            <!-- 数字与文本字段都先改草稿，失焦 / 回车时校验通过才提交（不是每敲一个字存一次）；
                 数字字段空着时按项目默认值显示，与运行器的回落一致 -->
            <a-input-number
              v-else-if="isIntegerInput(inputItem)"
              :value="getNumberInputValue(option, inputItem)"
              :precision="0"
              :disabled="props.disabled"
              class="option-control"
              @change="setInputDraft(option.name, inputItem.name, $event)"
              @blur="commitInputDraft(option.name, inputItem)"
              @press-enter="commitInputDraft(option.name, inputItem)"
            />
            <a-input-number
              v-else-if="isDecimalInput(inputItem)"
              :value="getNumberInputValue(option, inputItem)"
              :disabled="props.disabled"
              class="option-control"
              @change="setInputDraft(option.name, inputItem.name, $event)"
              @blur="commitInputDraft(option.name, inputItem)"
              @press-enter="commitInputDraft(option.name, inputItem)"
            />
            <a-switch
              v-else-if="isBooleanInput(inputItem)"
              :checked="getBooleanInputValue(option, inputItem)"
              :disabled="props.disabled"
              :checked-children="t('edit.yes')"
              :un-checked-children="t('edit.no')"
              @change="handleInputBooleanChange(option.name, inputItem, $event)"
            />
            <a-input
              v-else
              :value="getTextInputValue(option, inputItem)"
              :disabled="props.disabled"
              :placeholder="inputItem.default || inputItem.description || inputItem.name"
              class="option-control"
              @update:value="setInputDraft(option.name, inputItem.name, $event)"
              @blur="commitInputDraft(option.name, inputItem)"
              @press-enter="commitInputDraft(option.name, inputItem)"
            />
            <MaaFWDescriptionView
              v-if="inputItem.description"
              :content="inputItem.description"
              :base-path="basePath"
              class="input-description"
            />
          </a-form-item>
        </div>

        <a-alert
          v-else
          type="warning"
          show-icon
          :message="
            t('edit.maafwUnsupportedOptionType', { type: option.type || t('edit.unknownType') })
          "
        />

        <div
          v-if="getCheckboxCountHint(option)"
          class="option-count-hint"
          :class="{ 'option-count-hint--warning': getCheckboxCountHint(option)?.warning }"
        >
          {{ getCheckboxCountHint(option)?.text }}
        </div>

        <MaaFWDescriptionView
          v-if="option.description"
          :content="option.description"
          :base-path="basePath"
          class="option-description"
        />

        <div
          v-for="nestedOptionNames in getActiveNestedOptionGroups(option)"
          :key="`${option.name}:${nestedOptionNames.join('|')}`"
          class="sub-options"
        >
          <MaaFWTaskOptionEditor
            :option-names="nestedOptionNames"
            :options="options"
            :task-options="taskOptions"
            :controller-name="controllerName"
            :resource-name="resourceName"
            :base-path="basePath"
            :lineage="[...lineage, option.name]"
            :disabled="props.disabled"
            :hide-toolbar="true"
            @update="emit('update', $event)"
          />
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import { buildMaaFWAssetUrl } from '@/composables/useMaaFWApi'
import MaaFWDescriptionView from './MaaFWDescriptionView.vue'
import {
  getCheckboxCountState,
  hasStoredSecret,
  isCheckboxCaseLocked,
  isPasswordInput,
} from './maafwOptionConstraints'
import {
  activeMaaFWNestedOptionGroups,
  effectiveMaaFWInputFieldValue,
  isMaaFWBooleanInput,
  isMaaFWDecimalInput,
  isMaaFWIntegerInput,
  isMaaFWOptionActiveFor,
  isMaaFWTruthyInputText,
  maafwInputFallbackDefault,
  resolveMaaFWCheckboxValue,
  resolveMaaFWChoiceValue,
  storedMaaFWInputFieldValue,
} from './maafwOptionValues'
import { hideBrokenMaaFWIcon, showLoadedMaaFWIcon } from './maafwIconImage'
import type {
  MaaFWOptionCaseInfo,
  MaaFWOptionInfo,
  MaaFWOptionInputInfo,
  MaaFWTaskOptionValue,
} from '@/types/script'

const { t } = useI18n()

defineOptions({
  name: 'MaaFWTaskOptionEditor',
})

const props = withDefaults(
  defineProps<{
    optionNames: string[]
    options: MaaFWOptionInfo[]
    taskOptions: Record<string, MaaFWTaskOptionValue>
    controllerName?: string
    resourceName?: string
    basePath?: string
    lineage?: string[]
    disabled?: boolean
    hideToolbar?: boolean
  }>(),
  {
    controllerName: '',
    resourceName: '',
    basePath: '',
    lineage: () => [],
    disabled: false,
    hideToolbar: false,
  }
)

const emit = defineEmits<{
  update: [payload: { optionName: string; value: MaaFWTaskOptionValue }]
}>()

type ChoiceChangeEvent = {
  target?: {
    value?: unknown
  }
}

const optionSearchQuery = ref('')
// 密码字段正在输入、还没提交的值，键为 `option\u0000字段`。换了任务（taskOptions 换了一份）就清空。
const passwordDrafts = ref<Record<string, string>>({})
// 数字 / 文本字段正在输入、还没提交的值，键同上；失焦 / 回车时提交，换了任务同样清空。
const inputDrafts = ref<Record<string, string>>({})

const optionMap = computed(() => {
  const entries = props.options.map(option => [option.name, option] as const)
  return new Map<string, MaaFWOptionInfo>(entries)
})

const isOptionActive = (option: MaaFWOptionInfo) =>
  isMaaFWOptionActiveFor(option, props.controllerName, props.resourceName)

const visibleOptions = computed(() => {
  const seen = new Set<string>()
  const result: MaaFWOptionInfo[] = []
  for (const optionName of props.optionNames) {
    if (seen.has(optionName) || props.lineage.includes(optionName)) continue
    seen.add(optionName)

    const option = optionMap.value.get(optionName)
    // Hotkeys are game key bindings shared by every user of the script: they
    // are configured once on the script page (Win32 only, Game.Hotkeys) and
    // overlaid at run time, so the per-task editor leaves them out.
    if (!option || option.type === 'hotkey' || !isOptionActive(option)) continue
    result.push(option)
  }
  return result
})

const filteredOptions = computed(() => {
  const keyword = optionSearchQuery.value.trim().toLowerCase()
  // 搜索框不显示时（子选项、选项不多的任务）不按残留的搜索词过滤
  if (!keyword || props.hideToolbar || visibleOptions.value.length <= 5) {
    return visibleOptions.value
  }
  return visibleOptions.value.filter(option => {
    return [option.name, option.label, option.description]
      .filter((item): item is string => typeof item === 'string')
      .some(item => item.toLowerCase().includes(keyword))
  })
})

const showOptionToolbar = computed(() => !props.hideToolbar && visibleOptions.value.length > 5)

watch(
  () => props.taskOptions,
  () => {
    passwordDrafts.value = {}
    inputDrafts.value = {}
  }
)

const getOptionLabel = (option: MaaFWOptionInfo) => option.label || option.name

const getCaseLabel = (caseItem: MaaFWOptionCaseInfo) => caseItem.label || caseItem.name

const getInputLabel = (inputItem: MaaFWOptionInputInfo) => inputItem.label || inputItem.name

const resolveMaaFWAssetUrl = (rawPath?: string | null) => {
  return buildMaaFWAssetUrl(props.basePath, rawPath)
}

const isIntegerInput = isMaaFWIntegerInput
const isDecimalInput = isMaaFWDecimalInput
const isBooleanInput = isMaaFWBooleanInput

const getDisplayCases = (option: MaaFWOptionInfo) => {
  const cases = [...option.cases]
  const hasYesNo = cases.some(caseItem => ['Yes', 'No', '是', '否'].includes(caseItem.name))
  if (!hasYesNo) return cases

  return cases.sort((left, right) => {
    const leftIsYes = left.name === 'Yes' || left.name === '是'
    const rightIsYes = right.name === 'Yes' || right.name === '是'
    if (leftIsYes && !rightIsYes) return -1
    if (!leftIsYes && rightIsYes) return 1
    return 0
  })
}

// 显示的值与运行器同一口径（maafwOptionValues）：单选存的 case 已失效时按默认 case，
// 数字 / 布尔字段空着时按项目默认值
const getStoredValue = (option: MaaFWOptionInfo): MaaFWTaskOptionValue | undefined =>
  props.taskOptions[option.name]

const getStringValue = (option: MaaFWOptionInfo) =>
  resolveMaaFWChoiceValue(option, getStoredValue(option))

const getStringListValue = (option: MaaFWOptionInfo) =>
  resolveMaaFWCheckboxValue(option, getStoredValue(option))

const getInputValueObject = (option: MaaFWOptionInfo): Record<string, string> => {
  const value = getStoredValue(option)
  if (value && !Array.isArray(value) && typeof value === 'object') return value
  return {}
}

const getStoredInputText = (option: MaaFWOptionInfo, inputName: string) =>
  storedMaaFWInputFieldValue(getStoredValue(option), inputName)

const inputDraftKey = (optionName: string, inputName: string) => `${optionName}\u0000${inputName}`

const getNumberInputValue = (option: MaaFWOptionInfo, inputItem: MaaFWOptionInputInfo) => {
  const draft = inputDrafts.value[inputDraftKey(option.name, inputItem.name)]
  const rawValue = (
    draft ?? effectiveMaaFWInputFieldValue(inputItem, getStoredValue(option))
  ).trim()
  if (!rawValue) return undefined

  const value = Number(rawValue)
  return Number.isFinite(value) ? value : undefined
}

const getBooleanInputValue = (option: MaaFWOptionInfo, inputItem: MaaFWOptionInputInfo) =>
  isMaaFWTruthyInputText(effectiveMaaFWInputFieldValue(inputItem, getStoredValue(option)))

const getTextInputValue = (option: MaaFWOptionInfo, inputItem: MaaFWOptionInputInfo) =>
  inputDrafts.value[inputDraftKey(option.name, inputItem.name)] ??
  getStoredInputText(option, inputItem.name)

const emitOptionValue = (optionName: string, value: MaaFWTaskOptionValue) => {
  emit('update', { optionName, value })
}

const validateInputValue = (inputItem: MaaFWOptionInputInfo, value: string) => {
  const trimmedValue = value.trim()
  if (!trimmedValue) {
    // 空值：字符串字段就是空；数字字段运行时按项目默认值跑，没有默认值才算没填
    const hasFallback = maafwInputFallbackDefault(inputItem) !== null
    if (isIntegerInput(inputItem) && !hasFallback) {
      message.error(t('edit.enterWholeNumber'))
      return false
    }
    if (isDecimalInput(inputItem) && !hasFallback) {
      message.error(t('edit.enterNumber'))
      return false
    }
    return true
  }
  if (isIntegerInput(inputItem) && !/^-?\d+$/.test(trimmedValue)) {
    message.error(t('edit.enterWholeNumber'))
    return false
  }
  if (isDecimalInput(inputItem) && !Number.isFinite(Number(trimmedValue))) {
    message.error(t('edit.enterNumber'))
    return false
  }

  if (!inputItem.verify) return true

  try {
    const regexp = new RegExp(inputItem.verify)
    if (regexp.test(value)) return true
  } catch {
    message.error(t('edit.validationPatternInvalidP0', { p0: inputItem.name }))
    return false
  }

  message.error(inputItem.verifyError || inputItem.patternMsg || t('edit.maafwInputVerifyFailed'))
  return false
}

const normalizeCheckboxValue = (value: unknown) => {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string')
    : []
}

const handleChoiceChange = (optionName: string, event: ChoiceChangeEvent) => {
  const value = event.target?.value
  emitOptionValue(optionName, typeof value === 'string' ? value : '')
}

const handleSelectChange = (optionName: string, value: unknown) => {
  emitOptionValue(optionName, value === null || value === undefined ? '' : String(value))
}

const handleCheckboxChange = (optionName: string, value: unknown) => {
  emitOptionValue(optionName, normalizeCheckboxValue(value))
}

const handleInputFieldChange = (
  optionName: string,
  inputItem: MaaFWOptionInputInfo,
  value: string | number | boolean | null,
  shouldValidate = true
) => {
  const option = optionMap.value.get(optionName)
  if (!option) return
  const inputValue = value === null ? '' : String(value)
  if (shouldValidate && !validateInputValue(inputItem, inputValue)) return

  emitOptionValue(optionName, {
    ...getInputValueObject(option),
    [inputItem.name]: inputValue,
  })
}

const handleInputBooleanChange = (
  optionName: string,
  inputItem: MaaFWOptionInputInfo,
  checked: unknown
) => {
  handleInputFieldChange(optionName, inputItem, Boolean(checked))
}

// a-input-number 清空时给 null：草稿记成空串，提交时按「用项目默认值」处理
const setInputDraft = (optionName: string, inputName: string, value: unknown) => {
  inputDrafts.value = {
    ...inputDrafts.value,
    [inputDraftKey(optionName, inputName)]:
      typeof value === 'string' || typeof value === 'number' ? String(value) : '',
  }
}

const dropInputDraft = (key: string) => {
  const next = { ...inputDrafts.value }
  delete next[key]
  inputDrafts.value = next
}

// 失焦 / 回车时提交：没改就不存；校验不过弹提示、草稿留在框里等用户改，不把不合规的值存进去
const commitInputDraft = (optionName: string, inputItem: MaaFWOptionInputInfo) => {
  const key = inputDraftKey(optionName, inputItem.name)
  const draft = inputDrafts.value[key]
  if (draft === undefined) return
  const option = optionMap.value.get(optionName)
  if (!option) return
  if (draft === getStoredInputText(option, inputItem.name)) {
    dropInputDraft(key)
    return
  }
  if (!validateInputValue(inputItem, draft)) return
  dropInputDraft(key)
  handleInputFieldChange(optionName, inputItem, draft, false)
}

const passwordDraftKey = inputDraftKey

const getPasswordDraft = (optionName: string, inputName: string) =>
  passwordDrafts.value[passwordDraftKey(optionName, inputName)] ?? ''

const setPasswordDraft = (optionName: string, inputName: string, value: unknown) => {
  passwordDrafts.value = {
    ...passwordDrafts.value,
    [passwordDraftKey(optionName, inputName)]: typeof value === 'string' ? value : '',
  }
}

const dropPasswordDraft = (key: string) => {
  const next = { ...passwordDrafts.value }
  delete next[key]
  passwordDrafts.value = next
}

const getPasswordPlaceholder = (option: MaaFWOptionInfo, inputItem: MaaFWOptionInputInfo) =>
  hasStoredSecret(getStoredInputText(option, inputItem.name))
    ? t('edit.maafwPasswordSaved')
    : inputItem.description || inputItem.name

// 只在失焦 / 回车时提交：留空表示不改（已保存的值只有密文，不能拿来回填）；
// 校验不过就把草稿留在框里等用户改。提交的是明文，后端落盘前加密。
const commitPasswordDraft = (optionName: string, inputItem: MaaFWOptionInputInfo) => {
  const key = passwordDraftKey(optionName, inputItem.name)
  const draft = passwordDrafts.value[key]
  if (!draft) return
  if (!validateInputValue(inputItem, draft)) return
  dropPasswordDraft(key)
  handleInputFieldChange(optionName, inputItem, draft, false)
}

const clearPassword = (optionName: string, inputItem: MaaFWOptionInputInfo) => {
  dropPasswordDraft(passwordDraftKey(optionName, inputItem.name))
  handleInputFieldChange(optionName, inputItem, '', false)
}

const getCheckboxCountHint = (option: MaaFWOptionInfo) => {
  const state = getCheckboxCountState(option, getStringListValue(option))
  if (!state) return null
  let text: string
  if (state.max === null) {
    text = t('edit.maafwCheckboxCountMin', { min: state.min })
  } else if (state.min === 0) {
    text = t('edit.maafwCheckboxCountMax', { max: state.max })
  } else if (state.min === state.max) {
    text = t('edit.maafwCheckboxCountExact', { count: state.min })
  } else {
    text = t('edit.maafwCheckboxCountRange', { min: state.min, max: state.max })
  }
  if (state.violation) {
    text += t('edit.maafwCheckboxCountCurrent', { count: state.count })
  }
  return { text, warning: state.violation !== null }
}

const getActiveNestedOptionGroups = (option: MaaFWOptionInfo) =>
  activeMaaFWNestedOptionGroups(option, getStoredValue(option))
</script>

<style scoped>
.maafw-option-editor {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.option-empty {
  padding: 24px;
  border: 1px dashed var(--ant-color-border);
  border-radius: 8px;
}

.option-toolbar {
  display: flex;
  justify-content: flex-end;
}

.option-search {
  max-width: 280px;
}

.option-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.option-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.option-icon,
.input-icon {
  width: 18px;
  height: 18px;
  object-fit: contain;
  flex: 0 0 auto;
}

.option-description,
.input-description {
  color: var(--ant-color-text-secondary);
}

.input-description {
  margin-top: 8px;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  font-size: 13px;
}

.option-control {
  width: 100%;
}

.option-radio-group,
.option-checkbox-group {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
}

.input-group {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px 16px;
}

.input-form-item {
  margin-bottom: 0;
}

.input-form-item-wide {
  grid-column: 1 / -1;
}

.password-field {
  display: flex;
  align-items: center;
  gap: 8px;
}

.option-count-hint {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.option-count-hint--warning {
  color: var(--ant-color-warning);
}

.input-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.sub-options {
  margin-top: 4px;
  margin-left: 16px;
  padding-left: 16px;
  border-left: 2px solid var(--ant-color-border-secondary);
}

@media (max-width: 768px) {
  .option-toolbar {
    justify-content: stretch;
  }

  .option-search {
    max-width: none;
  }

  .input-group {
    grid-template-columns: 1fr;
  }
}
</style>
