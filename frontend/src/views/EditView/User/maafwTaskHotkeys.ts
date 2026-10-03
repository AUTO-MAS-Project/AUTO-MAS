// #1127 按用户任务编辑器（MaaFWTaskOptionEditor）键位映射的数据层：taskOptions 里 hotkey 选项
// 存的是 Record<字段名, 组合键>（后端 pipeline_override 对 dict 取字段、空串回默认），只存与
// 默认不同的字段——与脚本级 Game.Hotkeys（hotkeyOptions.ts）同一约定，只是每任务一份。
import type { MaaFWOptionInfo } from '@/types/script'
import {
  countChangedHotkeys,
  effectiveHotkeyValues,
  mergeHotkeyMap,
  type MaaFWHotkeyMap,
} from '@/views/EditView/Script/MaaFWScriptEdit/hotkeyOptions'

/** 该 hotkey 选项在 taskOptions 里的字段表：原始值形状不对 / 非字符串一律当没有 */
export const hotkeyStoredFields = (
  option: MaaFWOptionInfo,
  raw: unknown
): Record<string, string> => {
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) return {}
  const record = raw as Record<string, unknown>
  const fields: Record<string, string> = {}
  for (const field of option.hotkeys ?? []) {
    const stored = record[field.name]
    if (typeof stored === 'string' && stored.trim()) fields[field.name] = stored
  }
  return fields
}

/** 与默认不同（canonical 意义上）的字段数：摘要行据此显示「已改 n 项」或「默认」 */
export const hotkeyChangedCount = (option: MaaFWOptionInfo, raw: unknown): number =>
  countChangedHotkeys([option], { [option.name]: hotkeyStoredFields(option, raw) })

/** 弹窗各字段的生效值（存的值，没有就是默认值） */
export const hotkeyModalValues = (option: MaaFWOptionInfo, raw: unknown): MaaFWHotkeyMap =>
  effectiveHotkeyValues([option], { [option.name]: hotkeyStoredFields(option, raw) })

/** 弹窗保存写回 taskOptions 的值：与默认相同的字段不存，全回默认就是空对象 */
export const hotkeySavedValue = (
  option: MaaFWOptionInfo,
  raw: unknown,
  values: MaaFWHotkeyMap
): Record<string, string> =>
  mergeHotkeyMap({ [option.name]: hotkeyStoredFields(option, raw) }, [option], values)[
    option.name
  ] ?? {}
