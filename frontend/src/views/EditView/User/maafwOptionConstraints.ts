import type { MaaFWOptionInfo, MaaFWOptionInputInfo } from '@/types/script'

/**
 * checkbox 选择数（PI v2.10.1 `min_count` / `max_count`）的当前状态。
 *
 * 限制值由后端加载器放宽成自洽的（下限不超过 case 数、上限不小于下限），这里直接用；
 * 没有任何限制时 `getCheckboxCountState` 返回 null。
 */
export type MaaFWCheckboxCountState = {
  min: number
  max: number | null
  count: number
  /** `min`：选少了；`max`：选多了（旧配置或项目默认值超过上限时会出现）；null：满足 */
  violation: 'min' | 'max' | null
}

const countSelectedCases = (option: MaaFWOptionInfo, selected: readonly string[]) => {
  const caseNames = new Set(option.cases.map(caseItem => caseItem.name))
  return new Set(selected.filter(caseName => caseNames.has(caseName))).size
}

export const getCheckboxCountState = (
  option: MaaFWOptionInfo,
  selected: readonly string[]
): MaaFWCheckboxCountState | null => {
  if (option.type !== 'checkbox') return null
  const min = Math.max(option.minCount ?? 0, 0)
  const max = option.maxCount ?? null
  if (min === 0 && max === null) return null

  const count = countSelectedCases(option, selected)
  let violation: MaaFWCheckboxCountState['violation'] = null
  if (count < min) violation = 'min'
  else if (max !== null && count > max) violation = 'max'
  return { min, max, count, violation }
}

/**
 * 达到上限后，还没勾的 case 一律禁用（协议：阻止超过 `max_count` 的勾选）；
 * 已勾的始终可以取消，旧配置超过上限时用户才能减回来。
 */
export const isCheckboxCaseLocked = (
  option: MaaFWOptionInfo,
  selected: readonly string[],
  caseName: string
) => {
  const max = option.type === 'checkbox' ? (option.maxCount ?? null) : null
  if (max === null || selected.includes(caseName)) return false
  return countSelectedCases(option, selected) >= max
}

/** PI v2.10.0：密码 / 密钥字段。界面只用掩码框、不回显已保存的值。 */
export const isPasswordInput = (inputItem: MaaFWOptionInputInfo) => inputItem.password === true

/** 已保存的密码字段在前端只拿得到密文；非空就算「已设置」。 */
export const hasStoredSecret = (value: string | undefined | null) => Boolean(value)
