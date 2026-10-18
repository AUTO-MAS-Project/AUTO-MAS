/**
 * 原生 GUI 配置会话「本次改动被丢弃」的共用判定与提示。
 *
 * 后端收尾时若判定本次 GUI 改动不能生效（队列结构或配置方案被改、配置读不出
 * 或从未写过），会下发 task.config.discarded；该帧由收尾过程发出，与停止响应
 * 分属两条链路，到达顺序不保证。脚本级（Scripts.vue）与用户级
 * （useNativeGuiSession）两个入口都要能承受两种顺序，判定与文案统一在此维护。
 */

import { h, type VNode } from 'vue'
import { Modal } from 'ant-design-vue'

/** 丢弃原因 → 正文词条（未知原因按通用文案兜底） */
export const configDiscardReasonKey = (reason: string): string => {
  if (reason === 'structure') return 'edit.configSessionDiscardedStructure'
  if (reason === 'unreadable') return 'edit.configSessionDiscardedUnreadable'
  if (reason === 'not_written') return 'edit.configSessionDiscardedNotWritten'
  return 'edit.configSessionDiscardedUnknown'
}

/** 丢弃提示的正文节点（role=alert；保留文案里的换行，每条都给出恢复路径） */
export const configDiscardContent = (
  t: (key: string, named?: Record<string, string>) => string,
  reason: string
): VNode =>
  h('div', { role: 'alert', style: { whiteSpace: 'pre-wrap' } }, t(configDiscardReasonKey(reason)))

/** 弹出「本次改动被丢弃」提示：遮罩期间弹出，zIndex 抬高以确保盖在配置遮罩之上 */
export const showConfigDiscardWarning = (
  t: (key: string, named?: Record<string, string>) => string,
  reason: string
): void => {
  Modal.warning({
    title: t('edit.configSessionDiscardedTitle'),
    content: configDiscardContent(t, reason),
    okText: t('misc.gotIt'),
    zIndex: 999,
  })
}
