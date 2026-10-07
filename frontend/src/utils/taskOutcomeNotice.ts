/**
 * 任务终态（TaskOutcome）到用户可感知提示的唯一映射。
 *
 * 报告要求「每个专项复制一套结果判断」属于伪整改：页面只判断终态分类，
 * 文案与恢复路径统一在这里维护。关键约束：读不到 taskOutcome 一律按
 * unknown 处理，绝不因为「请求返回成功」就提示成功。
 */

import { message, notification } from 'ant-design-vue'

import type { TaskOutcome } from '@/api'
import { showConfigDiscardWarning } from '@/utils/configSessionDiscard'

/** 终态的用户可感知分类 */
export type TaskOutcomeNoticeKind =
  | 'unknown'
  | 'saved'
  | 'discarded'
  | 'failed'
  | 'cancelled'
  | 'completed'
  | 'without_write'

const KIND_BY_OUTCOME: Record<string, TaskOutcomeNoticeKind> = {
  saved: 'saved',
  discarded: 'discarded',
  failed: 'failed',
  cancelled: 'cancelled',
  completed: 'completed',
  completed_without_write: 'without_write',
}

/** 终态分类；没有 taskOutcome（旧后端、结果未确认）时返回 unknown */
export const taskOutcomeNoticeKind = (
  taskOutcome: TaskOutcome | null | undefined
): TaskOutcomeNoticeKind =>
  taskOutcome ? (KIND_BY_OUTCOME[taskOutcome.outcome] ?? 'unknown') : 'unknown'

type Translate = (key: string, named?: Record<string, unknown>) => string

export interface TaskOutcomeNoticeOptions {
  /** 只读查看会话：未写入是预期行为，不再提示 */
  viewOnly?: boolean
  /** 已保存时的成功文案（缺省用 taskOutcome.saved） */
  savedMessageKey?: string
  savedMessageParams?: Record<string, unknown>
  /** 非配置任务成功完成（completed）时的成功文案；不传则静默 */
  completedMessageKey?: string
  completedMessageParams?: Record<string, unknown>
  /** 调用方已用别的通道报过失败（如 task.notice 的 error），避免重复提示 */
  failureAlreadyReported?: boolean
}

/**
 * 按终态给出用户可见提示并返回分类。
 *
 * saved 提示已保存、discarded 弹丢弃原因与恢复路径、failed 提示失败、
 * completed_without_write 在编辑会话下明确「未写入」、cancelled 静默、
 * unknown 提示「无法确认结果」并引导查询，绝不显示成功。
 */
export const notifyTaskOutcome = (
  t: Translate,
  taskOutcome: TaskOutcome | null | undefined,
  options: TaskOutcomeNoticeOptions = {}
): TaskOutcomeNoticeKind => {
  const kind = taskOutcomeNoticeKind(taskOutcome)

  if (kind === 'saved') {
    message.success(t(options.savedMessageKey ?? 'taskOutcome.saved', options.savedMessageParams))
    return kind
  }
  if (kind === 'discarded') {
    showConfigDiscardWarning(t, taskOutcome?.reason ?? 'unknown')
    return kind
  }
  if (kind === 'failed') {
    if (!options.failureAlreadyReported) message.error(t('taskOutcome.failed'))
    return kind
  }
  if (kind === 'without_write') {
    if (!options.viewOnly) message.info(t('taskOutcome.completedWithoutWrite'))
    return kind
  }
  if (kind === 'completed') {
    if (options.completedMessageKey) {
      message.success(t(options.completedMessageKey, options.completedMessageParams))
    }
    return kind
  }
  if (kind === 'unknown') {
    notification.warning({
      message: t('resultUnknown.title'),
      description: t('resultUnknown.description'),
    })
  }
  // cancelled：用户主动停止，静默收尾
  return kind
}
