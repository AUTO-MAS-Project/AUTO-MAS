<template>
  <!-- 应用内弹窗组件 -->
  <Modal
    v-model:open="isModalOpen"
    :title="currentModal?.title || '操作提示'"
    :closable="false"
    :mask-closable="false"
    :keyboard="true"
    centered
    @ok="handleOk"
    @cancel="handleCancel"
  >
    <p class="modal-message">{{ currentModal?.message || '' }}</p>
    <!-- 显示队列中还有多少待处理的弹窗 -->
    <p v-if="modalQueue.length > 0" class="modal-queue-hint">
      还有 {{ modalQueue.length }} 条消息待处理
    </p>
    <template #footer>
      <Button
        v-for="(option, index) in currentModal?.options || ['确定', '取消']"
        :key="index"
        :type="index === 0 ? 'primary' : 'default'"
        @click="handleChoice(index === 0)"
      >
        {{ option }}
      </Button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { Modal, Button, message as antMessage } from 'ant-design-vue'
import {
  normalizeDialogRequestData,
  useWebSocket,
  type WebSocketBaseMessage,
} from '@/composables/useWebSocket'
import { useAppLifecycle } from '@/composables/useAppLifecycle'
import {
  WS_ID_ARKNIGHTS_TOOLKIT,
  WS_TOOLKIT_NOTICE,
  type WSTaskNoticeData,
} from '@/services/websocket/types'

const logger = window.electronAPI.getLogger('WebSocket消息')

// 弹窗数据接口
interface ModalData {
  messageId: string
  title: string
  message: string
  options: string[]
  responseProtocol: 'legacy' | 'dialog'
}

// WebSocket hook
const { subscribe, unsubscribe, sendRaw } = useWebSocket()
const { initializeAppLifecycle, dialogRequests, respondDialog } = useAppLifecycle()
initializeAppLifecycle()

// 存储订阅ID用于取消订阅
let legacySubscriptionId: string | undefined
let toolkitNoticeSubscriptionId: string | undefined

// Modal 队列状态
const modalQueue = ref<ModalData[]>([])
const currentModal = ref<ModalData | null>(null)
const isModalOpen = ref(false)

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
const sendResponse = (modal: ModalData, choice: boolean): boolean => {
  if (modal.responseProtocol === 'dialog') {
    logger.info(`发送弹窗响应: ${modal.messageId}, choice=${choice}`)
    return respondDialog(modal.messageId, choice)
  }

  const response = { choice }
  logger.info(`发送用户选择结果: ${JSON.stringify({ messageId: modal.messageId, response })}`)

  // 保留旧 Message/Response 协议
  return sendRaw('Response', response, modal.messageId)
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
    const sent = sendResponse(currentModal.value, choice)
    if (currentModal.value.responseProtocol === 'dialog' && !sent) {
      logger.warn(`弹窗响应发送失败，保留弹窗等待重连: ${currentModal.value.messageId}`)
      isModalOpen.value = true
      return
    }
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
    logger.info(
      `显示队列中的下一个弹窗: ${nextModal.messageId}, 剩余队列: ${modalQueue.value.length}`
    )

    // 激活窗口
    await focusWindow()

    // 设置当前弹窗并显示
    currentModal.value = nextModal
    isModalOpen.value = true
  }
}

const isSameModal = (left: ModalData, right: ModalData): boolean =>
  left.messageId === right.messageId && left.responseProtocol === right.responseProtocol

