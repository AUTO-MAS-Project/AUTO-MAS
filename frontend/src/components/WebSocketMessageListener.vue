<template>
  <div style="display: none">
    <!-- 这是一个隐藏的监听组件，不需要UI -->
  </div>

  <!-- 简单的自定义对话框 -->
  <div v-if="showDialog" class="dialog-overlay" @click.self="showDialog = false">
    <div class="dialog-container">
      <div class="dialog-header">
        <h3>{{ dialogData.title }}</h3>
      </div>
      <div class="dialog-content">
        <p>{{ dialogData.message }}</p>
      </div>
      <div class="dialog-actions">
        <button 
          v-for="(option, index) in dialogData.options" 
          :key="index"
          class="dialog-button"
          @click="handleChoice(index)"
        >
          {{ option }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref, nextTick } from 'vue'
import { useWebSocket, type WebSocketBaseMessage } from '@/composables/useWebSocket'
import { logger } from '@/utils/logger'

// WebSocket hook
const { subscribe, unsubscribe, sendRaw } = useWebSocket()

// 对话框状态
const showDialog = ref(false)
const dialogData = ref({
  title: '',
  message: '',
  options: ['确定', '取消'],
  messageId: ''
})

// 存储订阅ID用于取消订阅
let subscriptionId: string

// 发送用户选择结果到后端
const sendResponse = (messageId: string, choice: boolean) => {
  const response = {
    message_id: messageId,
    choice: choice,
  }

  logger.info('[WebSocket消息监听器] 发送用户选择结果:', response)

  // 发送响应消息到后端
  sendRaw('Response', response)
}

// 处理用户选择
const handleChoice = (choiceIndex: number) => {
  const choice = choiceIndex === 0 // 第一个选项为true，其他为false
  sendResponse(dialogData.value.messageId, choice)
  showDialog.value = false
}

// 显示问题对话框
const showQuestion = (questionData: any) => {
  const title = questionData.title || '操作提示'
  const message = questionData.message || ''
  const options = questionData.options || ['确定', '取消']
  const messageId = questionData.message_id || 'fallback_' + Date.now()
  
  logger.info('[WebSocket消息监听器] 显示自定义对话框:', questionData)
  
  // 设置对话框数据
  dialogData.value = {
    title,
    message,
    options,
    messageId
  }
  
  showDialog.value = true
  
  // 在下一个tick自动聚焦第一个按钮
  nextTick(() => {
    const firstButton = document.querySelector('.dialog-button:first-child') as HTMLButtonElement
    if (firstButton) {
      firstButton.focus()
    }
  })
}

// 消息处理函数
const handleMessage = (message: WebSocketBaseMessage) => {
  try {
    logger.info('[WebSocket消息监听器] 收到Message类型消息:', message)
    logger.info('[WebSocket消息监听器] 消息详情 - type:', message.type, 'id:', message.id, 'data:', message.data)

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
  logger.info('[WebSocket消息监听器] 检查消息类型 - data.type:', data.type, 'data.message_id:', data.message_id)
  
  if (data.type === 'Question') {
    logger.info('[WebSocket消息监听器] 发现Question类型消息')
    
    if (data.message_id) {
      logger.info('[WebSocket消息监听器] message_id存在，显示选择弹窗')
      showQuestion(data)
      return
    } else {
      logger.warn('[WebSocket消息监听器] Question消息缺少message_id字段:', data)
      // 即使缺少message_id，也尝试显示弹窗，使用当前时间戳作为ID
      const fallbackId = 'fallback_' + Date.now()
      logger.info('[WebSocket消息监听器] 使用备用ID显示弹窗:', fallbackId)
      showQuestion({
        ...data,
        message_id: fallbackId
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

<style scoped>
/* 对话框遮罩层 */
.dialog-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 9999;
}

/* 对话框容器 */
.dialog-container {
  background: white;
  border-radius: 8px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
  min-width: 300px;
  max-width: 500px;
  width: 90%;
  animation: dialogAppear 0.2s ease-out;
}

/* 对话框头部 */
.dialog-header {
  padding: 16px 20px;
  border-bottom: 1px solid #eee;
}

.dialog-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #333;
}

/* 对话框内容 */
.dialog-content {
  padding: 20px;
}

.dialog-content p {
  margin: 0;
  font-size: 14px;
  line-height: 1.5;
  color: #666;
  word-break: break-word;
}

/* 按钮区域 */
.dialog-actions {
  padding: 12px 20px 20px;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

/* 按钮样式 */
.dialog-button {
  padding: 8px 16px;
  border: 1px solid #ddd;
  border-radius: 4px;
  background: white;
  color: #333;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s ease;
  min-width: 60px;
}

.dialog-button:hover {
  background: #f5f5f5;
  border-color: #999;
}

.dialog-button:focus {
  outline: 2px solid #007bff;
  outline-offset: 2px;
}

.dialog-button:first-child {
  background: #007bff;
  color: white;
  border-color: #007bff;
}

.dialog-button:first-child:hover {
  background: #0056b3;
  border-color: #0056b3;
}

/* 出现动画 */
@keyframes dialogAppear {
  from {
    opacity: 0;
    transform: scale(0.9);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

/* 暗色主题适配 */
@media (prefers-color-scheme: dark) {
  .dialog-container {
    background: #2d2d2d;
    color: #fff;
  }

  .dialog-header {
    border-bottom-color: #444;
  }

  .dialog-header h3 {
    color: #fff;
  }

  .dialog-content p {
    color: #ccc;
  }

  .dialog-button {
    background: #444;
    color: #fff;
    border-color: #555;
  }

  .dialog-button:hover {
    background: #555;
    border-color: #666;
  }

  .dialog-button:first-child {
    background: #0d6efd;
    border-color: #0d6efd;
  }

  .dialog-button:first-child:hover {
    background: #0b5ed7;
    border-color: #0b5ed7;
  }
}
</style>
