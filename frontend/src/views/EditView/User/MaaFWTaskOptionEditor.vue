<template>
  <div class="maafw-option-editor">
    <div v-if="showOptionToolbar" class="option-toolbar">
      <a-input
        v-model:value="optionSearchQuery"
        allow-clear
        :placeholder="t('core.edit.searchSettings')"
        class="option-search"
      />
    </div>

    <NoData
      v-if="filteredOptions.length === 0"
      class="option-empty"
      :description="
        optionSearchQuery
          ? t('core.edit.maafwNoMatchingSettings')
          : t('core.edit.maafwNoConfigurableOptions')
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
            <MaaFWOptionCaseLabel :case-item="caseItem" :base-path="basePath" />
          </a-radio>
        </a-radio-group>

        <a-select
          v-else-if="option.type === 'select' || option.type === 'scan_select'"
          :value="getStringValue(option)"
          :disabled="props.disabled"
          class="option-control"
          :placeholder="t('core.edit.pleaseChoose')"
          @change="handleSelectChange(option.name, $event)"
        >
          <a-select-option
            v-for="caseItem in option.cases"
            :key="caseItem.name"
            :value="caseItem.name"
          >
            <MaaFWOptionCaseLabel :case-item="caseItem" :base-path="basePath" />
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
            <MaaFWOptionCaseLabel :case-item="caseItem" :base-path="basePath" />
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
                {{ t('core.edit.maafwPasswordClear') }}
              </a-button>
            </div>
            <!-- 数字与文本字段都先改草稿，失焦 / 回车时校验通过才提交（不是每敲一个字存一次）；
                 没填的字段（含字符串）按项目默认值显示，与运行器的回落一致 -->
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
              :checked-children="t('core.edit.yes')"
              :un-checked-children="t('core.edit.no')"
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
            t('core.edit.maafwUnsupportedOptionType', {
              type: option.type || t('core.edit.unknownType'),
            })
          "
        />

        <!-- 勾选数要求、选中 case 的说明、选项说明 -->
        <MaaFWOptionNotes :option="option" :value="getStoredValue(option)" :base-path="basePath" />

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
import { computed, inject, onBeforeUnmount, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { buildMaaFWAssetUrl } from '@/composables/useMaaFWApi'
import MaaFWDescriptionView from './MaaFWDescriptionView.vue'
import MaaFWOptionCaseLabel from './MaaFWOptionCaseLabel.vue'
import MaaFWOptionNotes from './MaaFWOptionNotes.vue'
import { hasStoredSecret, isCheckboxCaseLocked, isPasswordInput } from './maafwOptionConstraints'
import {
  activeMaaFWNestedOptionGroups,
  effectiveMaaFWInputFieldValue,
  isMaaFWBooleanInput,
  isMaaFWDecimalInput,
  isMaaFWIntegerInput,
  isMaaFWOptionActiveFor,
  isMaaFWTruthyInputText,
  checkMaaFWInputValue,
  resolveMaaFWCheckboxValue,
  resolveMaaFWChoiceValue,
  storedMaaFWInputFieldValue,
} from './maafwOptionValues'
import { hideBrokenMaaFWIcon, showLoadedMaaFWIcon } from './maafwIconImage'
import {
  MAAFW_OPTION_DRAFTS_KEY,
  maafwOptionDraftKey,
  parseMaaFWOptionDraftKey,
  retainMaaFWDraftsForUnchangedFields,
} from './maafwOptionDrafts'
import type { MaaFWOptionInfo, MaaFWOptionInputInfo, MaaFWTaskOptionValue } from '@/types/script'

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
// 密码字段正在输入、还没提交的值，键为 `option\u0000字段`。
const passwordDrafts = ref<Record<string, string>>({})
// 数字 / 文本字段正在输入、还没提交的值，键同上；失焦 / 回车时提交。
// 两种草稿在选项值换了一份时，只丢掉已存值确实变了的字段（见下面的 watch）。
const inputDrafts = ref<Record<string, string>>({})
// 页面离开前由页面统一提交草稿（不在用户页里时没有登记处）
const draftRegistry = inject(MAAFW_OPTION_DRAFTS_KEY, null)

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

// 保存后按后端结果重载（受管任务）、配置恢复都会换一份 taskOptions：正在输入的字段没被改动就留着草稿
watch(
  () => props.taskOptions,
  (next, previous) => {
    passwordDrafts.value = retainMaaFWDraftsForUnchangedFields(passwordDrafts.value, previous, next)
    inputDrafts.value = retainMaaFWDraftsForUnchangedFields(inputDrafts.value, previous, next)
  }
)

const getOptionLabel = (option: MaaFWOptionInfo) => option.label || option.name

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
// 输入字段没填时按项目默认值（字符串只认没存或空串，password 和特调声明的例外不回落）
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

const inputDraftKey = maafwOptionDraftKey

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

// 没填（存的是空串或没存）时显示项目 default，与运行器回落一致；清空提交存空串，下次仍显示 default
const getTextInputValue = (option: MaaFWOptionInfo, inputItem: MaaFWOptionInputInfo) =>
  inputDrafts.value[inputDraftKey(option.name, inputItem.name)] ??
  effectiveMaaFWInputFieldValue(inputItem, getStoredValue(option))

const emitOptionValue = (optionName: string, value: MaaFWTaskOptionValue) => {
  emit('update', { optionName, value })
}

// 判定在 checkMaaFWInputValue（字符串只有空串算没填，纯空白照常过 verify），这里只负责报错
const validateInputValue = (inputItem: MaaFWOptionInputInfo, value: string) => {
  const problem = checkMaaFWInputValue(inputItem, value)
  if (problem === null) return true
  if (problem === 'wholeNumber') {
    message.error(t('core.edit.enterWholeNumber'))
  } else if (problem === 'number') {
    message.error(t('core.edit.enterNumber'))
  } else if (problem === 'patternInvalid') {
    message.error(t('core.edit.validationPatternInvalidP0', { p0: inputItem.name }))
  } else {
    message.error(
      inputItem.verifyError || inputItem.patternMsg || t('core.edit.maafwInputVerifyFailed')
    )
  }
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

// 草稿和已存值相同、或和没填时显示的项目默认值相同，都算没改（没填的字段不因此被钉成 default）
const isInputDraftUnchanged = (option: MaaFWOptionInfo, inputName: string, draft: string) => {
  if (draft === getStoredInputText(option, inputName)) return true
  const inputItem = option.inputs.find(item => item.name === inputName)
  if (!inputItem) return false
  return draft === effectiveMaaFWInputFieldValue(inputItem, getStoredValue(option))
}

// 失焦 / 回车时提交：没改就不存；校验不过弹提示、草稿留在框里等用户改，不把不合规的值存进去
const commitInputDraft = (optionName: string, inputItem: MaaFWOptionInputInfo) => {
  const key = inputDraftKey(optionName, inputItem.name)
  const draft = inputDrafts.value[key]
  if (draft === undefined) return
  const option = optionMap.value.get(optionName)
  if (!option) return
  if (isInputDraftUnchanged(option, inputItem.name, draft)) {
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
    ? t('core.edit.maafwPasswordSaved')
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

const findInputItem = (optionName: string, inputName: string) =>
  optionMap.value.get(optionName)?.inputs.find(item => item.name === inputName)

// 和已存值不同的文本 / 数字草稿、非空的密码草稿，才算没提交的改动
const hasPendingDrafts = () => {
  const inputPending = Object.entries(inputDrafts.value).some(([key, draft]) => {
    const { optionName, inputName } = parseMaaFWOptionDraftKey(key)
    const option = optionMap.value.get(optionName)
    if (!option) return false
    return !isInputDraftUnchanged(option, inputName, draft)
  })
  return inputPending || Object.values(passwordDrafts.value).some(Boolean)
}

// 页面离开前提交全部草稿：校验不过的照常弹提示、留在框里，返回 false 交给页面按未保存处理
const flushDrafts = () => {
  for (const key of Object.keys(inputDrafts.value)) {
    const { optionName, inputName } = parseMaaFWOptionDraftKey(key)
    const inputItem = findInputItem(optionName, inputName)
    if (inputItem) commitInputDraft(optionName, inputItem)
  }
  for (const key of Object.keys(passwordDrafts.value)) {
    const { optionName, inputName } = parseMaaFWOptionDraftKey(key)
    const inputItem = findInputItem(optionName, inputName)
    if (inputItem) commitPasswordDraft(optionName, inputItem)
  }
  return !hasPendingDrafts()
}

const unregisterDrafts = draftRegistry?.register({
  hasPending: hasPendingDrafts,
  flush: flushDrafts,
})
onBeforeUnmount(() => unregisterDrafts?.())

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

.input-description {
  margin-top: 8px;
  color: var(--ant-color-text-secondary);
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
