/**
 * Emulator 2.0 里模拟器类型的显示：名字与固定配色。设备表、路径弹窗、搜索与移除弹窗共用。
 */

/** 来源类型固定配色，路径、设备和弹窗保持一致。 */
const TYPE_COLORS: Record<string, string> = {
  ldplayer: 'blue',
  mumu: 'cyan',
  avd: 'purple',
}

export const typeColor = (type: string | undefined) => TYPE_COLORS[type ?? ''] ?? 'default'

/** 模拟器类型 → 用户看得懂的名字。界面上不该出现 ldplayer / mumu 这种内部名。 */
export const typeLabelOf = (t: (key: string) => string, type: string | undefined) => {
  if (!type) return ''
  const key = `emulator.type.${type}`
  const text = t(key)
  return text === key ? type : text
}
