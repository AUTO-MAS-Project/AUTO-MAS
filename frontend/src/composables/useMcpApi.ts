import { ref } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { Service, type McpStatusData } from '@/api'
import { queryClient } from '@/services/queryClient'
import { connectionState, onConnected, onDisconnected } from '@/services/websocket/connection'
import { subscribe, unsubscribe } from '@/services/websocket/subscriptions'
import { WS_ID_MCP, WS_MCP_STATUS_UPDATED } from '@/services/websocket/types'
import { observeFeature } from '@/utils/featureAnalytics'
import { translate as t } from '@/i18n'

const STATUS_KEY = ['core', 'mcp-status'] as const
const HOME_PAINT_TIMEOUT_MS = 5000
const HOME_PAINT_RETRY_MAX_MS = 30000
const logger = window.electronAPI.getLogger('MCP 状态')
let subscription: string | null = null
let disposeConnected: (() => void) | null = null
let disposeDisconnected: (() => void) | null = null
let generation = 0
let requestSequence = 0
let mutationSequence = 0
const retiredInstances = new Set<string>()
let homePainted = false
let homePaintRetryTimer: ReturnType<typeof setTimeout> | null = null
let homePaintRequest: ReturnType<
  typeof Service.notifyMcpHomePaintedApiCoreMcpHomePaintedPost
> | null = null
let paintFrame: number | null = null

function cancelHomePaintRetry(): void {
  if (homePaintRetryTimer !== null) clearTimeout(homePaintRetryTimer)
  homePaintRetryTimer = null
}

function cancelHomePaintRequest(): void {
  cancelHomePaintRetry()
  const request = homePaintRequest
  homePaintRequest = null
  request?.cancel()
}

async function releaseMcpAfterHomePaint(attempt = 0): Promise<void> {
  if (
    !homePainted ||
    subscription === null ||
    connectionState().value !== 'open' ||
    homePaintRequest
  )
    return
  cancelHomePaintRetry()
  const epoch = generation
  const request = Service.notifyMcpHomePaintedApiCoreMcpHomePaintedPost()
  homePaintRequest = request
  const timeout = setTimeout(() => request.cancel(), HOME_PAINT_TIMEOUT_MS)
  try {
    const response = await request
    if (response.code !== 200) throw new Error(response.message)
  } catch (error) {
    if (epoch !== generation || homePaintRequest !== request) return
    logger.warn(`通知首页首帧失败: ${String(error)}`)
    if (subscription !== null && connectionState().value === 'open') {
      homePaintRetryTimer = setTimeout(
        () => {
          homePaintRetryTimer = null
          if (epoch === generation && connectionState().value === 'open') {
            void releaseMcpAfterHomePaint(attempt + 1)
          }
        },
        Math.min(1000 * 2 ** Math.min(attempt, 5), HOME_PAINT_RETRY_MAX_MS)
      )
    }
  } finally {
    clearTimeout(timeout)
    if (homePaintRequest === request) homePaintRequest = null
  }
}

export function cancelMcpPaint(): void {
  if (paintFrame !== null) cancelAnimationFrame(paintFrame)
  paintFrame = null
}

export function scheduleMcpAfterPaint(): void {
  if (homePainted) return
  cancelMcpPaint()
  // 绘制等待归常驻 MCP 资源所有，切页时由布局接续，只有退出时彻底释放。
  paintFrame = requestAnimationFrame(() => {
    paintFrame = requestAnimationFrame(() => {
      paintFrame = null
      if (import.meta.env.DEV) performance.mark('auto-mas:mcp-release-paint')
      notifyMcpHomePainted()
    })
  })
}

export function notifyMcpHomePainted(): void {
  if (homePainted) return
  homePainted = true
  if (connectionState().value === 'open') void releaseMcpAfterHomePaint()
}

