import { ref, reactive, onUnmounted } from 'vue'
import { message, notification } from 'ant-design-vue'

// WebSocket连接状态
export type WebSocketStatus = '连接中' | '已连接' | '已断开' | '连接错误'

// WebSocket消息类型
export type WebSocketMessageType = 'Update' | 'Message' | 'Info' | 'Signal'

// WebSocket基础消息接口
export interface WebSocketBaseMessage {
  type: WebSocketMessageType
  data: any
}

// 进度消息接口
export interface ProgressMessage {
  taskId: string
  status: 'running' | 'waiting' | 'finished' | 'failed'
  progress: number
  msg: string
}

// 结果消息接口
export interface ResultMessage {
  taskId: string
  status: 'success' | 'failed'
  result: any
}

// 错误消息接口
export interface ErrorMessage {
  msg: string
  code: number
}

// 通知消息接口
export interface NotifyMessage {
  title: string
  content: string
}

// WebSocket连接配置
export interface WebSocketConfig {
  taskId: string
  onProgress?: (data: ProgressMessage) => void
  onResult?: (data: ResultMessage) => void
  onError?: (error: ErrorMessage) => void
  onNotify?: (notify: NotifyMessage) => void
  onStatusChange?: (status: WebSocketStatus) => void
  showNotifications?: boolean
}

export function useWebSocket() {
  const connections = ref<Map<string, WebSocket>>(new Map())
  const statuses = ref<Map<string, WebSocketStatus>>(new Map())
  const BASE_WS_URL = 'ws://localhost:36163/api/core/ws'

  // 心跳检测
  const heartbeat = (ws: WebSocket) => {
    const pingMessage = {
      type: 'Ping',
      data: {}
    }
    ws.send(JSON.stringify(pingMessage))
  }

  // 建立WebSocket连接
  const connect = async (config: WebSocketConfig): Promise<string | null> => {
    try {
      const ws = new WebSocket(BASE_WS_URL)
      const taskId = config.taskId

      ws.onopen = () => {
        statuses.value.set(taskId, '已连接')
        config.onStatusChange?.('已连接')

        // 启动心跳
        const heartbeatInterval = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            heartbeat(ws)
          }
        }, 30000)

        // 清理定时器
        ws.addEventListener('close', () => {
          clearInterval(heartbeatInterval)
        })
      }

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data) as WebSocketBaseMessage

          switch (message.type) {
            case 'Signal':
              // 心跳信��，无需特殊处理
              break
            case 'Progress':
              config.onProgress?.(message.data as ProgressMessage)
              break
            case 'Result':
              config.onResult?.(message.data as ResultMessage)
              break
            case 'Error':
              const errorData = message.data as ErrorMessage
              config.onError?.(errorData)
              if (config.showNotifications) {
                message.error(errorData.msg)
              }
              break
            case 'Notify':
              const notifyData = message.data as NotifyMessage
              config.onNotify?.(notifyData)
              if (config.showNotifications) {
                notification.info({
                  message: notifyData.title,
                  description: notifyData.content
                })
              }
              break
          }
        } catch (e) {
          console.error('WebSocket消息解析错误:', e)
        }
      }

      ws.onerror = (error) => {
        statuses.value.set(taskId, '连接错误')
        config.onStatusChange?.('连接错误')
        config.onError?.({ msg: 'WebSocket连接错误', code: 500 })
      }

      ws.onclose = () => {
        statuses.value.set(taskId, '已断开')
        config.onStatusChange?.('已断开')
        connections.value.delete(taskId)
      }

      connections.value.set(taskId, ws)
      statuses.value.set(taskId, '连接中')
      config.onStatusChange?.('连接中')

      return taskId
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : '连接失败'
      if (config.onError) {
        config.onError({ msg: errorMsg, code: 500 })
      }
      return null
    }
  }

  // 发送任务开始指令
  const startTask = (taskId: string, params: any) => {
    const ws = connections.value.get(taskId)
    if (ws && ws.readyState === WebSocket.OPEN) {
      const message = {
        type: 'StartTask',
        data: {
          taskId,
          params
        }
      }
      ws.send(JSON.stringify(message))
    }
  }

  // 更新配置
  const updateConfig = (configKey: string, value: any) => {
    // 发送给所���活跃连接
    connections.value.forEach((ws) => {
      if (ws.readyState === WebSocket.OPEN) {
        const message = {
          type: 'UpdateConfig',
          data: {
            configKey,
            value
          }
        }
        ws.send(JSON.stringify(message))
      }
    })
  }

  // 关闭连接
  const disconnect = (taskId: string) => {
    const ws = connections.value.get(taskId)
    if (ws) {
      ws.close()
      connections.value.delete(taskId)
      statuses.value.delete(taskId)
    }
  }

  // 关闭所有连接
  const disconnectAll = () => {
    connections.value.forEach((ws, taskId) => {
      disconnect(taskId)
    })
  }

  // 组件卸载时清理所有连接
  onUnmounted(() => {
    disconnectAll()
  })

  return {
    connect,
    disconnect,
    disconnectAll,
    startTask,
    updateConfig,
    statuses
  }
}