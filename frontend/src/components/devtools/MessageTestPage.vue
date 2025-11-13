<template>
  <div class="test-page">
    <h3 class="page-title">🔧 消息弹窗测试</h3>

    <div class="test-section">
      <h4>测试消息弹窗</h4>
      <div class="test-controls">
        <button class="test-btn primary" :disabled="isTesting" @click="triggerQuestionModal">
          {{ isTesting ? '测试中...' : '触发Question弹窗' }}
        </button>

        <button class="test-btn secondary" :disabled="isTesting" @click="triggerCustomModal">
          自定义消息测试
        </button>

        <button class="test-btn warning" :disabled="isTesting" @click="directTriggerModal">
          直接触发测试
        </button>

        <!-- 新增：3s 后触发 Question 弹窗（复用已有逻辑） -->
        <button
          class="test-btn secondary"
          :disabled="isTesting || isDelayed"
          @click="scheduleQuestionModal"
        >
          {{ isDelayed ? '已计划：3s 后触发...' : '3s 后触发Question弹窗' }}
        </button>
      </div>

      <div class="test-info">
        <p>点击按钮测试全屏消息选择弹窗功能</p>
        <p>最后响应: {{ lastResponse || '暂无' }}</p>
        <p>
          连接状态: <span :class="connectionStatusClass">{{ connectionStatus }}</span>
        </p>
      </div>
    </div>

    <div class="test-section">
      <h4>自定义测试消息</h4>
      <div class="custom-form">
        <div class="form-group">
          <label>标题:</label>
          <input
            v-model="customMessage.title"
            type="text"
            placeholder="请输入弹窗标题"
            class="form-input"
          />
        </div>
        <div class="form-group">
          <label>消息内容:</label>
          <textarea
            v-model="customMessage.message"
            placeholder="请输入消息内容"
            class="form-textarea"
            rows="3"
          ></textarea>
        </div>
        <button
          class="test-btn primary"
          :disabled="!customMessage.title || !customMessage.message"
          @click="sendCustomMessage"
        >
          发送自定义消息
        </button>
      </div>
    </div>

    <div class="test-section">
      <h4>测试历史</h4>
      <div class="test-history">
        <div v-for="(test, index) in testHistory" :key="index" class="history-item">
          <div class="history-time">{{ test.time }}</div>
          <div class="history-content">{{ test.title }} - {{ test.result }}</div>
        </div>
        <div v-if="testHistory.length === 0" class="no-history">暂无测试历史</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useWebSocket } from '@/composables/useWebSocket'
import { logger } from '@/utils/logger'

const { subscribe, unsubscribe, getConnectionInfo } = useWebSocket()

// 测试状态
const isTesting = ref(false)
const lastResponse = ref('')
const testHistory = ref<Array<{ time: string; title: string; result: string }>>([])
const connectionStatus = ref('检查中...')
const connectionStatusClass = ref('status-checking')

// 新增：延时触发状态与定时器
const isDelayed = ref(false)
let delayTimer: number | undefined

// 自定义消息
const customMessage = ref({
  title: '操作确认',
  message: '请确认是否继续执行此操作？',
})

// 更新连接状态
const updateConnectionStatus = () => {
  try {
    const connInfo = getConnectionInfo()
    connectionStatus.value = connInfo.status

    switch (connInfo.status) {
      case '已连接':
        connectionStatusClass.value = 'status-connected'
        break
      case '连接中':
        connectionStatusClass.value = 'status-connecting'
        break
      case '已断开':
        connectionStatusClass.value = 'status-disconnected'
        break
      case '连接错误':
        connectionStatusClass.value = 'status-error'
        break
      default:
        connectionStatusClass.value = 'status-unknown'
    }
  } catch {
    connectionStatus.value = '获取失败'
    connectionStatusClass.value = 'status-error'
  }
}

// 存储订阅ID用于监听响应
let responseSubscriptionId: string

// 生成唯一ID
const generateId = () => {
  return 'test-' + Math.random().toString(36).substr(2, 9)
}

// 格式化时间
const formatTime = () => {
  return new Date().toLocaleTimeString()
}

