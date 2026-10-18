// 虚拟显示器询问弹窗的常驻订阅
// 真实显示器回来了但有任务在跑，后端不拆虚拟屏、改为问用户。此时虚拟屏是主显示器，
// 主窗口和任务栏都在看不见的那块上，所以弹窗不能画在主窗口里，得由主进程另开一个
// 窗口放到回来的那块屏右下角——渲染进程这里只负责把消息转给主进程。

import { subscribe, unsubscribe } from '@/services/websocket/subscriptions'
import {
  WS_DISPLAY_DETACH_PROMPT,
  WS_DISPLAY_DETACH_PROMPT_CLOSED,
  WS_ID_MAIN,
  type WSDisplayDetachPromptData,
} from '@/services/websocket/types'

const logger = window.electronAPI.getLogger('虚拟显示器提示')

let subscriptionIds: string[] = []

const showPrompt = async (data: WSDisplayDetachPromptData): Promise<void> => {
  logger.info(`真实显示器已恢复（${data.returned.join(', ')}），有任务在跑，弹窗询问是否拆除虚拟屏`)
  try {
    await window.electronAPI.showVirtualDisplayPrompt?.(data)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.warn(`打开虚拟显示器询问弹窗失败: ${errorMsg}`)
  }
}

const closePrompt = async (): Promise<void> => {
  try {
    await window.electronAPI.closeVirtualDisplayPrompt?.()
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.warn(`关闭虚拟显示器询问弹窗失败: ${errorMsg}`)
  }
}

/** 注册虚拟显示器询问订阅（幂等），必须在首个主连接建立前调用。 */
export function bootstrapVirtualDisplayPrompt(): void {
  if (subscriptionIds.length > 0) return
  subscriptionIds = [
    subscribe({ id: WS_ID_MAIN, type: WS_DISPLAY_DETACH_PROMPT }, message => {
      void showPrompt(message.data)
    }),
    subscribe({ id: WS_ID_MAIN, type: WS_DISPLAY_DETACH_PROMPT_CLOSED }, () => {
      void closePrompt()
    }),
  ]
}

/** 释放虚拟显示器询问订阅（幂等）。 */
export function disposeVirtualDisplayPrompt(): void {
  for (const subscriptionId of subscriptionIds.splice(0)) {
    unsubscribe(subscriptionId)
  }
}
