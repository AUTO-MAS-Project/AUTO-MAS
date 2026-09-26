// 系统级通知常驻订阅
// 模拟器管理与明日方舟工具箱的错误提示不属于任何任务或页面，由应用级常驻
// 订阅统一弹出通知（v1.1 由全量 Message 订阅承担，v2 精确路由后需显式订阅）。
// 后端启动期攒下的系统通知（如 M9A 配置迁移结果）也走这里：主连接建立后发一次，
// 正文是多行，逐行显示。

import { h } from 'vue'
import { notification } from 'ant-design-vue'
import { subscribe, unsubscribe } from '@/services/websocket/subscriptions'
import {
  WS_EMULATOR_NOTICE,
  WS_ID_ARKNIGHTS_PC_TOOLKIT,
  WS_ID_EMULATOR_MANAGER,
  WS_ID_MAIN,
  WS_SYSTEM_NOTICE,
  WS_TOOLKIT_NOTICE,
  type WSSystemNoticeData,
  type WSTaskNoticeData,
} from '@/services/websocket/types'

let subscriptionIds: string[] = []

type NoticeLevel = WSTaskNoticeData['level']
type NoticeDescription = string | (() => ReturnType<typeof h>)

const notify = (level: NoticeLevel, title: string, description: NoticeDescription): void => {
  const args = { message: title, description }
  if (level === 'error') {
    notification.error(args)
  } else if (level === 'warning') {
    notification.warning(args)
  } else {
    notification.info(args)
  }
}

const showNotice = (title: string, data: WSTaskNoticeData): void => {
  notify(data.level, title, data.message)
}

// 迁移结果这类通知一条里有好几行（迁了哪些脚本、停用了谁、丢了什么），
// 用户要能读完才关，所以不自动消失；行数多时给个滚动条而不是撑满屏
const showSystemNotice = (data: WSSystemNoticeData): void => {
  const lines = (data.lines ?? []).filter(line => typeof line === 'string' && line.trim())
  const description = () =>
    h(
      'div',
      { style: { maxHeight: '60vh', overflowY: 'auto', whiteSpace: 'pre-wrap' } },
      lines.map((line, index) => h('div', { key: index }, line))
    )
  const args = { message: data.title, description, duration: null }
  if (data.level === 'error') {
    notification.error(args)
  } else if (data.level === 'warning') {
    notification.warning(args)
  } else {
    notification.info(args)
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
    subscribe({ id: WS_ID_MAIN, type: WS_SYSTEM_NOTICE }, message =>
      showSystemNotice(message.data)
    ),
  ]
}

/** 释放系统级通知订阅（幂等）。 */
export function disposeSystemNotices(): void {
  for (const subscriptionId of subscriptionIds.splice(0)) {
    unsubscribe(subscriptionId)
  }
}
