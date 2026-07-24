import { useWebSocket } from '@/composables/useWebSocket'

// 调度中心调试工具
const logger = window.electronAPI.getLogger('调度器调试')

interface DebugSubscription {
  filter: {
    type?: unknown
    id?: unknown
  }
}

interface DebugWebSocketStorage {
  status: { value: unknown }
  connectionId: unknown
  subscriptions: { value: Map<unknown, DebugSubscription> }
  cacheMarkers: { value: Set<unknown> }
  cachedMessages: { value: unknown[] }
}

export function debugScheduler() {
  logger.info('=== 调度中心调试信息 ===')

  // 检查WebSocket连接状态
  const wsStorage = (window as unknown as Record<PropertyKey, DebugWebSocketStorage | undefined>)[
    Symbol.for('GLOBAL_WEBSOCKET_PERSISTENT')
  ]
  if (wsStorage) {
    logger.info(`WebSocket状态: ${wsStorage.status.value}`)
    logger.info(`WebSocket连接ID: ${wsStorage.connectionId}`)
    logger.info(`订阅数量: ${wsStorage.subscriptions.value.size}`)
    logger.info(`缓存标记数量: ${wsStorage.cacheMarkers.value.size}`)
    logger.info(`缓存消息数量: ${wsStorage.cachedMessages.value.length}`)

    // 列出所有订阅
    logger.info('当前订阅:')
    wsStorage.subscriptions.value.forEach((sub, id) => {
      logger.info(`  - ${id}: type=${sub.filter.type}, id=${sub.filter.id}`)
    })
  } else {
    logger.info('WebSocket存储未初始化')
  }

  // 检查调度中心状态
  const scheduler = document.querySelector('[data-scheduler-debug]')
  if (scheduler) {
    logger.info('调度中心组件已挂载')
  } else {
    logger.info('调度中心组件未找到')
  }
}

// 复用主连接测试 WebSocket，避免调试连接替换正常渲染器会话。
export function testWebSocketConnection() {
  logger.info('=== 测试WebSocket连接 ===')
  const { getConnectionInfo, sendRaw } = useWebSocket()
  const connection = getConnectionInfo()
  if (connection.wsReadyState !== WebSocket.OPEN) {
    logger.warn(`主 WebSocket 未连接: status=${connection.status}`)
    return false
  }

  const sent = sendRaw(
    'Signal',
    {
      Ping: Date.now(),
      connectionId: connection.connectionId,
    },
    'SchedulerDebug'
  )
  logger.info(sent ? 'WebSocket 心跳探测已发送' : 'WebSocket 心跳探测发送失败')
  return sent
}

// 在控制台中暴露调试函数
if (typeof window !== 'undefined') {
  window.debugScheduler = debugScheduler
  window.testWebSocketConnection = testWebSocketConnection
}
