// 应用级 HSR 安装恢复询问：首条主连接之前常驻订阅，避免路由切换漏掉请求。
// 一次只能处理一个弹窗，后续请求排队；断线或后端关闭请求时立即清除旧选择。

import { ref } from 'vue'
import { onConnected, onDisconnected, send } from '@/services/websocket/connection'
import { subscribe, unsubscribe } from '@/services/websocket/subscriptions'
import {
  WS_HSR_INSTALL_DECISION,
  WS_HSR_INSTALL_PROMPT,
  WS_HSR_INSTALL_PROMPT_CLOSED,
  WS_ID_TASK_MANAGER,
  type WSHSRInstallPromptData,
} from '@/services/websocket/types'

const logger = window.electronAPI.getLogger('HSR安装恢复')
export const hsrInstallPrompts = ref<WSHSRInstallPromptData[]>([])
export const hsrInstallDecisionPending = ref<string | null>(null)

let subscriptionIds: string[] = []
let disposeDisconnect: (() => void) | null = null
let disposeConnect: (() => void) | null = null

const forgetRequest = (requestId: string) => {
  hsrInstallPrompts.value = hsrInstallPrompts.value.filter(prompt => prompt.requestId !== requestId)
  if (hsrInstallDecisionPending.value === requestId) {
    hsrInstallDecisionPending.value = null
  }
}

export function bootstrapHSRInstallRecovery(): void {
  if (subscriptionIds.length) return
  subscriptionIds = [
    subscribe({ id: WS_ID_TASK_MANAGER, type: WS_HSR_INSTALL_PROMPT }, message => {
      const prompt = message.data
      if (
        !prompt.requestId ||
        !prompt.taskId ||
        hsrInstallPrompts.value.some(previous => previous.requestId === prompt.requestId)
      ) {
        return
      }
      hsrInstallPrompts.value.push(prompt)
    }),
    subscribe({ id: WS_ID_TASK_MANAGER, type: WS_HSR_INSTALL_PROMPT_CLOSED }, message => {
      forgetRequest(message.data.requestId)
    }),
  ]
  disposeDisconnect = onDisconnected(() => {
    hsrInstallPrompts.value = []
    hsrInstallDecisionPending.value = null
  })
  // reconnectNow 在切换连接代次时不会触发 onDisconnected。
  // 新连接建立后，旧连接的关闭帧可能已丢失；绝不可沿用旧确认请求。
  disposeConnect = onConnected(() => {
    hsrInstallPrompts.value = []
    hsrInstallDecisionPending.value = null
  })
}

export function respondToHSRInstallRecovery(action: 'retry' | 'skip' | 'stop'): boolean {
  const prompt = hsrInstallPrompts.value[0]
  if (!prompt || hsrInstallDecisionPending.value) return false
  const sent = send(WS_ID_TASK_MANAGER, WS_HSR_INSTALL_DECISION, {
    requestId: prompt.requestId,
    taskId: prompt.taskId,
    action,
  })
  if (!sent) {
    logger.warn('未能发送 HSR 安装恢复选择')
    return false
  }
  hsrInstallDecisionPending.value = prompt.requestId
  return true
}

export function disposeHSRInstallRecovery(): void {
  for (const id of subscriptionIds.splice(0)) unsubscribe(id)
  disposeDisconnect?.()
  disposeDisconnect = null
  disposeConnect?.()
  disposeConnect = null
  hsrInstallPrompts.value = []
  hsrInstallDecisionPending.value = null
}