function applyStatus(next: McpStatusData): McpStatusData {
  const current = queryClient.getQueryData<McpStatusData>(STATUS_KEY)
  if (current) {
    if (current.instanceId === next.instanceId) {
      if (next.revision < current.revision) return current
      if (next.revision === current.revision) {
        next = { ...next, elapsedMs: Math.max(current.elapsedMs, next.elapsedMs) }
      }
    } else {
      if (retiredInstances.has(next.instanceId)) return current
      retiredInstances.add(current.instanceId)
      if (retiredInstances.size > 8)
        retiredInstances.delete(retiredInstances.values().next().value!)
    }
  }
  queryClient.setQueryData(STATUS_KEY, next)
  // 状态已确认开始加载或进入终态时，不再重复首帧通知。
  if (next.state !== 'pending') cancelHomePaintRequest()
  return next
}

async function fetchStatus(): Promise<McpStatusData> {
  const sequence = ++requestSequence
  const epoch = generation
  const mutation = mutationSequence
  const response = await Service.getMcpStatusApiCoreMcpStatusGet()
  if (response.code !== 200) throw new Error(t('core.tools.mcp.queryFailed'))
  const current = queryClient.getQueryData<McpStatusData>(STATUS_KEY)
  if (epoch !== generation || sequence !== requestSequence) return current ?? response.data
  // 请求期间先收到新进程的 WS 时，旧进程的在途快照不能把它换回去。
  if (mutation !== mutationSequence && current?.instanceId !== response.data.instanceId) {
    return current ?? response.data
  }
  return applyStatus(response.data)
}

export function bootstrapMcpStatus(): void {
  if (subscription !== null) return
  subscription = subscribe({ id: WS_ID_MCP, type: WS_MCP_STATUS_UPDATED }, message => {
    mutationSequence++
    applyStatus(message.data)
  })
  const reconnect = async () => {
    generation++
    cancelHomePaintRequest()
    // 后端重启会恢复为 pending；首页已经绘制过的窗口无需再次导航回首页。
    if (homePainted) void releaseMcpAfterHomePaint()
    try {
      await fetchStatus()
    } catch (error) {
      logger.warn(`MCP 状态恢复失败: ${String(error)}`)
    }
  }
  disposeConnected = onConnected(reconnect)
  disposeDisconnected = onDisconnected(() => {
    generation++
    cancelHomePaintRequest()
  })
  if (connectionState().value === 'open') void reconnect()
}

export function disposeMcpStatus(): void {
  generation++
  cancelMcpPaint()
  cancelHomePaintRequest()
  if (subscription !== null) unsubscribe(subscription)
  subscription = null
  disposeConnected?.()
  disposeConnected = null
  disposeDisconnected?.()
  disposeDisconnected = null
  retiredInstances.clear()
  queryClient.removeQueries({ queryKey: STATUS_KEY })
}

export function useMcpApi() {
  // 读取共享缓存；只有显式快照和 WS 入口写缓存，避免查询框架再次写入旧响应。
  const query = useQuery({ queryKey: STATUS_KEY, queryFn: fetchStatus, enabled: false })
  const loading = ref(false)
  const retrying = ref(false)
  const error = ref('')
  let active = true
  const dispose = () => {
    active = false
  }

  const refresh = async () => {
    loading.value = true
    error.value = ''
    try {
      const snapshot = await fetchStatus()
      if (active && homePainted && snapshot.state === 'pending') void releaseMcpAfterHomePaint()
    } catch {
      if (active) error.value = t('core.tools.mcp.queryFailed')
    } finally {
      if (active) loading.value = false
    }
  }
  const retry = async () => {
    if (retrying.value || query.data.value?.state !== 'failed') return
    retrying.value = true
    error.value = ''
    const epoch = generation
    // 使重试前尚未返回的查询失效；后端确认的状态仍按 revision 合并。
    requestSequence++
    try {
      const response = await observeFeature(
        'mcp_retry_requested',
        {},
        () => Service.retryMcpApiCoreMcpRetryPost(),
        result => (result.accepted ? 'accepted' : 'rejected')
      )
      if (epoch === generation) applyStatus(response.data)
      if (!response.accepted && active) error.value = t('core.tools.mcp.retryRejected')
    } catch {
      if (active) error.value = t('core.tools.mcp.retryFailed')
    } finally {
      if (active) retrying.value = false
    }
  }
  return { status: query.data, loading, retrying, error, refresh, retry, dispose }
}
