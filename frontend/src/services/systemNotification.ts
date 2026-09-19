// 系统原生通知的常驻订阅
// 后端推送的系统通知（任务完成、失败截图等）由主进程以系统原生通知弹出，
// Windows 上走 Toast、可进通知中心，不再使用会占托盘图标的托盘气泡；
// 渲染进程这里只负责把消息转给主进程。

import { subscribe, unsubscribe } from '@/services/websocket/subscriptions'
import { WS_ID_MAIN, WS_SYSTEM_NOTICE, type WSSystemNoticeData } from '@/services/websocket/types'

const logger = window.electronAPI.getLogger('系统通知')

let subscriptionIds: string[] = []

const showNotice = async (data: WSSystemNoticeData): Promise<void> => {
  try {
    await window.electronAPI.systemNotify?.({ title: data.title, message: data.message })
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.warn(`弹出系统通知失败: ${errorMsg}`)
  }
}

/** 注册系统通知订阅（幂等），必须在首个主连接建立前调用。 */
export function bootstrapSystemNotification(): void {
  if (subscriptionIds.length > 0) return
  subscriptionIds = [
    subscribe({ id: WS_ID_MAIN, type: WS_SYSTEM_NOTICE }, message => {
      void showNotice(message.data)
    }),
  ]
}

/** 释放系统通知订阅（幂等）。 */
export function disposeSystemNotification(): void {
  for (const subscriptionId of subscriptionIds.splice(0)) {
    unsubscribe(subscriptionId)
  }
}
