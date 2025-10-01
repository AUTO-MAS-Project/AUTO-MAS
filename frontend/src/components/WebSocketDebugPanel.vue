<template>
  <div class="websocket-debug">
    <h3>WebSocket 调试面板</h3>
    
    <div class="debug-section">
      <h4>连接状态</h4>
      <p>状态: {{ wsStatus }}</p>
      <p>订阅数量: {{ subscriberCount }}</p>
    </div>

    <div class="debug-section">
      <h4>测试消息</h4>
      <button @click="testQuestionMessage" class="test-btn">测试 Question 消息</button>
      <button @click="testNormalMessage" class="test-btn">测试普通消息</button>
      <button @click="testMalformedMessage" class="test-btn">测试格式错误消息</button>
    </div>

    <div class="debug-section">
      <h4>最近接收的消息</h4>
      <div class="message-log">
        <div v-for="(msg, index) in recentMessages" :key="index" class="message-item">
          <div class="message-timestamp">{{ msg.timestamp }}</div>
          <div class="message-content">{{ JSON.stringify(msg.data, null, 2) }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useWebSocket, type WebSocketBaseMessage } from '@/composables/useWebSocket'
import { logger } from '@/utils/logger'

const { subscribe, unsubscribe, sendRaw, getConnectionInfo } = useWebSocket()

// 状态
const wsStatus = ref('')
const subscriberCount = ref(0)
const recentMessages = ref<Array<{timestamp: string, data: any}>>([])

// 订阅ID
let debugSubscriptionId: string

// 更新状态
const updateStatus = () => {
  const connInfo = getConnectionInfo()
  wsStatus.value = connInfo.status
  subscriberCount.value = connInfo.subscriberCount
}

// 处理接收到的消息
const handleDebugMessage = (message: WebSocketBaseMessage) => {
  logger.info('[WebSocket调试] 收到消息:', message)
  
  // 添加到最近消息列表
  recentMessages.value.unshift({
    timestamp: new Date().toLocaleTimeString(),
    data: message
  })
  
  // 保持最近10条消息
  if (recentMessages.value.length > 10) {
    recentMessages.value = recentMessages.value.slice(0, 10)
  }
  
  updateStatus()
}

// 测试发送Question消息
const testQuestionMessage = () => {
  const message = {
    id: "debug_test_" + Date.now(),
    type: "message",
    data: {
      type: "Question",
      message_id: "q_" + Date.now(),
      title: "调试测试问题",
      message: "这是一个来自调试面板的测试问题，请选择是否继续？"
    }
  }
  
  logger.info('[WebSocket调试] 发送Question消息:', message)
  sendRaw('message', message.data)
}

// 测试发送普通消息
const testNormalMessage = () => {
  const message = {
    id: "debug_normal_" + Date.now(),
    type: "message",
    data: {
      action: "test_action",
      status: "running",
      content: "这是一个来自调试面板的普通消息"
    }
  }
  
  logger.info('[WebSocket调试] 发送普通消息:', message)
  sendRaw('message', message.data)
}

// 测试发送格式错误的消息
const testMalformedMessage = () => {
  const message = {
    id: "debug_malformed_" + Date.now(),
    type: "message",
    data: {
      type: "Question",
      // 故意缺少 message_id
      title: "格式错误的问题",
      message: "这个消息缺少message_id字段，测试容错处理"
    }
  }
  
  logger.info('[WebSocket调试] 发送格式错误消息:', message)
  sendRaw('message', message.data)
}

// 组件挂载
onMounted(() => {
  logger.info('[WebSocket调试] 调试面板挂载')
  
  // 订阅所有类型的消息进行调试
  debugSubscriptionId = subscribe({}, handleDebugMessage)
  
  updateStatus()
  
  // 定期更新状态
  const statusTimer = setInterval(updateStatus, 2000)
  
  // 组件卸载时清理定时器
  onUnmounted(() => {
    clearInterval(statusTimer)
  })
})

// 组件卸载
onUnmounted(() => {
  logger.info('[WebSocket调试] 调试面板卸载')
  if (debugSubscriptionId) {
    unsubscribe(debugSubscriptionId)
  }
})
</script>

<style scoped>
.websocket-debug {
  position: fixed;
  top: 80px;
  right: 20px;
  width: 350px;
  background: white;
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 15px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
  z-index: 1000;
  font-size: 12px;
  max-height: 600px;
  overflow-y: auto;
}

.debug-section {
  margin-bottom: 15px;
  padding-bottom: 10px;
  border-bottom: 1px solid #eee;
}

.debug-section:last-child {
  border-bottom: none;
}

h3 {
  margin: 0 0 15px 0;
  font-size: 14px;
  color: #333;
}

h4 {
  margin: 0 0 8px 0;
  font-size: 12px;
  color: #666;
  font-weight: 600;
}

p {
  margin: 4px 0;
  color: #555;
}

.test-btn {
  background: #007bff;
  color: white;
  border: none;
  padding: 6px 12px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 11px;
  margin: 2px;
}

.test-btn:hover {
  background: #0056b3;
}

.message-log {
  max-height: 200px;
  overflow-y: auto;
  background: #f8f9fa;
  border: 1px solid #dee2e6;
  border-radius: 4px;
  padding: 8px;
}

.message-item {
  margin-bottom: 8px;
  padding: 6px;
  background: white;
  border-radius: 3px;
  border-left: 3px solid #007bff;
}

.message-item:last-child {
  margin-bottom: 0;
}

.message-timestamp {
  font-size: 10px;
  color: #666;
  margin-bottom: 4px;
}

.message-content {
  font-family: monospace;
  font-size: 10px;
  color: #333;
  white-space: pre-wrap;
  word-break: break-word;
}

/* 暗色主题适配 */
@media (prefers-color-scheme: dark) {
  .websocket-debug {
    background: #2a2a2a;
    border-color: #444;
    color: white;
  }
  
  .debug-section {
    border-bottom-color: #444;
  }
  
  h3, h4 {
    color: #e8e8e8;
  }
  
  p {
    color: #ccc;
  }
  
  .message-log {
    background: #333;
    border-color: #555;
  }
  
  .message-item {
    background: #444;
  }
  
  .message-content {
    color: #e8e8e8;
  }
}
</style>