// 添加弹窗到队列
const enqueueModal = async (modalData: ModalData) => {
  if (
    (currentModal.value && isSameModal(currentModal.value, modalData)) ||
    modalQueue.value.some(queuedModal => isSameModal(queuedModal, modalData))
  ) {
    logger.info(`忽略重复弹窗请求: ${modalData.messageId}`)
    return
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

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

// 工具箱通知（id=ArknightsPCToolkit, type=toolkit.notice）：
// 后端 MaaFW 工具异步错误由此推送（如 ArknightsPC 连接明日方舟窗口失败，
// app/MaaFW/ArknightWin32.py），payload 复用 WSTaskNoticeData { level, message }。
const handleToolkitNotice = (envelope: WebSocketBaseMessage) => {
  const data = (isRecord(envelope.data) ? envelope.data : {}) as Partial<WSTaskNoticeData>
  const text =
    typeof data.message === 'string' && data.message.trim().length > 0
      ? data.message
      : '明日方舟工具箱发生未知错误'
  logger.info(`收到工具箱通知: level=${data.level ?? 'info'}, message=${text}`)

  if (data.level === 'error') {
    antMessage.error(text)
  } else if (data.level === 'warning') {
    antMessage.warning(text)
  } else {
    antMessage.info(text)
  }
}

const showQuestion = async (questionData: unknown) => {
  if (!isRecord(questionData)) {
    logger.warn('收到无效的旧版 Question 消息')
    return
  }

  const options = Array.isArray(questionData.options)
    ? questionData.options.filter((option): option is string => typeof option === 'string')
    : []
  const rawMessageId = questionData.message_id

  await enqueueModal({
    messageId:
      typeof rawMessageId === 'string' && rawMessageId.length > 0
        ? rawMessageId
        : `fallback_${Date.now()}`,
    title: typeof questionData.title === 'string' ? questionData.title : '操作提示',
    message: typeof questionData.message === 'string' ? questionData.message : '',
    options: options.length > 0 ? options : ['确定', '取消'],
    responseProtocol: 'legacy',
  })
}

const handleDialogRequest = (data: unknown) => {
  const request = normalizeDialogRequestData(data)
  if (!request) {
    logger.warn('dialog.request 缺少有效的 data.requestId，已拒绝创建无法关联的弹窗')
    return
  }

  void enqueueModal({
    messageId: request.requestId,
    title: request.title,
    message: request.message,
    options: request.options,
    responseProtocol: 'dialog',
  })
}

// 新协议由应用生命周期协调器唯一订阅；本组件只负责把待响应请求渲染成队列。
watch(
  dialogRequests,
  requests => {
    for (const request of requests) {
      handleDialogRequest(request)
    }
  },
  { immediate: true }
)

// 消息处理函数
const handleMessage = (message: WebSocketBaseMessage) => {
  try {
    // 只打印摘要信息，避免打印完整消息内容
    const dataSize = message.data
      ? typeof message.data === 'string'
        ? message.data.length
        : JSON.stringify(message.data).length
      : 0
    logger.info(
      `收到Message类型消息: ${JSON.stringify({
        type: message.type,
        id: message.id,
        dataSize: `${dataSize} bytes`,
      })}`
    )

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
const handleObjectMessage = (data: unknown) => {
  if (!isRecord(data)) {
    logger.warn('收到非对象的 Message 数据')
    return
  }

  // 打印完整对象内容
  logger.debug(`处理对象消息: ${JSON.stringify(data)}`)

  // 检查是否为Question类型的消息
  logger.debug(`检查消息类型 - data.type: ${data.type}, data.message_id: ${data.message_id}`)

  if (data.type === 'Question') {
    logger.info('发现Question类型消息')

    if (data.message_id) {
      logger.info('message_id存在，显示应用内弹窗')
      void showQuestion(data)
      return
    } else {
      logger.warn('Question消息缺少message_id字段')
      // 即使缺少message_id，也尝试显示对话框，使用当前时间戳作为ID
      const fallbackId = 'fallback_' + Date.now()
      logger.info(`使用备用ID显示弹窗: ${fallbackId}`)
      void showQuestion({
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
  } catch {
    // 不是JSON格式，作为普通字符串处理
    logger.debug(`普通字符串消息: ${data}`)
  }
}

// 处理其他类型的消息
const handleOtherMessage = (data: unknown) => {
  logger.debug(`处理其他类型消息: ${typeof data}, ${JSON.stringify(data)}`)
}

// 组件挂载时订阅消息
onMounted(() => {
  logger.info('组件挂载，开始监听旧版 Message，并渲染生命周期弹窗队列')

  // 保留旧 Message 类型订阅（注意大写 M）
  legacySubscriptionId = subscribe({ type: 'Message' }, handleMessage)

  // 工具箱异步错误通知（此前全库无订阅者，后端推送后用户"无反应"）
  toolkitNoticeSubscriptionId = subscribe(
    { id: WS_ID_ARKNIGHTS_TOOLKIT, type: WS_TOOLKIT_NOTICE },
    handleToolkitNotice
  )

  logger.info(
    `旧版弹窗订阅ID: ${legacySubscriptionId}, 工具箱通知订阅ID: ${toolkitNoticeSubscriptionId}`
  )

  // 暴露调试接口到 window 对象（仅用于开发调试）
  window.__debugShowQuestion = showQuestion
  logger.debug('已暴露调试接口: window.__debugShowQuestion')
})

// 组件卸载时取消订阅
onUnmounted(() => {
  logger.info('组件卸载，停止监听新旧弹窗消息与工具箱通知')
  if (legacySubscriptionId) unsubscribe(legacySubscriptionId)
  if (toolkitNoticeSubscriptionId) unsubscribe(toolkitNoticeSubscriptionId)
  // 清理调试接口
  delete window.__debugShowQuestion
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
