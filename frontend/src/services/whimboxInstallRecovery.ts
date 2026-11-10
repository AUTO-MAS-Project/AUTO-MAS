// 应用级 Whimbox 安装恢复询问：首条主连接之前常驻订阅，避免路由切换漏掉请求。
// 一次只能处理一个弹窗，后续请求排队；断线或后端关闭请求时立即清除旧选择。

import { ref } from 'vue'
import { onConnected, onDisconnected, send } from '@/services/websocket/connection'
import { subscribe, unsubscribe } from '@/services/websocket/subscriptions'
import {
  WS_WHIMBOX_INSTALL_DECISION,
  WS_WHIMBOX_INSTALL_PROMPT,
  WS_WHIMBOX_INSTALL_PROMPT_CLOSED,
  WS_ID_TASK_MANAGER,
  type WSWhimboxInstallPromptData,
} from '@/services/websocket/types'

const logger = window.electronAPI.getLogger('Whimbox安装恢复')
export const whimboxInstallPrompts = ref<WSWhimboxInstallPromptData[]>([])
export const whimboxInstallDecisionPending = ref<string | null>(null)

let subscriptionIds: string[] = []
let disposeDisconnect: (() => void) | null = null
let disposeConnect: (() => void) | null = null

const forgetRequest = (requestId: string) => {
  whimboxInstallPrompts.value = whimboxInstallPrompts.value.filter(
    prompt => prompt.requestId !== requestId
  )
  if (whimboxInstallDecisionPending.value === requestId) {
    whimboxInstallDecisionPending.value = null
  }
}

export function bootstrapWhimboxInstallRecovery(): void {
  if (subscriptionIds.length) return
  subscriptionIds = [
    subscribe({ id: WS_ID_TASK_MANAGER, type: WS_WHIMBOX_INSTALL_PROMPT }, message => {
      const prompt = message.data
      if (
        !prompt.requestId ||
        !prompt.taskId ||
        whimboxInstallPrompts.value.some(previous => previous.requestId === prompt.requestId)
      ) {
        return
      }
      whimboxInstallPrompts.value.push(prompt)
    }),
    subscribe({ id: WS_ID_TASK_MANAGER, type: WS_WHIMBOX_INSTALL_PROMPT_CLOSED }, message => {
      forgetRequest(message.data.requestId)
    }),
  ]
  disposeDisconnect = onDisconnected(() => {
    whimboxInstallPrompts.value = []
    whimboxInstallDecisionPending.value = null
  })
  // reconnectNow 在切换连接代次时不会触发 onDisconnected。
  // 新连接建立后，旧连接的关闭帧可能已丢失；绝不可沿用旧确认请求。
  disposeConnect = onConnected(() => {
    whimboxInstallPrompts.value = []
    whimboxInstallDecisionPending.value = null
  })
}

export function respondToWhimboxInstallRecovery(
  action: 'retry' | 'skip' | 'stop' | 'repair_gui'
): boolean {
  const prompt = whimboxInstallPrompts.value[0]
  if (!prompt || whimboxInstallDecisionPending.value) return false
  const sent = send(WS_ID_TASK_MANAGER, WS_WHIMBOX_INSTALL_DECISION, {
    requestId: prompt.requestId,
    taskId: prompt.taskId,
    action,
  })
  if (!sent) {
    logger.warn('未能发送 Whimbox 安装恢复选择')
    return false
  }
  whimboxInstallDecisionPending.value = prompt.requestId
  return true
}

export function disposeWhimboxInstallRecovery(): void {
  for (const id of subscriptionIds.splice(0)) unsubscribe(id)
  disposeDisconnect?.()
  disposeDisconnect = null
  disposeConnect?.()
  disposeConnect = null
  whimboxInstallPrompts.value = []
  whimboxInstallDecisionPending.value = null
}
