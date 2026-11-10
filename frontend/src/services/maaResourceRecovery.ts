// 应用级 MAA 安装恢复询问：首条主连接之前常驻订阅，避免路由切换漏掉请求。
// 一次只能处理一个弹窗，后续请求排队；断线或后端关闭请求时立即清除旧选择。

import { ref } from 'vue'
import { onConnected, onDisconnected, send } from '@/services/websocket/connection'
import { subscribe, unsubscribe } from '@/services/websocket/subscriptions'
import {
  WS_MAA_RESOURCE_RECOVERY_DECISION,
  WS_MAA_RESOURCE_RECOVERY_PROMPT,
  WS_MAA_RESOURCE_RECOVERY_CLOSED,
  WS_ID_TASK_MANAGER,
  type WSMAAResourceRecoveryPromptData,
} from '@/services/websocket/types'

const logger = window.electronAPI.getLogger('MAA安装恢复')
export const maaResourceRecoveryPrompts = ref<WSMAAResourceRecoveryPromptData[]>([])
export const maaResourceRecoveryDecisionPending = ref<string | null>(null)

let subscriptionIds: string[] = []
let disposeDisconnect: (() => void) | null = null
let disposeConnect: (() => void) | null = null

const forgetRequest = (requestId: string) => {
  maaResourceRecoveryPrompts.value = maaResourceRecoveryPrompts.value.filter(
    prompt => prompt.requestId !== requestId
  )
  if (maaResourceRecoveryDecisionPending.value === requestId) {
    maaResourceRecoveryDecisionPending.value = null
  }
}

export function bootstrapMAAResourceRecovery(): void {
  if (subscriptionIds.length) return
  subscriptionIds = [
    subscribe({ id: WS_ID_TASK_MANAGER, type: WS_MAA_RESOURCE_RECOVERY_PROMPT }, message => {
      const prompt = message.data
      if (
        !prompt.requestId ||
        !prompt.taskId ||
        maaResourceRecoveryPrompts.value.some(previous => previous.requestId === prompt.requestId)
      ) {
        return
      }
      maaResourceRecoveryPrompts.value.push(prompt)
    }),
    subscribe({ id: WS_ID_TASK_MANAGER, type: WS_MAA_RESOURCE_RECOVERY_CLOSED }, message => {
      forgetRequest(message.data.requestId)
    }),
  ]
  disposeDisconnect = onDisconnected(() => {
    maaResourceRecoveryPrompts.value = []
    maaResourceRecoveryDecisionPending.value = null
  })
  // reconnectNow 在切换连接代次时不会触发 onDisconnected。
  // 新连接建立后，旧连接的关闭帧可能已丢失；绝不可沿用旧确认请求。
  disposeConnect = onConnected(() => {
    maaResourceRecoveryPrompts.value = []
    maaResourceRecoveryDecisionPending.value = null
  })
}

export function respondToMAAResourceRecovery(action: 'retry' | 'stop'): boolean {
  const prompt = maaResourceRecoveryPrompts.value[0]
  if (!prompt || maaResourceRecoveryDecisionPending.value) return false
  const sent = send(WS_ID_TASK_MANAGER, WS_MAA_RESOURCE_RECOVERY_DECISION, {
    requestId: prompt.requestId,
    taskId: prompt.taskId,
    action,
  })
  if (!sent) {
    logger.warn('未能发送 MAA 安装恢复选择')
    return false
  }
  maaResourceRecoveryDecisionPending.value = prompt.requestId
  return true
}

export function disposeMAAResourceRecovery(): void {
  for (const id of subscriptionIds.splice(0)) unsubscribe(id)
  disposeDisconnect?.()
  disposeDisconnect = null
  disposeConnect?.()
  disposeConnect = null
  maaResourceRecoveryPrompts.value = []
  maaResourceRecoveryDecisionPending.value = null
}
