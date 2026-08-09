<template>
  <div class="maafw-option-editor">
    <div v-if="showOptionToolbar" class="option-toolbar">
      <a-input
        v-model:value="optionSearchQuery"
        allow-clear
        placeholder="搜索配置项…"
        class="option-search"
      />
    </div>

    <a-empty
      v-if="filteredOptions.length === 0"
      class="option-empty"
      :description="optionSearchQuery ? '没有匹配的配置项' : '当前任务没有可配置项'"
    />

    <a-collapse
      v-else-if="shouldGroupOptions"
      v-model:active-key="activeOptionGroupKeys"
      class="option-group-collapse"
    >
      <a-collapse-panel v-for="group in optionGroups" :key="group.key" :header="group.label">
        <MaaFWTaskOptionEditor
          :option-names="group.optionNames"
          :options="options"
          :task-options="taskOptions"
          :controller-name="controllerName"
          :resource-name="resourceName"
          :base-path="basePath"
          :lineage="lineage"
          :disabled="props.disabled"
          :hide-toolbar="true"
          @update="emit('update', $event)"
        />
      </a-collapse-panel>
    </a-collapse>

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
          placeholder="请选择"
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
          <a-checkbox v-for="caseItem in option.cases" :key="caseItem.name" :value="caseItem.name">
            {{ getCaseLabel(caseItem) }}
          </a-checkbox>
        </a-checkbox-group>

        <div v-else-if="option.type === 'input'" class="input-group">
          <a-form-item
            v-for="inputItem in option.inputs"
            :key="inputItem.name"
            class="input-form-item"
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
                />
                <span>{{ getInputLabel(inputItem) }}</span>
              </span>
            </template>
            <a-input-number
              v-if="isIntegerInput(inputItem)"
              :value="getNumberInputValue(option, inputItem.name)"
              :precision="0"
              :disabled="props.disabled"
              class="option-control"
              @change="handleInputNumberChange(option.name, inputItem, $event)"
            />
            <a-input-number
              v-else-if="isDecimalInput(inputItem)"
              :value="getNumberInputValue(option, inputItem.name)"
              :disabled="props.disabled"
              class="option-control"
              @change="handleInputNumberChange(option.name, inputItem, $event)"
            />
            <a-switch
              v-else-if="isBooleanInput(inputItem)"
              :checked="getBooleanInputValue(option, inputItem.name)"
              :disabled="props.disabled"
              checked-children="是"
              un-checked-children="否"
              @change="handleInputBooleanChange(option.name, inputItem, $event)"
            />
            <a-input
              v-else
              :value="getInputFieldValue(option, inputItem.name)"
              :disabled="props.disabled"
              :placeholder="inputItem.description || inputItem.name"
              class="option-control"
              @change="handleInputTextChange(option.name, inputItem, $event)"
              @blur="handleInputTextBlur(inputItem, $event)"
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
          :message="`不支持的配置项类型：${option.type || '未知'}，请联系脚本作者或升级 AUTO-MAS`"
        />

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
import { computed, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import { buildMaaFWAssetUrl } from '@/composables/useMaaFWApi'
import MaaFWDescriptionView from './MaaFWDescriptionView.vue'
import type {
  MaaFWOptionCaseInfo,
  MaaFWOptionInfo,
  MaaFWOptionInputInfo,
  MaaFWTaskOptionValue,
} from '@/types/script'

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

type InputChangeEvent = Event & {
  target: HTMLInputElement
}

type ChoiceChangeEvent = {
  target?: {
    value?: unknown
  }
}

type OptionGroup = {
  key: string
  label: string
  optionNames: string[]
}

const optionSearchQuery = ref('')
const activeOptionGroupKeys = ref<string[]>([])

const optionMap = computed(() => {
  const entries = props.options.map(option => [option.name, option] as const)
  return new Map<string, MaaFWOptionInfo>(entries)
})

const isOptionActive = (option: MaaFWOptionInfo) => {
  if (option.controller.length > 0 && !option.controller.includes(props.controllerName)) {
    return false
  }
  if (option.resource.length > 0 && !option.resource.includes(props.resourceName)) {
    return false
  }
  return true
}

const visibleOptions = computed(() => {
  const seen = new Set<string>()
  const result: MaaFWOptionInfo[] = []
  for (const optionName of props.optionNames) {
    if (seen.has(optionName) || props.lineage.includes(optionName)) continue
    seen.add(optionName)

    const option = optionMap.value.get(optionName)
    // Hotkeys are owned by the MaaFW project itself. MAS does not capture or
    // persist them, so omit them from the editor instead of implying support.
    if (!option || option.type === 'hotkey' || !isOptionActive(option)) continue
    result.push(option)
  }
  return result
})

const filteredOptions = computed(() => {
  const keyword = optionSearchQuery.value.trim().toLowerCase()
  if (!keyword) return visibleOptions.value
  return visibleOptions.value.filter(option => {
    return [option.name, option.label, option.description]
      .filter((item): item is string => typeof item === 'string')
      .some(item => item.toLowerCase().includes(keyword))
  })
})

const optionTypeLabels: Record<string, string> = {
  switch: '开关选项',
  select: '单选选项',
  scan_select: '扫描选择',
  checkbox: '多选选项',
  input: '输入选项',
}

const optionGroups = computed<OptionGroup[]>(() => {
  const groups = new Map<string, OptionGroup>()
  for (const option of filteredOptions.value) {
    const key = option.type || 'unknown'
    const group = groups.get(key) || {
      key,
      label: optionTypeLabels[key] || `其他选项：${key}`,
      optionNames: [],
    }
    group.optionNames.push(option.name)
    groups.set(key, group)
  }
  return Array.from(groups.values())
})

const showOptionToolbar = computed(() => !props.hideToolbar && visibleOptions.value.length > 5)
const shouldGroupOptions = computed(
  () => !props.hideToolbar && filteredOptions.value.length > 5 && optionGroups.value.length > 1
)

watch(
  optionGroups,
  groups => {
    activeOptionGroupKeys.value = groups.map(group => group.key)
  },
  { immediate: true }
)

const getOptionLabel = (option: MaaFWOptionInfo) => option.label || option.name

const getCaseLabel = (caseItem: MaaFWOptionCaseInfo) => caseItem.label || caseItem.name

const getInputLabel = (inputItem: MaaFWOptionInputInfo) => inputItem.label || inputItem.name

const resolveMaaFWAssetUrl = (rawPath?: string | null) => {
  return buildMaaFWAssetUrl(props.basePath, rawPath)
}

const normalizePipelineType = (inputItem: MaaFWOptionInputInfo) =>
  (inputItem.pipelineType || 'string').toLowerCase()

const isIntegerInput = (inputItem: MaaFWOptionInputInfo) =>
  ['int', 'integer'].includes(normalizePipelineType(inputItem))

const isDecimalInput = (inputItem: MaaFWOptionInputInfo) =>
  ['float', 'double', 'number'].includes(normalizePipelineType(inputItem))

const isBooleanInput = (inputItem: MaaFWOptionInputInfo) =>
  ['bool', 'boolean'].includes(normalizePipelineType(inputItem))

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

const getDefaultValue = (option: MaaFWOptionInfo): MaaFWTaskOptionValue => {
  if (['select', 'scan_select', 'switch'].includes(option.type)) {
    if (typeof option.defaultCase === 'string') return option.defaultCase
    return option.cases[0]?.name || ''
  }

  if (option.type === 'checkbox') {
    if (!Array.isArray(option.defaultCase)) return []
    const caseNames = new Set(option.cases.map(caseItem => caseItem.name))
    return option.defaultCase.filter(caseName => caseNames.has(caseName))
  }

  if (option.type === 'input') {
    const inputValues: Record<string, string> = {}
    for (const inputItem of option.inputs) {
      inputValues[inputItem.name] = inputItem.default || ''
    }
    return inputValues
  }

  return ''
}

const getStoredValue = (option: MaaFWOptionInfo): MaaFWTaskOptionValue => {
  return props.taskOptions[option.name] ?? getDefaultValue(option)
}

const getStringValue = (option: MaaFWOptionInfo) => {
  const value = getStoredValue(option)
  if (typeof value === 'string') return value
  const defaultValue = getDefaultValue(option)
  return typeof defaultValue === 'string' ? defaultValue : ''
}

const getStringListValue = (option: MaaFWOptionInfo) => {
  const value = getStoredValue(option)
  if (Array.isArray(value)) return value
  return []
}

const getInputValueObject = (option: MaaFWOptionInfo) => {
  const value = getStoredValue(option)
  if (!Array.isArray(value) && typeof value === 'object') return value
  return {}
}

const getInputFieldValue = (option: MaaFWOptionInfo, inputName: string) => {
  return getInputValueObject(option)[inputName] || ''
}

const getNumberInputValue = (option: MaaFWOptionInfo, inputName: string) => {
  const rawValue = getInputFieldValue(option, inputName).trim()
  if (!rawValue) return undefined

  const value = Number(rawValue)
  return Number.isFinite(value) ? value : undefined
}

const getBooleanInputValue = (option: MaaFWOptionInfo, inputName: string) => {
  return ['true', '1', 'yes', 'y', 'on'].includes(
    getInputFieldValue(option, inputName).toLowerCase()
  )
}

const emitOptionValue = (optionName: string, value: MaaFWTaskOptionValue) => {
  emit('update', { optionName, value })
}

const validateInputValue = (inputItem: MaaFWOptionInputInfo, value: string) => {
  const trimmedValue = value.trim()
  if (isIntegerInput(inputItem) && !/^-?\d+$/.test(trimmedValue)) {
    message.error('请输入整数')
    return false
  }
  if (isDecimalInput(inputItem) && (!trimmedValue || !Number.isFinite(Number(trimmedValue)))) {
    message.error('请输入数字')
    return false
  }

  if (!inputItem.verify) return true

  try {
    const regexp = new RegExp(inputItem.verify)
    if (regexp.test(value)) return true
  } catch {
    message.error(`输入校验正则无效：${inputItem.name}`)
    return false
  }

  message.error(inputItem.verifyError || inputItem.patternMsg || '输入不符合脚本要求')
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

const handleInputNumberChange = (
  optionName: string,
  inputItem: MaaFWOptionInputInfo,
  value: unknown
) => {
  if (typeof value === 'string' || typeof value === 'number' || value === null) {
    handleInputFieldChange(optionName, inputItem, value)
  }
}

const handleInputBooleanChange = (
  optionName: string,
  inputItem: MaaFWOptionInputInfo,
  checked: unknown
) => {
  handleInputFieldChange(optionName, inputItem, Boolean(checked))
}

const handleInputTextChange = (
  optionName: string,
  inputItem: MaaFWOptionInputInfo,
  event: InputChangeEvent
) => {
  handleInputFieldChange(optionName, inputItem, event.target.value, false)
}

const handleInputTextBlur = (inputItem: MaaFWOptionInputInfo, event: InputChangeEvent) => {
  validateInputValue(inputItem, event.target.value)
}

const getActiveNestedOptionGroups = (option: MaaFWOptionInfo) => {
  if (!['select', 'scan_select', 'switch', 'checkbox'].includes(option.type)) return []

  if (option.type === 'checkbox') {
    const selectedCaseNames = new Set(getStringListValue(option))
    return option.cases
      .filter(caseItem => selectedCaseNames.has(caseItem.name) && caseItem.option.length > 0)
      .map(caseItem => caseItem.option)
  }

  const selectedCaseName = getStringValue(option)
  const selectedCase = option.cases.find(caseItem => caseItem.name === selectedCaseName)
  return selectedCase?.option.length ? [selectedCase.option] : []
}
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

.option-group-collapse {
  background: transparent;
}

.option-group-collapse :deep(.ant-collapse-content-box) {
  display: flex;
  flex-direction: column;
  gap: 16px;
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
