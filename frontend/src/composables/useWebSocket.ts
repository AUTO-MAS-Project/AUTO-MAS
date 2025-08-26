import { ref, reactive } from 'vue'
import { message, notification } from 'ant-design-vue'
import { Service } from '@/api/services/Service'

// WebSocket连接状态
export type WebSocketStatus = '连接中' | '已连接' | '已断开' | '连接错误'

// WebSocket消息类型
export interface WebSocketMessage {
  type: 'Update' | 'Message' | 'Info' | 'Signal'
  data?: any
  message?: string
  messageId?: string
}

// WebSocket连接配置
export interface WebSocketConfig {
  taskId: string
  mode: '设置脚本' | '自动代理' | '人工排查'
  onMessage?: (data: any) => void
  onStatusChange?: (status: WebSocketStatus) => void
  onError?: (error: string) => void
  showNotifications?: boolean
}

export function useWebSocket() {
  const connections = ref<Map<string, WebSocket>>(new Map())
  const statuses = ref<Map<string, WebSocketStatus>>(new Map())

  // 获取WebSocket地址并建立连接
  const connect = async (config: WebSocketConfig): Promise<string | null> => {
    try {
      // 调用API获取WebSocket连接ID
      const response = await Service.addTaskApiDispatchStartPost({
        taskId: config.taskId,
        mode: config.mode as any,
      })

      if (response.code !== 200) {
        const errorMsg = response.message || '获取WebSocket地址失败'
        if (config.onError) {
          config.onError(errorMsg)
        } else {
          message.error(errorMsg)
        }
        return null
      }

      const websocketId = response.websocketId
      const wsUrl = `ws://localhost:8000/api/dispatch/ws/${websocketId}`

      // 建立WebSocket连接
      const ws = new WebSocket(wsUrl)
      connections.value.set(websocketId, ws)
      statuses.value.set(websocketId, '连接中')

      // 通知状态变化
      if (config.onStatusChange) {
        config.onStatusChange('连接中')
      }

      ws.onopen = () => {
        statuses.value.set(websocketId, '已连接')
        if (config.onStatusChange) {
          config.onStatusChange('已连接')
        }
        if (config.showNotifications !== false) {
          message.success('已连接到服务器')
        }
      }

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          handleMessage(data, config)
        } catch (error) {
          console.error('解析WebSocket消息失败:', error)
          const errorMsg = `收到无效消息: ${event.data}`
          if (config.onError) {
            config.onError(errorMsg)
          }
        }
      }

      ws.onclose = () => {
        statuses.value.set(websocketId, '已断开')
        connections.value.delete(websocketId)
        if (config.onStatusChange) {
          config.onStatusChange('已断开')
        }
        if (config.showNotifications !== false) {
          message.warning('与服务器连接已断开')
        }
      }

      ws.onerror = (error) => {
        statuses.value.set(websocketId, '连接错误')
        const errorMsg = '连接发生错误'
        if (config.onError) {
          config.onError(errorMsg)
        } else if (config.showNotifications !== false) {
          message.error(errorMsg)
        }
        console.error('WebSocket错误:', error)
      }

      return websocketId
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : '连接失败'
      if (config.onError) {
        config.onError(errorMsg)
      } else {
        message.error(errorMsg)
      }
      return null
    }
  }

  // 处理WebSocket消息
  const handleMessage = (data: WebSocketMessage, config: WebSocketConfig) => {
    // 调用自定义消息处理器
    if (config.onMessage) {
      config.onMessage(data)
    }

    // 默认消息处理
    switch (data.type) {
      case 'Info':
        // 通知信息
        let level = 'info'
        let content = '未知通知'

        // 检查数据中是否有 Error 字段
        if (data.data?.Error) {
          level = 'error'
          content = data.data.Error
        } else {
          content = data.data?.val || data.data?.message || data.message || '未知通知'
        }

        // 显示系统通知（仅在启用通知时）
        if (config.showNotifications !== false) {
          if (level === 'error') {
            notification.error({ message: '任务错误', description: content })
          } else if (level === 'warning') {
            notification.warning({ message: '任务警告', description: content })
          } else if (level === 'success') {
            notification.success({ message: '任务成功', description: content })
          } else {
            notification.info({ message: '任务信息', description: content })
          }
        }
        break

      case 'Signal':
        // 状态信号
        if (data.data?.Accomplish !== undefined) {
          const isSuccess = data.data.Accomplish
          const statusMsg = isSuccess ? '任务已完成' : '任务已失败'
          
          if (config.showNotifications !== false) {
            if (isSuccess) {
              notification.success({ message: '任务完成', description: statusMsg })
            } else {
              notification.error({ message: '任务失败', description: statusMsg })
            }
          }
        }
        break
    }
  }

  // 断开连接
  const disconnect = (websocketId: string) => {
    const ws = connections.value.get(websocketId)
    if (ws) {
      ws.close()
      connections.value.delete(websocketId)
      statuses.value.delete(websocketId)
    }
  }

  // 断开所有连接
  const disconnectAll = () => {
    connections.value.forEach((ws) => {
      ws.close()
    })
    connections.value.clear()
    statuses.value.clear()
  }

  // 发送消息
  const sendMessage = (websocketId: string, message: any) => {
    const ws = connections.value.get(websocketId)
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(message))
      return true
    }
    return false
  }

  // 获取连接状态
  const getStatus = (websocketId: string): WebSocketStatus | undefined => {
    return statuses.value.get(websocketId)
  }

  // 检查连接是否存在
  const isConnected = (websocketId: string): boolean => {
    const ws = connections.value.get(websocketId)
    return ws?.readyState === WebSocket.OPEN
  }

  return {
    connections: connections.value,
    statuses: statuses.value,
    connect,
    disconnect,
    disconnectAll,
    sendMessage,
    getStatus,
    isConnected,
  }
}