// 添加测试历史
const addTestHistory = (title: string, result: string) => {
  testHistory.value.unshift({
    time: formatTime(),
    title,
    result,
  })
  // 保持最多10条历史记录
  if (testHistory.value.length > 10) {
    testHistory.value = testHistory.value.slice(0, 10)
  }
}

// 直接触发弹窗（备用方法）
const directTriggerModal = () => {
  isTesting.value = true

  try {
    // 直接触发浏览器的confirm对话框作为备用测试
    const result = confirm(
      '这是直接触发的测试弹窗。\n\n如果WebSocket消息弹窗无法正常工作，这个方法可以用来验证基本功能。\n\n点击"确定"继续，点击"取消"退出。'
    )

    lastResponse.value = result ? '用户选择: 确认 (直接触发)' : '用户选择: 取消 (直接触发)'
    addTestHistory('直接触发测试', result ? '确认' : '取消')

    logger.info('[调试工具] 直接触发测试完成，结果:', result)
  } catch (error: any) {
    logger.error('[调试工具] 直接触发测试失败:', error)
    lastResponse.value = '直接触发失败: ' + (error?.message || '未知错误')
  }

  setTimeout(() => {
    isTesting.value = false
  }, 1000)
}

// 直接调用弹窗API测试功能
const simulateMessage = (messageData: any) => {
  logger.info('[调试工具] 直接测试弹窗功能:', messageData)

  try {
    // 检查是否在Electron环境
    if (typeof window !== 'undefined' && (window as any).electronAPI?.showQuestionDialog) {
      // 直接调用Electron的弹窗API进行测试
      ;(window as any).electronAPI
        .showQuestionDialog({
          title: messageData.title || '测试标题',
          message: messageData.message || '测试消息',
          options: messageData.options || ['确定', '取消'],
          messageId: messageData.message_id || 'test-' + Date.now(),
        })
        .then((result: boolean) => {
          logger.info('[调试工具] 弹窗测试结果:', result)
          const choice = result ? '确认' : '取消'
          lastResponse.value = `用户选择: ${choice}`
          addTestHistory('弹窗测试', choice)
        })
        .catch((error: any) => {
          logger.error('[调试工具] 弹窗测试失败:', error)
          lastResponse.value = '弹窗测试失败: ' + (error?.message || '未知错误')
        })
    } else {
      logger.warn('[调试工具] 不在Electron环境中或API不可用，使用浏览器confirm作为备用')
      const result = confirm(
        `${messageData.title || '测试'}\n\n${messageData.message || '这是测试消息'}`
      )
      const choice = result ? '确认' : '取消'
      lastResponse.value = `用户选择: ${choice} (浏览器备用)`
      addTestHistory('浏览器备用测试', choice)
    }
  } catch (error: any) {
    logger.error('[调试工具] 测试弹窗失败:', error)
    lastResponse.value = '测试失败: ' + (error?.message || '未知错误')
  }
}

// 触发标准Question弹窗
const triggerQuestionModal = () => {
  isTesting.value = true

  const testMessageData = {
    message_id: generateId(),
    type: 'Question',
    title: '测试提示',
    message: '这是一个测试消息，请选择您的操作。',
  }

  logger.info('[调试工具] 发送测试Question消息:', testMessageData)

  // 直接模拟接收消息
  simulateMessage(testMessageData)

  lastResponse.value = '已发送测试Question消息'
  addTestHistory('标准Question测试', '已发送')

  setTimeout(() => {
    isTesting.value = false
  }, 1000)
}

// 新增：3s 后触发 Question 弹窗（复用已有逻辑）
const scheduleQuestionModal = () => {
  if (isDelayed.value) return
  isDelayed.value = true
  delayTimer = window.setTimeout(() => {
    triggerQuestionModal()
    isDelayed.value = false
  }, 3000)
}

// 触发自定义弹窗
const triggerCustomModal = () => {
  isTesting.value = true

  const testMessageData = {
    message_id: generateId(),
    type: 'Question',
    title: '自定义测试',
    message:
      '这是一个自定义的测试消息，用于验证弹窗的不同内容显示。您可以测试长文本、特殊字符等情况。',
  }

  logger.info('[调试工具] 发送自定义测试消息:', testMessageData)

  simulateMessage(testMessageData)

  lastResponse.value = '已发送自定义测试消息'
  addTestHistory('自定义内容测试', '已发送')

  setTimeout(() => {
    isTesting.value = false
  }, 1000)
}

