/**
 * 插件市场快照的 sessionStorage 缓存。
 *
 * 由两处共用：
 * - PluginMarket.vue：挂载时读取缓存直接渲染，安装/刷新后写回；
 * - appEntry 的启动预热（marketPrewarm.ts）：应用进入后后台拉取快照写入缓存，
 *   用户首次打开市场页时即可命中，避免首开卡等待网络。
 *
 * 读写失败一律静默降级（返回 null / 不写入），不影响调用方主流程。
 */
import type { MarketSnapshot } from './marketModel'

export const PLUGIN_MARKET_CACHE_KEY = 'auto-mas-plugin-market-cache-v1'

export interface PluginMarketCache {
  snapshot: MarketSnapshot
  saved_at: string
}

export const saveMarketSnapshotCache = (snapshot: MarketSnapshot): boolean => {
  try {
    const payload: PluginMarketCache = {
      snapshot,
      saved_at: new Date().toISOString(),
    }
    sessionStorage.setItem(PLUGIN_MARKET_CACHE_KEY, JSON.stringify(payload))
    return true
  } catch {
    return false
  }
}

export const loadMarketSnapshotCache = (): MarketSnapshot | null => {
  try {
    const raw = sessionStorage.getItem(PLUGIN_MARKET_CACHE_KEY)
    if (!raw) {
      return null
    }
    const parsed = JSON.parse(raw) as PluginMarketCache
    if (!parsed || typeof parsed !== 'object' || !parsed.snapshot) {
      return null
    }
    return parsed.snapshot
  } catch {
    return null
  }
}
