import type { MascotMenuDefinition } from '../../src/types/mascotPack'
import { assertOptionalNumber, assertPlainObject, fail } from './assetPackageService'

/** 旧包使用同一协议的内置布局，不要求重新制作素材包。 */
export const DEFAULT_MASCOT_MENU: MascotMenuDefinition = {
  protocolVersion: 1,
  layout: 'list',
  items: [
    { capability: 'task.start', icon: '▶' },
    { capability: 'task.stop', icon: '■' },
    { separator: true },
    { capability: 'idle.refresh', icon: '↻' },
    { capability: 'idle.toggle', icon: '✉' },
    { capability: 'animation.toggle', icon: '❚❚' },
  ],
}

export function normalizeMascotMenu(value: unknown): MascotMenuDefinition | undefined {
  if (value === undefined) return undefined
  const raw = assertPlainObject(value, 'mascot.menu')
  if (raw.protocolVersion !== 1) fail('mascot.menu.protocolVersion 不受支持')
  if (raw.layout !== undefined && raw.layout !== 'list' && raw.layout !== 'grid')
    fail('mascot.menu.layout 不受支持')
  if (!Array.isArray(raw.items) || !raw.items.length || raw.items.length > 24)
    fail('mascot.menu.items 需要 1 到 24 个菜单项')
  const seen = new Set<string>()
  const items = raw.items.map((value: unknown): MascotMenuDefinition['items'][number] => {
    const item = assertPlainObject(value, 'mascot.menu.items')
    if (item.separator === true) return { separator: true }
    if (
      typeof item.capability !== 'string' ||
      !/^[a-z][a-z0-9.-]{0,63}$/.test(item.capability) ||
      seen.has(item.capability)
    )
      fail('mascot.menu.items.capability 无效或重复')
    seen.add(item.capability)
    if (item.icon !== undefined && (typeof item.icon !== 'string' || item.icon.length > 8))
      fail('mascot.menu.items.icon 需要不超过 8 个字符的文本')
    return { capability: item.capability, ...(item.icon === undefined ? {} : { icon: item.icon }) }
  })
  if (!seen.size) fail('mascot.menu.items 至少需要一个能力项')
  let style: MascotMenuDefinition['style']
  if (raw.style !== undefined) {
    const input = assertPlainObject(raw.style, 'mascot.menu.style')
    style = {}
    const ranges = { width: [160, 480], radius: [0, 32], fontSize: [12, 20], itemHeight: [32, 64] }
    for (const [key, [min, max]] of Object.entries(ranges)) {
      const value = assertOptionalNumber(input[key], `mascot.menu.style.${key}`, min, max)
      if (value !== undefined) Object.assign(style, { [key]: value })
    }
    for (const key of ['background', 'text', 'border', 'accent'] as const) {
      const color = input[key]
      if (color === undefined) continue
      if (typeof color !== 'string' || !/^#[\da-f]{6}([\da-f]{2})?$/i.test(color))
        fail(`mascot.menu.style.${key} 需要十六进制颜色`)
      style[key] = color
    }
  }
  return {
    protocolVersion: 1,
    layout: raw.layout ?? 'list',
    items,
    ...(style ? { style } : {}),
  }
}