// 发送完全自定义的消息
const sendCustomMessage = () => {
  if (!customMessage.value.title || !customMessage.value.message) {
    return
  }

  isTesting.value = true

  const testMessageData = {
    message_id: generateId(),
    type: 'Question',
    title: customMessage.value.title,
    message: customMessage.value.message,
  }

  logger.info('[调试工具] 发送用户自定义消息:', testMessageData)

  simulateMessage(testMessageData)

  lastResponse.value = `已发送自定义消息: ${customMessage.value.title}`
  addTestHistory(`自定义: ${customMessage.value.title}`, '已发送')

  setTimeout(() => {
    isTesting.value = false
  }, 1000)
}

// 监听响应消息
const handleResponseMessage = (message: any) => {
  logger.info('[调试工具] 收到响应消息:', message)

  if (message.data && message.data.choice !== undefined) {
    const choice = message.data.choice ? '确认' : '取消'
    lastResponse.value = `用户选择: ${choice}`
    addTestHistory('用户响应', choice)
  }
}

// 组件挂载时订阅响应消息
onMounted(() => {
  logger.info('[调试工具] 初始化消息测试页面')

  // 订阅Response类型的消息来监听用户的选择结果
  responseSubscriptionId = subscribe({ type: 'Response' }, handleResponseMessage)

  // 初始化连接状态
  updateConnectionStatus()

  // 定期更新连接状态
  const statusTimer = setInterval(updateConnectionStatus, 2000)

  logger.info('[调试工具] 已订阅Response消息，订阅ID:', responseSubscriptionId)

  // 清理定时器
  onUnmounted(() => {
    clearInterval(statusTimer)
  })
})

// 组件卸载时清理订阅
onUnmounted(() => {
  if (responseSubscriptionId) {
    unsubscribe(responseSubscriptionId)
    logger.info('[调试工具] 已取消Response消息订阅')
  }
  // 清理延时触发定时器
  if (delayTimer) {
    clearTimeout(delayTimer)
    delayTimer = undefined
  }
})
</script>

<style scoped>
.test-page {
  color: #fff;
}

.page-title {
  margin: 0 0 16px 0;
  font-size: 14px;
  color: #4caf50;
}

.test-section {
  margin-bottom: 20px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 6px;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.test-section h4 {
  margin: 0 0 12px 0;
  font-size: 12px;
  color: #e0e0e0;
}

.test-controls {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.test-btn {
  padding: 6px 12px;
  border: none;
  border-radius: 4px;
  font-size: 11px;
  cursor: pointer;
  transition: all 0.2s ease;
  min-width: 80px;
}

.test-btn.primary {
  background: #4caf50;
  color: white;
}

.test-btn.primary:hover:not(:disabled) {
  background: #45a049;
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(76, 175, 80, 0.3);
}

.test-btn.secondary {
  background: #2196f3;
  color: white;
}

.test-btn.secondary:hover:not(:disabled) {
  background: #1976d2;
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(33, 150, 243, 0.3);
}

.test-btn.warning {
  background: #ff9800;
  color: white;
}

.test-btn.warning:hover:not(:disabled) {
  background: #f57c00;
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(255, 152, 0, 0.3);
}

.test-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.test-btn:active:not(:disabled) {
  transform: translateY(0);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.2);
}

.test-info {
  font-size: 10px;
  color: #bbb;
}

.test-info p {
  margin: 4px 0;
}

/* 连接状态样式 */
.status-connected {
  color: #4caf50;
  font-weight: 600;
}

.status-connecting {
  color: #ff9800;
  font-weight: 600;
}

.status-disconnected {
  color: #f44336;
  font-weight: 600;
}

.status-error {
  color: #e91e63;
  font-weight: 600;
}

.status-checking,
.status-unknown {
  color: #9e9e9e;
  font-weight: 600;
}

.custom-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.form-group label {
  font-size: 10px;
  color: #ccc;
  font-weight: 500;
}

.form-input,
.form-textarea {
  padding: 8px;
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.08);
  color: #fff;
  font-size: 11px;
  transition: all 0.2s ease;
}

