// MFW 键位映射（PI v2.8 hotkey）在脚本页的数据层：从 interface 预览里挑出对当前控制器 / 资源
// 生效的 hotkey option，读写脚本配置 Game.Hotkeys（JSON：{option 名: {字段名: 组合键}}，只存与
// 默认不同的字段）。
import type { MaaFWInterfacePreviewData, MaaFWOptionInfo } from '@/types/script'
import { formatHotkey, parseHotkey, sameHotkey } from '@/utils/maafwHotkey'

/** Game.Hotkeys 解析后的形态 */
export type MaaFWHotkeyMap = Record<string, Record<string, string>>

const appliesTo = (allowed: readonly string[] | undefined, name: string) =>
  !allowed || allowed.length === 0 || allowed.includes(name)

/**
 * 只挂在某个选项分支下的 hotkey option 的生效条件（最近一层）：用户在任务配置里没选到这个分支时，
 * 运行时不会叠加脚本级键位，弹窗要说清楚。
 */
export interface MaaFWHotkeyGate {
  /** 上级选项的显示名 */
  option: string
  /** 分支的显示名（没有 label 时是 case 名） */
  caseLabel: string
  /** 上级是 switch 且分支是「开」 */
  switchOn: boolean
}

const SWITCH_ON_CASES = /^(yes|y|true|on|1)$/i

const walkHotkeyOptions = (
  previewData: MaaFWInterfacePreviewData,
  controllerName: string,
  resourceName: string
) => {
  const optionByName = new Map(previewData.options.map(option => [option.name, option]))
  const resource = previewData.resources.find(item => item.name === resourceName)
  const controller = previewData.controllers.find(item => item.name === controllerName)
  const tasks = previewData.tasks.filter(
    task => appliesTo(task.controller, controllerName) && appliesTo(task.resource, resourceName)
  )
  // 直接挂在 globalOption / 资源 / 控制器 / 任务上的 option 不受任何分支约束
  const roots = [
    ...(previewData.globalOption ?? []),
    ...(resource?.option ?? []),
    ...(controller?.option ?? []),
    ...tasks.flatMap(task => task.option ?? []),
  ]
  const direct = new Set(roots)

  const seen = new Set<string>()
  const collected = new Set<string>()
  const gates = new Map<string, MaaFWHotkeyGate>()
  const visit = (name: string, gate: MaaFWHotkeyGate | null) => {
    if (seen.has(name)) return
    seen.add(name)
    const option = optionByName.get(name)
    if (!option) return
    if (!appliesTo(option.controller, controllerName)) return
    if (!appliesTo(option.resource, resourceName)) return
    if (option.type === 'hotkey' && option.hotkeys?.length) {
      collected.add(name)
      if (gate && !direct.has(name)) gates.set(name, gate)
    }
    for (const item of option.cases ?? []) {
      const childGate: MaaFWHotkeyGate = {
        option: option.label || option.name,
        caseLabel: item.label || item.name,
        switchOn: option.type === 'switch' && SWITCH_ON_CASES.test(item.name),
      }
      item.option?.forEach(child => visit(child, childGate))
    }
  }
  roots.forEach(name => visit(name, null))
  return { collected, gates }
}

/**
 * 对当前控制器 / 资源生效的 hotkey option：来源是 globalOption、当前资源与控制器的 option、
 * 适用任务的 option（含 cases 里的子选项），再按 option 自身的 controller / resource 过滤。
 * 先按 settings 里出现的顺序排，其余按 options 原顺序补齐。
 */
export const collectHotkeyOptions = (
  previewData: MaaFWInterfacePreviewData | null,
  controllerName: string,
  resourceName: string
): MaaFWOptionInfo[] => {
  if (!previewData) return []
  const { collected } = walkHotkeyOptions(previewData, controllerName, resourceName)

  const settingOrder = new Map<string, number>()
  for (const setting of previewData.settings ?? []) {
    for (const name of setting.option ?? []) {
      if (!settingOrder.has(name)) settingOrder.set(name, settingOrder.size)
    }
  }
  const ranked = previewData.options
    .map((option, index) => ({ option, index }))
    .filter(({ option }) => collected.has(option.name))
  ranked.sort((a, b) => {
    const rankA = settingOrder.get(a.option.name) ?? Number.POSITIVE_INFINITY
    const rankB = settingOrder.get(b.option.name) ?? Number.POSITIVE_INFINITY
    return rankA === rankB ? a.index - b.index : rankA - rankB
  })
  return ranked.map(({ option }) => option)
}

/** 只在某个分支下才生效的 hotkey option → 生效条件；直接挂着的不在结果里 */
export const collectHotkeyGates = (
  previewData: MaaFWInterfacePreviewData | null,
  controllerName: string,
  resourceName: string
): Record<string, MaaFWHotkeyGate> => {
  if (!previewData) return {}
  const { gates } = walkHotkeyOptions(previewData, controllerName, resourceName)
  return Object.fromEntries(gates)
}

