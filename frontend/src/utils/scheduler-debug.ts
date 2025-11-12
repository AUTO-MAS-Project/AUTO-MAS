// 调度中心调试工具
export function debugScheduler() {
  console.log('=== 调度中心调试信息 ===')

  // 检查WebSocket连接状态
  const wsStorage = (window as any)[Symbol.for('GLOBAL_WEBSOCKET_PERSISTENT')]
  if (wsStorage) {
    console.log('WebSocket状态:', wsStorage.status.value)
    console.log('WebSocket连接ID:', wsStorage.connectionId)
    console.log('订阅数量:', wsStorage.subscriptions.value.size)
    console.log('缓存标记数量:', wsStorage.cacheMarkers.value.size)
    console.log('缓存消息数量:', wsStorage.cachedMessages.value.length)

    // 列出所有订阅
    console.log('当前订阅:')
    wsStorage.subscriptions.value.forEach((sub, id) => {
      console.log(`  - ${id}: type=${sub.filter.type}, id=${sub.filter.id}`)
    })
  } else {
    console.log('WebSocket存储未初始化')
  }

  // 检查调度中心状态
  const scheduler = document.querySelector('[data-scheduler-debug]')
  if (scheduler) {
    console.log('调度中心组件已挂载')
  } else {
    console.log('调度中心组件未找到')
  }
}

// 测试WebSocket连接
export function testWebSocketConnection() {
  console.log('=== 测试WebSocket连接 ===')

  try {
    const ws = new WebSocket('ws://localhost:36163/api/core/ws')

    ws.onopen = () => {
      console.log('✅ WebSocket连接成功')
      ws.send(
        JSON.stringify({
          type: 'Signal',
          data: { Connect: true, connectionId: 'test-connection' },
        })
      )
    }

    ws.onmessage = event => {
      const message = JSON.parse(event.data)
      console.log('📩 收到消息:', message)
    }

    ws.onerror = error => {
      console.log('❌ WebSocket错误:', error)
    }

    ws.onclose = event => {
      console.log('🔌 WebSocket连接关闭:', event.code, event.reason)
    }

    // 5秒后关闭测试连接
    setTimeout(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.close()
        console.log('🔌 测试连接已关闭')
      }
    }, 5000)
  } catch (error) {
    console.log('❌ 无法创建WebSocket连接:', error)
  }
}

// 在控制台中暴露调试函数
if (typeof window !== 'undefined') {
  ;(window as any).debugScheduler = debugScheduler
  ;(window as any).testWebSocketConnection = testWebSocketConnection
}
