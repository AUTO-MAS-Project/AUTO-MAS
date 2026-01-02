// 调度中心调试工具
import { getLogger } from '@/utils/logger'

const logger = getLogger('调度器调试')

export function debugScheduler() {
  logger.info('=== 调度中心调试信息 ===')

  // 检查WebSocket连接状态
  const wsStorage = (window as any)[Symbol.for('GLOBAL_WEBSOCKET_PERSISTENT')]
  if (wsStorage) {
    logger.info('WebSocket状态:', wsStorage.status.value)
    logger.info('WebSocket连接ID:', wsStorage.connectionId)
    logger.info('订阅数量:', wsStorage.subscriptions.value.size)
    logger.info('缓存标记数量:', wsStorage.cacheMarkers.value.size)
    logger.info('缓存消息数量:', wsStorage.cachedMessages.value.length)

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

// 测试WebSocket连接
export async function testWebSocketConnection() {
  logger.info('=== 测试WebSocket连接 ===')

  try {
    // 从 Electron 获取 WebSocket 端点
    let wsUrl = 'ws://localhost:36163/api/core/ws'
    if (window.electronAPI?.getApiEndpoint) {
      try {
        const wsEndpoint = await window.electronAPI.getApiEndpoint('websocket')
        wsUrl = `${wsEndpoint}/api/core/ws`
        logger.info(`使用端点: ${wsUrl}`)
      } catch (error) {
        logger.warn('获取端点失败，使用默认值:', error)
      }
    }
    
    const ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      logger.info('✅ WebSocket连接成功')
      ws.send(
        JSON.stringify({
          type: 'Signal',
          data: { Connect: true, connectionId: 'test-connection' },
        })
      )
    }

    ws.onmessage = event => {
      const message = JSON.parse(event.data)
      logger.info('📩 收到消息:', message)
    }

    ws.onerror = error => {
      logger.error('❌ WebSocket错误:', error)
    }

    ws.onclose = event => {
      logger.info('🔌 WebSocket连接关闭:', event.code, event.reason)
    }

    // 5秒后关闭测试连接
    setTimeout(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.close()
        logger.info('🔌 测试连接已关闭')
      }
    }, 5000)
  } catch (error) {
    logger.error('❌ 无法创建WebSocket连接:', error)
  }
}

// 在控制台中暴露调试函数
if (typeof window !== 'undefined') {
  ; (window as any).debugScheduler = debugScheduler
    ; (window as any).testWebSocketConnection = testWebSocketConnection
}