/** 弹窗副标题：展示的 option 所在的 setting 里只有一个带描述时用它，否则不显示 */
export const hotkeySettingDescription = (
  previewData: MaaFWInterfacePreviewData | null,
  options: readonly MaaFWOptionInfo[]
): string => {
  const names = new Set(options.map(option => option.name))
  const descriptions = (previewData?.settings ?? [])
    .filter(setting => setting.option?.some(name => names.has(name)))
    .map(setting => setting.description?.trim() ?? '')
    .filter(Boolean)
  return descriptions.length === 1 ? descriptions[0] : ''
}

/** 读 Game.Hotkeys；不是合法 JSON 或形状不对的部分一律当没有 */
export const parseHotkeyMap = (value: string | null | undefined): MaaFWHotkeyMap => {
  let parsed: unknown
  try {
    parsed = JSON.parse(value || '{}')
  } catch {
    return {}
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
  const result: MaaFWHotkeyMap = {}
  for (const [optionName, fields] of Object.entries(parsed as Record<string, unknown>)) {
    if (!fields || typeof fields !== 'object' || Array.isArray(fields)) continue
    const entry: Record<string, string> = {}
    for (const [fieldName, combo] of Object.entries(fields as Record<string, unknown>)) {
      if (typeof combo === 'string' && combo.trim()) entry[fieldName] = combo
    }
    if (Object.keys(entry).length > 0) result[optionName] = entry
  }
  return result
}

/** 每个字段当前生效的组合键（存的值，没有就是默认值），按存储串给出 */
export const effectiveHotkeyValues = (
  options: readonly MaaFWOptionInfo[],
  map: MaaFWHotkeyMap
): MaaFWHotkeyMap => {
  const result: MaaFWHotkeyMap = {}
  for (const option of options) {
    const entry: Record<string, string> = {}
    for (const field of option.hotkeys ?? []) {
      const stored = map[option.name]?.[field.name]
      entry[field.name] = formatHotkey(parseHotkey(stored || field.default || ''))
    }
    result[option.name] = entry
  }
  return result
}

/**
 * 弹窗常驻说明用：这批键位要不要组合键。都只按单键为 none；都要同样个数的修饰键为 all；
 * 有的要有的不要（或个数不同）为 mixed，此时由各行自己标出个数。
 */
export type MaaFWHotkeyComboSummary =
  | { kind: 'none' }
  | { kind: 'all'; count: number }
  | { kind: 'mixed' }

export const hotkeyComboSummary = (
  options: readonly MaaFWOptionInfo[]
): MaaFWHotkeyComboSummary => {
  const counts = new Set(
    options.flatMap(option => (option.hotkeys ?? []).map(field => field.modifierCount ?? 0))
  )
  if (counts.size === 0 || (counts.size === 1 && counts.has(0))) return { kind: 'none' }
  if (counts.size === 1) return { kind: 'all', count: [...counts][0] }
  return { kind: 'mixed' }
}

/**
 * 录到的组合键与项目要的修饰键个数对不上时的原因：项目 pipeline 只按得出 modifierCount 个修饰键，
 * 少了映射不出它要的占位符，多了运行时不会按下。对得上返回 null。
 */
export const hotkeyModifierProblem = (
  keys: readonly string[],
  modifierCount: number | undefined
): 'single-key-only' | 'needs-modifiers' | null => {
  const required = modifierCount ?? 0
  const pressed = Math.max(keys.length - 1, 0)
  if (pressed === required) return null
  return required === 0 ? 'single-key-only' : 'needs-modifiers'
}

/** 已改（与默认不同）的字段数 */
export const countChangedHotkeys = (
  options: readonly MaaFWOptionInfo[],
  values: MaaFWHotkeyMap
): number =>
  options.reduce(
    (total, option) =>
      total +
      (option.hotkeys ?? []).filter(field => {
        const value = values[option.name]?.[field.name]
        return Boolean(value) && !sameHotkey(value, field.default ?? '')
      }).length,
    0
  )

/**
 * 把弹窗里的值写回 Game.Hotkeys：只替换这次展示的 option 的条目（没展示的原样保留，资源切换
 * 暂时看不到的不能删）；与默认相同的字段不存，option 空了就删掉。
 */
export const mergeHotkeyMap = (
  existing: MaaFWHotkeyMap,
  options: readonly MaaFWOptionInfo[],
  values: MaaFWHotkeyMap
): MaaFWHotkeyMap => {
  const result: MaaFWHotkeyMap = { ...existing }
  for (const option of options) {
    delete result[option.name]
    const entry: Record<string, string> = {}
    for (const field of option.hotkeys ?? []) {
      const value = values[option.name]?.[field.name]
      if (value && !sameHotkey(value, field.default ?? '')) entry[field.name] = value
    }
    if (Object.keys(entry).length > 0) result[option.name] = entry
  }
  return result
}
