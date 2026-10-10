// MFW 选项在界面上显示的值：存了什么、没存或存的值已失效时按什么显示。口径与后端运行器
// app/task/MaaFW/tools/core/runner/pipeline_override.py 的 _normalize_choice_value /
// _normalize_checkbox_values / _coerce_input_value 一致——界面显示的就是运行时下发的，改一边要
// 同步另一边。编辑器（MaaFWTaskOptionEditor）与队列行上的勾选数检查共用这一份。

import type { MaaFWOptionInfo, MaaFWOptionInputInfo, MaaFWTaskOptionValue } from '@/types/script'
import { getCheckboxCountState } from './maafwOptionConstraints'

const CHOICE_TYPES = new Set(['select', 'scan_select', 'switch'])

export const isMaaFWChoiceOption = (option: MaaFWOptionInfo) => CHOICE_TYPES.has(option.type)

/** 单选类的默认 case：default_case 不在 cases 里（项目写错或更新后删了）就取第一个 case */
export const defaultMaaFWChoiceValue = (option: MaaFWOptionInfo): string => {
  const defaultCase = option.defaultCase
  if (typeof defaultCase === 'string' && option.cases.some(item => item.name === defaultCase)) {
    return defaultCase
  }
  return option.cases[0]?.name || ''
}

/**
 * 单选类实际生效的 case：存的值不在 cases 里（项目更新改名或删掉了这个 case）时，
 * 运行器按默认 case 跑，界面也按默认 case 显示、展开它的子选项。
 */
export const resolveMaaFWChoiceValue = (
  option: MaaFWOptionInfo,
  stored: MaaFWTaskOptionValue | undefined
): string =>
  typeof stored === 'string' && option.cases.some(item => item.name === stored)
    ? stored
    : defaultMaaFWChoiceValue(option)

/** 多选的默认勾选：default_case 里在 cases 中的那些 */
export const defaultMaaFWCheckboxValue = (option: MaaFWOptionInfo): string[] => {
  if (!Array.isArray(option.defaultCase)) return []
  const caseNames = new Set(option.cases.map(item => item.name))
  return option.defaultCase.filter(caseName => caseNames.has(caseName))
}

/** 多选当前的勾选：没存过按默认，存过就按存的（空数组就是一个都不勾） */
export const resolveMaaFWCheckboxValue = (
  option: MaaFWOptionInfo,
  stored: MaaFWTaskOptionValue | undefined
): string[] => {
  if (stored === undefined || stored === null) return defaultMaaFWCheckboxValue(option)
  return Array.isArray(stored) ? stored.filter(item => typeof item === 'string') : []
}

const pipelineTypeOf = (inputItem: MaaFWOptionInputInfo) =>
  (inputItem.pipelineType || 'string').toLowerCase()

export const isMaaFWIntegerInput = (inputItem: MaaFWOptionInputInfo) =>
  ['int', 'integer'].includes(pipelineTypeOf(inputItem))

export const isMaaFWDecimalInput = (inputItem: MaaFWOptionInputInfo) =>
  ['float', 'double', 'number'].includes(pipelineTypeOf(inputItem))

export const isMaaFWBooleanInput = (inputItem: MaaFWOptionInputInfo) =>
  ['bool', 'boolean'].includes(pipelineTypeOf(inputItem))

/** 存下来的 input 字段原值（没存就是空串） */
export const storedMaaFWInputFieldValue = (
  stored: MaaFWTaskOptionValue | undefined,
  inputName: string
): string => {
  if (!stored || Array.isArray(stored) || typeof stored !== 'object') return ''
  const value = stored[inputName]
  return typeof value === 'string' ? value : ''
}

/**
 * 数字 / 布尔字段的「项目默认」：这类字段没填时运行器按 interface 的 default 下发。
 * 字符串字段没有这条回落（空串本身就是合法取值，M9A 的兑换码没填就该是空），返回 null。
 */
export const maafwInputFallbackDefault = (inputItem: MaaFWOptionInputInfo): string | null => {
  if (pipelineTypeOf(inputItem) === 'string' || pipelineTypeOf(inputItem) === 'str') return null
  const fallback = (inputItem.default ?? '').trim()
  return fallback || null
}

/** input 字段实际生效的值：数字 / 布尔字段空着时就是项目默认值 */
export const effectiveMaaFWInputFieldValue = (
  inputItem: MaaFWOptionInputInfo,
  stored: MaaFWTaskOptionValue | undefined
): string => {
  const raw = storedMaaFWInputFieldValue(stored, inputItem.name)
  if (raw.trim()) return raw
  return maafwInputFallbackDefault(inputItem) ?? raw
}

export const isMaaFWTruthyInputText = (value: string) =>
  ['true', '1', 'yes', 'y', 'on'].includes(value.trim().toLowerCase())

/** 当前取值下展开的子选项组：单选类看生效的 case，多选看每个勾上的 case */
export const activeMaaFWNestedOptionGroups = (
  option: MaaFWOptionInfo,
  stored: MaaFWTaskOptionValue | undefined
): string[][] => {
  if (option.type === 'checkbox') {
    const selected = new Set(resolveMaaFWCheckboxValue(option, stored))
    return option.cases
      .filter(caseItem => selected.has(caseItem.name) && caseItem.option.length > 0)
      .map(caseItem => caseItem.option)
  }
  if (!isMaaFWChoiceOption(option)) return []
  const selectedName = resolveMaaFWChoiceValue(option, stored)
  const selectedCase = option.cases.find(caseItem => caseItem.name === selectedName)
  return selectedCase?.option.length ? [selectedCase.option] : []
}

/** 这个选项在当前控制器 / 资源下是否显示、是否生效 */
export const isMaaFWOptionActiveFor = (
  option: MaaFWOptionInfo,
  controllerName: string,
  resourceName: string
) => {
  if (option.controller.length > 0 && !option.controller.includes(controllerName)) return false
  if (option.resource.length > 0 && !option.resource.includes(resourceName)) return false
  return true
}

/**
 * 一组选项（连同当前取值下展开的子选项）里勾选数不满足 min_count / max_count 的多选项。
 * 运行器遇到这种选项会让整个用户的运行计划构建失败，队列行上据此给出标记。
 */
export const findMaaFWCheckboxCountViolations = (
  optionNames: readonly string[],
  optionMap: ReadonlyMap<string, MaaFWOptionInfo>,
  values: Record<string, MaaFWTaskOptionValue> | undefined,
  context: { controllerName: string; resourceName: string }
): MaaFWOptionInfo[] => {
  const violations: MaaFWOptionInfo[] = []
  const seen = new Set<string>()
  const visit = (names: readonly string[]) => {
    for (const name of names) {
      if (seen.has(name)) continue
      seen.add(name)
      const option = optionMap.get(name)
      if (!option || option.type === 'hotkey') continue
      if (!isMaaFWOptionActiveFor(option, context.controllerName, context.resourceName)) continue
      const stored = values?.[name]
      const state = getCheckboxCountState(option, resolveMaaFWCheckboxValue(option, stored))
      if (state?.violation) violations.push(option)
      for (const group of activeMaaFWNestedOptionGroups(option, stored)) visit(group)
    }
  }
  visit(optionNames)
  return violations
}
