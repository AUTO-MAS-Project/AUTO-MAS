/**
 * 插件市场快照启动预热。
 *
 * 由 appEntry 在进入应用后以 fire-and-forget 方式调用（动态 import，
 * 不阻塞启动、不 gate 启动遮罩）。成功后把快照写入 sessionStorage 缓存，
 * 用户点进市场页时直接使用已预热数据；任何失败一律静默——市场页
 * 挂载时发现无缓存会自行发起正常请求兜底。
 */
import { useWebSocket } from '@/composables/useWebSocket'
import {
  WS_ID_PLUGIN_MARKET,
  WS_MARKET_ERROR,
  WS_MARKET_SNAPSHOT_REQUEST,
  WS_MARKET_SNAPSHOT_RESPONSE,
} from '@/services/websocket/types'
import type { MarketSnapshot } from './marketModel'
import { loadMarketSnapshotCache, saveMarketSnapshotCache } from './marketCache'

const PREWARM_TIMEOUT_MS = 15000

// 单飞行：应用一次会话只预热一次；失败也不重试，由市场页自然兜底。
let prewarmPromise: Promise<void> | null = null

async function runPrewarm(): Promise<void> {
  const logger = window.electronAPI.getLogger('插件市场预热')
  try {
    if (loadMarketSnapshotCache()) {
      logger.info('已存在市场快照缓存，跳过预热')
      return
    }

    const ws = useWebSocket()
    if (ws.state.value !== 'open') {
      logger.info('WebSocket 未连接，跳过市场快照预热（市场页打开时会自行请求）')
      return
    }

    const response = await ws.request(
      WS_ID_PLUGIN_MARKET,
      WS_MARKET_SNAPSHOT_REQUEST,
      [WS_MARKET_SNAPSHOT_RESPONSE, WS_MARKET_ERROR],
      { perPrefixLimit: 60 },
      PREWARM_TIMEOUT_MS
    )
    if (response.type === WS_MARKET_ERROR) {
      const message = String((response.data as { message?: unknown })?.message || '市场返回错误')
      logger.warn(`市场快照预热失败（静默）: ${message}`)
      return
    }

    const payload = (response.data as { payload?: unknown })?.payload
    if (payload && typeof payload === 'object') {
      saveMarketSnapshotCache(payload as MarketSnapshot)
      logger.info('市场快照预热完成，已写入缓存')
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    logger.warn(`市场快照预热失败（静默）: ${message}`)
  }
}

export function prewarmPluginMarketSnapshot(): Promise<void> {
  if (prewarmPromise) {
    return prewarmPromise
  }
  prewarmPromise = runPrewarm()
  return prewarmPromise
}
