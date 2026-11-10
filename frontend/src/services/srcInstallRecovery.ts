// 应用级 Src 安装恢复询问：首条主连接之前常驻订阅，避免路由切换漏掉请求。
// 一次只能处理一个弹窗，后续请求排队；断线或后端关闭请求时立即清除旧选择。

import { ref } from 'vue'
import { onConnected, onDisconnected, send } from '@/services/websocket/connection'
import { subscribe, unsubscribe } from '@/services/websocket/subscriptions'
import {
  WS_SRC_INSTALL_DECISION,
  WS_SRC_INSTALL_PROMPT,
  WS_SRC_INSTALL_PROMPT_CLOSED,
  WS_ID_TASK_MANAGER,
  type WSSrcInstallPromptData,
} from '@/services/websocket/types'

const logger = window.electronAPI.getLogger('Src安装恢复')
export const srcInstallPrompts = ref<WSSrcInstallPromptData[]>([])
export const srcInstallDecisionPending = ref<string | null>(null)

let subscriptionIds: string[] = []
let disposeDisconnect: (() => void) | null = null
let disposeConnect: (() => void) | null = null

const forgetRequest = (requestId: string) => {
  srcInstallPrompts.value = srcInstallPrompts.value.filter(prompt => prompt.requestId !== requestId)
  if (srcInstallDecisionPending.value === requestId) {
    srcInstallDecisionPending.value = null
  }
}

export function bootstrapSrcInstallRecovery(): void {
  if (subscriptionIds.length) return
  subscriptionIds = [
    subscribe({ id: WS_ID_TASK_MANAGER, type: WS_SRC_INSTALL_PROMPT }, message => {
      const prompt = message.data
      if (
        !prompt.requestId ||
        !prompt.taskId ||
        srcInstallPrompts.value.some(previous => previous.requestId === prompt.requestId)
      ) {
        return
      }
      srcInstallPrompts.value.push(prompt)
    }),
    subscribe({ id: WS_ID_TASK_MANAGER, type: WS_SRC_INSTALL_PROMPT_CLOSED }, message => {
      forgetRequest(message.data.requestId)
    }),
  ]
  disposeDisconnect = onDisconnected(() => {
    srcInstallPrompts.value = []
    srcInstallDecisionPending.value = null
  })
  // reconnectNow 在切换连接代次时不会触发 onDisconnected。
  // 新连接建立后，旧连接的关闭帧可能已丢失；绝不可沿用旧确认请求。
  disposeConnect = onConnected(() => {
    srcInstallPrompts.value = []
    srcInstallDecisionPending.value = null
  })
}

export function respondToSrcInstallRecovery(action: 'retry' | 'skip' | 'stop'): boolean {
  const prompt = srcInstallPrompts.value[0]
  if (!prompt || srcInstallDecisionPending.value) return false
  const sent = send(WS_ID_TASK_MANAGER, WS_SRC_INSTALL_DECISION, {
    requestId: prompt.requestId,
    taskId: prompt.taskId,
    action,
  })
  if (!sent) {
    logger.warn('未能发送 Src 安装恢复选择')
    return false
  }
  srcInstallDecisionPending.value = prompt.requestId
  return true
}

export function disposeSrcInstallRecovery(): void {
  for (const id of subscriptionIds.splice(0)) unsubscribe(id)
  disposeDisconnect?.()
  disposeDisconnect = null
  disposeConnect?.()
  disposeConnect = null
  srcInstallPrompts.value = []
  srcInstallDecisionPending.value = null
}
