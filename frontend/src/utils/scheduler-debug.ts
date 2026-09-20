// 调度中心调试工具
import { useWebSocket } from '@/composables/useWebSocket'
import { subscriptionCount } from '@/services/websocket/subscriptions'

const logger = window.electronAPI.getLogger('调度器调试')

export function debugScheduler() {
  logger.info('=== 调度中心调试信息 ===')

  // 主 WebSocket 连接诊断信息
  const { getConnectionInfo } = useWebSocket()
  const info = getConnectionInfo()
  logger.info(`WebSocket连接信息: ${JSON.stringify(info)}`)
  logger.info(`订阅数量: ${subscriptionCount()}`)

  // 检查调度中心状态
  const scheduler = document.querySelector('[data-scheduler-debug]')
  if (scheduler) {
    logger.info('调度中心组件已挂载')
  } else {
    logger.info('调度中心组件未找到')
  }
}

// 在控制台中暴露调试函数
if (typeof window !== 'undefined') {
  window.debugScheduler = debugScheduler
}
