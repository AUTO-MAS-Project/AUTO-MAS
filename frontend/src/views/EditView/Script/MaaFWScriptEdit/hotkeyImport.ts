// 把外壳（MXU / MFAAvalonia / MFW-PyQt6）实例里已经配好的键位带进脚本级 Game.Hotkeys：
// 键位弹窗的「从项目导入」与新建引导最后一步的「同时把键位导入到脚本」共用这里的纯逻辑。
import type { MaaFWShellInstanceItem } from '@/api'
import type { MaaFWInterfacePreviewData, MaaFWOptionInfo } from '@/types/script'
import { canonicalHotkey, formatHotkey, isStorableHotkey, parseHotkey } from '@/utils/maafwHotkey'
import { effectiveHotkeyValues, mergeHotkeyMap, type MaaFWHotkeyMap } from './hotkeyOptions'

/**
 * 外壳实例列表里读键位要用的字段。`hotkeys`（{option 名: {字段名: 组合键}}，后端只给 interface
 * 里声明过的 hotkey 选项与字段）是列表接口新加的，生成的客户端重生成前在这里声明成可选。
 */
export type MaaFWShellHotkeySource = Pick<
  MaaFWShellInstanceItem,
  'id' | 'name' | 'source' | 'active'
> & { hotkeys?: MaaFWHotkeyMap | null; sourceDir?: string }

/** 实例带的键位（没有就是空表） */
export const shellInstanceHotkeys = (instance: MaaFWShellHotkeySource): MaaFWHotkeyMap =>
  instance.hotkeys ?? {}

/** 实例带不带键位 */
export const hasShellInstanceHotkeys = (instance: MaaFWShellHotkeySource): boolean =>
  Object.values(shellInstanceHotkeys(instance)).some(fields => Object.keys(fields).length > 0)

/** 键位弹窗里「从项目导入」的一个候选：内容相同的实例已合并 */
export interface MaaFWHotkeyImportCandidate {
  /** 代表实例的 ID（下拉菜单的 key） */
  id: string
  /** 来源外壳 */
  source: string
  /** 代表实例的名字：合并进来的有外壳上次使用的那份就用它，否则是列表里第一份 */
  name: string
  /** 合并进来的实例里有外壳上次使用的那份 */
  active: boolean
  /** 限定到本次展示的 option / 字段后的键位 */
  hotkeys: MaaFWHotkeyMap
}

/** 只留展示的 option 里声明过的字段、非空的值 */
export const restrictHotkeys = (
  hotkeys: MaaFWHotkeyMap,
  options: readonly MaaFWOptionInfo[]
): MaaFWHotkeyMap => {
  const result: MaaFWHotkeyMap = {}
  for (const option of options) {
    const entry: Record<string, string> = {}
    for (const field of option.hotkeys ?? []) {
      const value = hotkeys[option.name]?.[field.name]
      if (typeof value === 'string' && value.trim()) entry[field.name] = value.trim()
    }
    if (Object.keys(entry).length > 0) result[option.name] = entry
  }
  return result
}

// 内容比较用：按展示顺序逐字段列出、组合键归一（与 sameHotkey 同一口径）
const hotkeySignature = (hotkeys: MaaFWHotkeyMap, options: readonly MaaFWOptionInfo[]) =>
  JSON.stringify(
    options.flatMap(option =>
      (option.hotkeys ?? []).map(field => canonicalHotkey(hotkeys[option.name]?.[field.name]))
    )
  )

/**
 * 「从项目导入」的候选：各实例的键位限定到展示的 option / 字段后非空的才算，内容完全相同的合并成
 * 一个（MXU 的键位是全局选项，所有实例共用，通常只剩一个）；外壳上次使用的那份排第一，其余按列表顺序。
 */
export const collectHotkeyImportCandidates = (
  instances: readonly MaaFWShellHotkeySource[],
  options: readonly MaaFWOptionInfo[]
): MaaFWHotkeyImportCandidate[] => {
  const groups = new Map<string, MaaFWHotkeyImportCandidate>()
  for (const instance of instances) {
    const hotkeys = restrictHotkeys(shellInstanceHotkeys(instance), options)
    if (Object.keys(hotkeys).length === 0) continue
    const signature = hotkeySignature(hotkeys, options)
    const existing = groups.get(signature)
    const active = Boolean(instance.active)
    if (!existing) {
      groups.set(signature, {
        id: instance.id,
        source: instance.source,
        name: instance.name,
        active,
        hotkeys,
      })
    } else if (active && !existing.active) {
      groups.set(signature, { ...existing, id: instance.id, name: instance.name, active })
    }
  }
  const candidates = [...groups.values()]
  return [...candidates.filter(item => item.active), ...candidates.filter(item => !item.active)]
}

export interface MaaFWHotkeyImportResult {
  /** 要填进去的字段（按存储串归一过），只含候选里有值且支持的 */
  values: MaaFWHotkeyMap
  /** 填进去的字段数 */
  applied: number
  /** 按键不支持、跳过的字段数 */
  skipped: number
}

/**
 * 把一份键位换成要填进弹窗草稿的值：展示的每个字段候选里有值就归一后填，主键不支持或解析不出的
 * 跳过并计数。修饰键个数与项目要的不符照样填，由弹窗标红并拦住保存。
 */
export const importHotkeyValues = (
  options: readonly MaaFWOptionInfo[],
  hotkeys: MaaFWHotkeyMap
): MaaFWHotkeyImportResult => {
  const values: MaaFWHotkeyMap = {}
  let applied = 0
  let skipped = 0
  for (const option of options) {
    for (const field of option.hotkeys ?? []) {
      const value = hotkeys[option.name]?.[field.name]
      if (typeof value !== 'string' || !value.trim()) continue
      if (!isStorableHotkey(value)) {
        skipped += 1
        continue
      }
      values[option.name] = {
        ...values[option.name],
        [field.name]: formatHotkey(parseHotkey(value)),
      }
      applied += 1
    }
  }
  return { values, applied, skipped }
}

/** interface 里全部 hotkey option（不按控制器 / 资源过滤：Game.Hotkeys 按 option 名存，切换后照样用） */
export const allHotkeyOptions = (
  previewData: MaaFWInterfacePreviewData | null
): MaaFWOptionInfo[] =>
  (previewData?.options ?? []).filter(option => option.type === 'hotkey' && option.hotkeys?.length)

/**
 * 把导入的键位并进 Game.Hotkeys：只动导入里出现的 option，其余条目原样保留；这些 option 里导入没给
 * 或不支持的字段沿用已存的值；与默认相同的字段不存。
 */
export const mergeImportedHotkeys = (
  existing: MaaFWHotkeyMap,
  options: readonly MaaFWOptionInfo[],
  imported: MaaFWHotkeyMap
): MaaFWHotkeyMap => {
  const { values } = importHotkeyValues(options, imported)
  const touched = options.filter(option => values[option.name])
  if (touched.length === 0) return existing
  const merged = effectiveHotkeyValues(touched, existing)
  for (const option of touched) {
    merged[option.name] = { ...merged[option.name], ...values[option.name] }
  }
  return mergeHotkeyMap(existing, touched, merged)
}
