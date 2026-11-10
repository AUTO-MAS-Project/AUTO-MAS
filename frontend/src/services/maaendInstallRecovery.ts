// 应用级 MaaEnd 安装恢复询问：首条主连接之前常驻订阅，避免路由切换漏掉请求。
// 一次只能处理一个弹窗，后续请求排队；断线或后端关闭请求时立即清除旧选择。

import { ref } from 'vue'
import { onConnected, onDisconnected, send } from '@/services/websocket/connection'
import { subscribe, unsubscribe } from '@/services/websocket/subscriptions'
import {
  WS_BETTERGI_INSTALL_DECISION,
  WS_BETTERGI_INSTALL_PROMPT,
  WS_BETTERGI_INSTALL_PROMPT_CLOSED,
  WS_ID_TASK_MANAGER,
  type WSMaaEndInstallPromptData,
} from '@/services/websocket/types'

const logger = window.electronAPI.getLogger('MaaEnd安装恢复')
export const maaendInstallPrompts = ref<WSMaaEndInstallPromptData[]>([])
export const maaendInstallDecisionPending = ref<string | null>(null)

let subscriptionIds: string[] = []
let disposeDisconnect: (() => void) | null = null
let disposeConnect: (() => void) | null = null

const forgetRequest = (requestId: string) => {
  maaendInstallPrompts.value = maaendInstallPrompts.value.filter(
    prompt => prompt.requestId !== requestId
  )
  if (maaendInstallDecisionPending.value === requestId) {
    maaendInstallDecisionPending.value = null
  }
}

export function bootstrapMaaEndInstallRecovery(): void {
  if (subscriptionIds.length) return
  subscriptionIds = [
    subscribe({ id: WS_ID_TASK_MANAGER, type: WS_BETTERGI_INSTALL_PROMPT }, message => {
      const prompt = message.data
      if (
        !prompt.requestId ||
        !prompt.taskId ||
        maaendInstallPrompts.value.some(previous => previous.requestId === prompt.requestId)
      ) {
        return
      }
      maaendInstallPrompts.value.push(prompt)
    }),
    subscribe({ id: WS_ID_TASK_MANAGER, type: WS_BETTERGI_INSTALL_PROMPT_CLOSED }, message => {
      forgetRequest(message.data.requestId)
    }),
  ]
  disposeDisconnect = onDisconnected(() => {
    maaendInstallPrompts.value = []
    maaendInstallDecisionPending.value = null
  })
  // reconnectNow 在切换连接代次时不会触发 onDisconnected。
  // 新连接建立后，旧连接的关闭帧可能已丢失；绝不可沿用旧确认请求。
  disposeConnect = onConnected(() => {
    maaendInstallPrompts.value = []
    maaendInstallDecisionPending.value = null
  })
}

export function respondToMaaEndInstallRecovery(action: 'retry' | 'stop'): boolean {
  const prompt = maaendInstallPrompts.value[0]
  if (!prompt || maaendInstallDecisionPending.value) return false
  const sent = send(WS_ID_TASK_MANAGER, WS_BETTERGI_INSTALL_DECISION, {
    requestId: prompt.requestId,
    taskId: prompt.taskId,
    action,
  })
  if (!sent) {
    logger.warn('未能发送 MaaEnd 安装恢复选择')
    return false
  }
  maaendInstallDecisionPending.value = prompt.requestId
  return true
}

export function disposeMaaEndInstallRecovery(): void {
  for (const id of subscriptionIds.splice(0)) unsubscribe(id)
  disposeDisconnect?.()
  disposeDisconnect = null
  disposeConnect?.()
  disposeConnect = null
  maaendInstallPrompts.value = []
  maaendInstallDecisionPending.value = null
}
