<template>
  <div style="display: none">
    <!-- 这是一个隐藏的监听组件，不需要UI -->
    <!-- 现在使用系统级对话框窗口而不是应用内弹窗 -->
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useWebSocket, type WebSocketBaseMessage } from '@/composables/useWebSocket'
import { logger } from '@/utils/logger'

// WebSocket hook
const { subscribe, unsubscribe, sendRaw } = useWebSocket()

// 存储订阅ID用于取消订阅
let subscriptionId: string

// 检查是否在 Electron 环境中
const isElectron = () => {
  return typeof window !== 'undefined' && (window as any).electronAPI
}

// 发送用户选择结果到后端
const sendResponse = (messageId: string, choice: boolean) => {
  const response = { choice: choice }
  logger.info('[WebSocket消息监听器] 发送用户选择结果:', response)

  // 发送响应消息到后端
  sendRaw('Response', response, messageId)
}

// 显示系统级问题对话框
const showQuestion = async (questionData: any) => {
  const title = questionData.title || '操作提示'
  const message = questionData.message || ''
  const options = questionData.options || ['确定', '取消']
  const messageId = questionData.message_id || 'fallback_' + Date.now()

  logger.info('[WebSocket消息监听器] 显示系统级对话框:', questionData)

  if (!isElectron()) {
    logger.error('[WebSocket消息监听器] 不在 Electron 环境中，无法显示系统级对话框')
    // 在非 Electron 环境中，使用默认响应
    sendResponse(messageId, false)
    return
  }

  try {
    // 调用 Electron API 显示系统级对话框
    const result = await (window as any).electronAPI.showQuestionDialog({
      title,
      message,
      options,
      messageId,
    })

    logger.info('[WebSocket消息监听器] 系统级对话框返回结果:', result)

    // 发送结果到后端
    sendResponse(messageId, result)
  } catch (error) {
    logger.error('[WebSocket消息监听器] 显示系统级对话框失败:', error)
    // 出错时发送默认响应
    sendResponse(messageId, false)
  }
}

// 消息处理函数
const handleMessage = (message: WebSocketBaseMessage) => {
  try {
    logger.info('[WebSocket消息监听器] 收到Message类型消息:', message)
    logger.info(
      '[WebSocket消息监听器] 消息详情 - type:',
      message.type,
      'id:',
      message.id,
      'data:',
      message.data
    )

    // 解析消息数据
    if (message.data) {
      console.log('[WebSocket消息监听器] 消息数据:', message.data)

      // 根据具体的消息内容进行处理
      if (typeof message.data === 'object') {
        // 处理对象类型的数据
        handleObjectMessage(message.data)
      } else if (typeof message.data === 'string') {
        // 处理字符串类型的数据
        handleStringMessage(message.data)
      } else {
        // 处理其他类型的数据
        handleOtherMessage(message.data)
      }
    } else {
      logger.warn('[WebSocket消息监听器] 收到空数据的消息')
    }

    // 这里可以添加具体的业务逻辑
    // 例如：更新状态、触发事件、显示通知等
  } catch (error) {
    logger.error('[WebSocket消息监听器] 处理消息时发生错误:', error)
  }
}

// 处理对象类型的消息
const handleObjectMessage = (data: any) => {
  logger.info('[WebSocket消息监听器] 处理对象消息:', data)

  // 检查是否为Question类型的消息
  logger.info(
    '[WebSocket消息监听器] 检查消息类型 - data.type:',
    data.type,
    'data.message_id:',
    data.message_id
  )

  if (data.type === 'Question') {
    logger.info('[WebSocket消息监听器] 发现Question类型消息')

    if (data.message_id) {
      logger.info('[WebSocket消息监听器] message_id存在，显示系统级对话框')
      showQuestion(data)
      return
    } else {
      logger.warn('[WebSocket消息监听器] Question消息缺少message_id字段:', data)
      // 即使缺少message_id，也尝试显示对话框，使用当前时间戳作为ID
      const fallbackId = 'fallback_' + Date.now()
      logger.info('[WebSocket消息监听器] 使用备用ID显示对话框:', fallbackId)
      showQuestion({
        ...data,
        message_id: fallbackId,
      })
      return
    }
  }

  // 根据对象的属性进行不同处理
  if (data.action) {
    logger.info('[WebSocket消息监听器] 消息动作:', data.action)
  }

  if (data.status) {
    logger.info('[WebSocket消息监听器] 消息状态:', data.status)
  }

  if (data.content) {
    logger.info('[WebSocket消息监听器] 消息内容:', data.content)
  }

  // 可以根据具体需求添加更多处理逻辑
}

// 处理字符串类型的消息
const handleStringMessage = (data: string) => {
  logger.info('[WebSocket消息监听器] 处理字符串消息:', data)

  try {
    // 尝试解析JSON字符串
    const parsed = JSON.parse(data)
    logger.info('[WebSocket消息监听器] 解析后的JSON:', parsed)
    handleObjectMessage(parsed)
  } catch (error) {
    // 不是JSON格式，作为普通字符串处理
    logger.info('[WebSocket消息监听器] 普通字符串消息:', data)
  }
}

// 处理其他类型的消息
const handleOtherMessage = (data: any) => {
  logger.info('[WebSocket消息监听器] 处理其他类型消息:', typeof data, data)
}

// 组件挂载时订阅消息
onMounted(() => {
  logger.info('[WebSocket消息监听器~~] 组件挂载，开始监听Message类型的消息')

  // 使用新的 subscribe API，订阅 Message 类型的消息（注意大写M）
  subscriptionId = subscribe({ type: 'Message' }, handleMessage)

  logger.info('[WebSocket消息监听器~~] 订阅ID:', subscriptionId)
  logger.info('[WebSocket消息监听器~~] 订阅过滤器:', { type: 'Message' })
})

// 组件卸载时取消订阅
onUnmounted(() => {
  logger.info('[WebSocket消息监听器~~] 组件卸载，停止监听Message类型的消息')
  // 使用新的 unsubscribe API
  if (subscriptionId) {
    unsubscribe(subscriptionId)
  }
})
</script>
