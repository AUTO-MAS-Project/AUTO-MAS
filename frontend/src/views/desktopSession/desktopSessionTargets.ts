import { MAX_DESKTOP_SESSION_TARGETS } from '../../../electron/services/desktopSessionProtocol'

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/**
 * 把旧版「打开分身时一并启动」的选择并入清单末尾。
 *
 * 只剔除确定已删除的 id：known 里要同时含有现存的队列、托管和插件暂不可用的托管，
 * 插件不可用的托管是暂时读不到，不算删除。结果按序去重、统一小写，最多 100 条。
 */
export function mergeLegacyDesktopSessionTargets(
  current: readonly string[],
  legacy: unknown,
  known: ReadonlySet<string>
): string[] {
  const merged = [...new Set(current.map(id => id.toLowerCase()))]
  if (!Array.isArray(legacy)) return merged
  for (const value of legacy) {
    if (merged.length >= MAX_DESKTOP_SESSION_TARGETS) break
    if (typeof value !== 'string' || !UUID.test(value)) continue
    const id = value.toLowerCase()
    if (known.has(id) && !merged.includes(id)) merged.push(id)
  }
  return merged
}