.form-input:focus,
.form-textarea:focus {
  outline: none;
  border-color: #4caf50;
  background: rgba(255, 255, 255, 0.12);
  box-shadow: 0 0 0 2px rgba(76, 175, 80, 0.2);
}

.form-input::placeholder,
.form-textarea::placeholder {
  color: rgba(255, 255, 255, 0.4);
}

.form-textarea {
  resize: vertical;
  min-height: 60px;
  font-family: inherit;
}

.test-history {
  max-height: 120px;
  overflow-y: auto;
  border-radius: 4px;
}

.test-history::-webkit-scrollbar {
  width: 4px;
}

.test-history::-webkit-scrollbar-track {
  background: rgba(255, 255, 255, 0.05);
  border-radius: 2px;
}

.test-history::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.2);
  border-radius: 2px;
}

.test-history::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.3);
}

.history-item {
  display: flex;
  justify-content: space-between;
  padding: 6px 8px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  font-size: 10px;
  transition: background-color 0.2s ease;
  border-radius: 3px;
  margin-bottom: 2px;
}

.history-item:hover {
  background: rgba(255, 255, 255, 0.05);
}

.history-item:last-child {
  border-bottom: none;
  margin-bottom: 0;
}

.history-time {
  color: #888;
  min-width: 60px;
  font-weight: 500;
}

.history-content {
  color: #ccc;
  flex: 1;
  margin-left: 8px;
}

.no-history {
  text-align: center;
  color: #666;
  font-size: 10px;
  padding: 16px 0;
  font-style: italic;
}

/* 暗色主题专用样式增强 */
@media (prefers-color-scheme: dark) {
  .test-page {
    color: #e8e8e8;
  }

  .page-title {
    color: #66bb6a;
    text-shadow: 0 0 8px rgba(102, 187, 106, 0.3);
  }

  .test-section {
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.08);
    backdrop-filter: blur(8px);
  }

  .test-section h4 {
    color: #f0f0f0;
  }

  .test-btn.primary {
    background: linear-gradient(135deg, #4caf50 0%, #66bb6a 100%);
    border: 1px solid rgba(76, 175, 80, 0.3);
  }

  .test-btn.primary:hover:not(:disabled) {
    background: linear-gradient(135deg, #45a049 0%, #5cb85c 100%);
    border-color: rgba(76, 175, 80, 0.5);
  }

  .test-btn.secondary {
    background: linear-gradient(135deg, #2196f3 0%, #42a5f5 100%);
    border: 1px solid rgba(33, 150, 243, 0.3);
  }

  .test-btn.secondary:hover:not(:disabled) {
    background: linear-gradient(135deg, #1976d2 0%, #1e88e5 100%);
    border-color: rgba(33, 150, 243, 0.5);
  }

  .form-input,
  .form-textarea {
    background: rgba(0, 0, 0, 0.2);
    border-color: rgba(255, 255, 255, 0.15);
  }

  .form-input:focus,
  .form-textarea:focus {
    background: rgba(0, 0, 0, 0.3);
    border-color: #66bb6a;
    box-shadow: 0 0 0 2px rgba(102, 187, 106, 0.2);
  }

  .history-item {
    background: rgba(255, 255, 255, 0.02);
    border-bottom-color: rgba(255, 255, 255, 0.06);
  }

  .history-item:hover {
    background: rgba(255, 255, 255, 0.08);
  }

  .history-time {
    color: #aaa;
  }

  .history-content {
    color: #ddd;
  }
}

/* 高对比度模式适配 */
@media (prefers-contrast: more) {
  .test-section {
    border-width: 2px;
    border-color: rgba(255, 255, 255, 0.3);
  }

  .test-btn {
    border: 2px solid currentColor;
    font-weight: 600;
  }

  .form-input,
  .form-textarea {
    border-width: 2px;
  }

  .form-input:focus,
  .form-textarea:focus {
    border-width: 2px;
    box-shadow: 0 0 0 3px rgba(76, 175, 80, 0.3);
  }
}

/* 减少动画模式适配 */
@media (prefers-reduced-motion: reduce) {
  .test-btn,
  .form-input,
  .form-textarea,
  .history-item {
    transition: none;
  }

  .test-btn:hover:not(:disabled) {
    transform: none;
  }

  .page-title {
    text-shadow: none;
  }
}
</style>
