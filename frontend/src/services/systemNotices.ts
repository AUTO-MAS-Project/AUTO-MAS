// 系统级通知常驻订阅
// 模拟器管理与明日方舟工具箱的错误提示不属于任何任务或页面，由应用级常驻
// 订阅统一弹出通知（v1.1 由全量 Message 订阅承担，v2 精确路由后需显式订阅）。

import { notification } from 'ant-design-vue'
import { subscribe, unsubscribe } from '@/services/websocket/subscriptions'
import {
  WS_EMULATOR_NOTICE,
  WS_ID_ARKNIGHTS_PC_TOOLKIT,
  WS_ID_EMULATOR_MANAGER,
  WS_TOOLKIT_NOTICE,
  type WSTaskNoticeData,
} from '@/services/websocket/types'

let subscriptionIds: string[] = []

const showNotice = (title: string, data: WSTaskNoticeData): void => {
  if (data.level === 'error') {
    notification.error({ message: title, description: data.message })
  } else if (data.level === 'warning') {
    notification.warning({ message: title, description: data.message })
  } else {
    notification.info({ message: title, description: data.message })
  }
}

/** 注册系统级通知订阅（幂等），必须在首个主连接建立前调用。 */
export function bootstrapSystemNotices(): void {
  if (subscriptionIds.length > 0) return
  subscriptionIds = [
    subscribe({ id: WS_ID_EMULATOR_MANAGER, type: WS_EMULATOR_NOTICE }, message =>
      showNotice('模拟器管理', message.data)
    ),
    subscribe({ id: WS_ID_ARKNIGHTS_PC_TOOLKIT, type: WS_TOOLKIT_NOTICE }, message =>
      showNotice('明日方舟工具箱', message.data)
    ),
  ]
}

/** 释放系统级通知订阅（幂等）。 */
export function disposeSystemNotices(): void {
  for (const subscriptionId of subscriptionIds.splice(0)) {
    unsubscribe(subscriptionId)
  }
}
