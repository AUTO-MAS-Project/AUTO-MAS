<template>
  <!-- 应用内弹窗组件 -->
  <Modal v-model:open="isModalOpen" :title="currentModal?.title || '操作提示'" :closable="false" :maskClosable="false"
    :keyboard="true" centered @ok="handleOk" @cancel="handleCancel">
    <p class="modal-message">{{ currentModal?.message || '' }}</p>
    <!-- 显示队列中还有多少待处理的弹窗 -->
    <p v-if="modalQueue.length > 0" class="modal-queue-hint">
      还有 {{ modalQueue.length }} 条消息待处理
    </p>
    <template #footer>
      <Button v-for="(option, index) in (currentModal?.options || ['确定', '取消'])" :key="index"
        :type="index === 0 ? 'primary' : 'default'" @click="handleChoice(index === 0)">
        {{ option }}
      </Button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { Modal, Button } from 'ant-design-vue'
import { useWebSocket, type WebSocketBaseMessage } from '@/composables/useWebSocket'

const logger = window.electronAPI.getLogger('WebSocket消息')

// 弹窗数据接口
interface ModalData {
  messageId: string
  title: string
  message: string
  options: string[]
}

// WebSocket hook
const { subscribe, unsubscribe, sendRaw } = useWebSocket()

// 存储订阅ID用于取消订阅
let subscriptionId: string

// Modal 队列状态
const modalQueue = ref<ModalData[]>([])
const currentModal = ref<ModalData | null>(null)
const isModalOpen = ref(false)

// 检查是否在 Electron 环境中
const isElectron = () => {
  return typeof window !== 'undefined' && (window as any).electronAPI
}

// 激活窗口到前台
const focusWindow = async () => {
  try {
    if (window.electronAPI?.windowFocus) {
      await window.electronAPI.windowFocus()
      logger.info('窗口已激活到前台')
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.warn(`激活窗口失败: ${errorMsg}`)
  }
}

// 发送用户选择结果到后端
const sendResponse = (messageId: string, choice: boolean) => {
  const response = { choice: choice }
  logger.info(`发送用户选择结果: ${JSON.stringify({ messageId, response })}`)

  // 发送响应消息到后端
  sendRaw('Response', response, messageId)
}

// 处理确认按钮
const handleOk = () => {
  handleChoice(true)
}

// 处理取消按钮
const handleCancel = () => {
  handleChoice(false)
}

// 处理用户选择
const handleChoice = (choice: boolean) => {
  if (currentModal.value) {
    sendResponse(currentModal.value.messageId, choice)
    logger.info(`弹窗已处理: ${currentModal.value.messageId}`)
  }

  // 关闭当前弹窗
  isModalOpen.value = false
  currentModal.value = null

  // 显示队列中的下一个弹窗
  showNextModal()
}

// 显示队列中的下一个弹窗
const showNextModal = async () => {
  if (modalQueue.value.length > 0) {
    // 从队列头部取出下一个弹窗
    const nextModal = modalQueue.value.shift()!
    logger.info(`显示队列中的下一个弹窗: ${nextModal.messageId}, 剩余队列: ${modalQueue.value.length}`)

    // 激活窗口
    await focusWindow()

    // 设置当前弹窗并显示
    currentModal.value = nextModal
    isModalOpen.value = true
  }
}

// 添加弹窗到队列
const showQuestion = async (questionData: any) => {
  const title = questionData.title || '操作提示'
  const message = questionData.message || ''
  const options = questionData.options || ['确定', '取消']
  const messageId = questionData.message_id || 'fallback_' + Date.now()

  const modalData: ModalData = {
    messageId,
    title,
    message,
    options,
  }

  logger.info(`收到弹窗请求: ${modalData.messageId}`)

  // 如果当前没有显示弹窗，直接显示
  if (!isModalOpen.value && !currentModal.value) {
    logger.info(`直接显示弹窗: ${modalData.messageId}`)

    // 激活窗口
    await focusWindow()

    // 设置当前弹窗并显示
    currentModal.value = modalData
    isModalOpen.value = true
  } else {
    // 否则加入队列
    modalQueue.value.push(modalData)
    logger.info(`弹窗已加入队列: ${modalData.messageId}, 当前队列长度: ${modalQueue.value.length}`)
  }
}

// 消息处理函数
const handleMessage = (message: WebSocketBaseMessage) => {
  try {
    // 只打印摘要信息，避免打印完整消息内容
    const dataSize = message.data ? (typeof message.data === 'string' ? message.data.length : JSON.stringify(message.data).length) : 0
    logger.info(`收到Message类型消息: ${JSON.stringify({
      type: message.type,
      id: message.id,
      dataSize: `${dataSize} bytes`
    })}`)

    // 解析消息数据
    if (message.data) {
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
      logger.warn('收到空数据的消息')
    }

    // 这里可以添加具体的业务逻辑
    // 例如：更新状态、触发事件、显示通知等
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`处理消息时发生错误: ${errorMsg}`)
  }
}

// 处理对象类型的消息
const handleObjectMessage = (data: any) => {
  // 打印完整对象内容
  logger.debug(`处理对象消息: ${JSON.stringify(data)}`)

  // 检查是否为Question类型的消息
  logger.debug(
    `检查消息类型 - data.type: ${data.type}, data.message_id: ${data.message_id}`
  )

  if (data.type === 'Question') {
    logger.info('发现Question类型消息')

    if (data.message_id) {
      logger.info('message_id存在，显示应用内弹窗')
      showQuestion(data)
      return
    } else {
      logger.warn('Question消息缺少message_id字段')
      // 即使缺少message_id，也尝试显示对话框，使用当前时间戳作为ID
      const fallbackId = 'fallback_' + Date.now()
      logger.info(`使用备用ID显示弹窗: ${fallbackId}`)
      showQuestion({
        ...data,
        message_id: fallbackId,
      })
      return
    }
  }

  // 根据对象的属性进行不同处理
  if (data.action) {
    logger.debug(`消息动作: ${data.action}`)
  }

  if (data.status) {
    logger.debug(`消息状态: ${data.status}`)
  }

  if (data.content) {
    logger.debug(`消息内容: ${data.content}`)
  }

  // 可以根据具体需求添加更多处理逻辑
}

// 处理字符串类型的消息
const handleStringMessage = (data: string) => {
  // 记录字符串消息
  logger.debug(`处理字符串消息: ${data}`)

  try {
    // 尝试解析JSON字符串
    const parsed = JSON.parse(data)
    logger.debug(`解析后的JSON: ${JSON.stringify(parsed)}`)
    handleObjectMessage(parsed)
  } catch (error) {
    // 不是JSON格式，作为普通字符串处理
    logger.debug(`普通字符串消息: ${data}`)
  }
}

// 处理其他类型的消息
const handleOtherMessage = (data: any) => {
  logger.debug(`处理其他类型消息: ${typeof data}, ${JSON.stringify(data)}`)
}

// 组件挂载时订阅消息
onMounted(() => {
  logger.info('组件挂载，开始监听Message类型的消息')

  // 使用新的 subscribe API，订阅 Message 类型的消息（注意大写M）
  subscriptionId = subscribe({ type: 'Message' }, handleMessage)

  logger.info(`订阅ID: ${subscriptionId}`)
  logger.info(`订阅过滤器: ${JSON.stringify({ type: 'Message' })}`)

    // 暴露调试接口到 window 对象（仅用于开发调试）
    ; (window as any).__debugShowQuestion = showQuestion
  logger.debug('已暴露调试接口: window.__debugShowQuestion')
})

// 组件卸载时取消订阅
onUnmounted(() => {
  logger.info('组件卸载，停止监听Message类型的消息')
  // 使用新的 unsubscribe API
  if (subscriptionId) {
    unsubscribe(subscriptionId)
  }
  // 清理调试接口
  delete (window as any).__debugShowQuestion
})
</script>

<style scoped>
.modal-message {
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-secondary, #595959);
  margin: 0;
  word-wrap: break-word;
  white-space: pre-wrap;
}

.modal-queue-hint {
  font-size: 12px;
  color: var(--text-tertiary, #8c8c8c);
  margin-top: 12px;
  margin-bottom: 0;
  padding-top: 8px;
  border-top: 1px solid var(--border-secondary, #f0f0f0);
}
</style>