//   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
//   Copyright © 2025-2026 AUTO-MAS Team

import { useI18n } from 'vue-i18n'

/**
 * 状态值 → 词表 key 的映射。
 *
 * 这些中文**同时也是程序的判定依据**（后端 `app/models/task.py` 的
 * `UserItem/ScriptItem.status`，以及前端 `SchedulerStatus`），全仓有近百处
 * `=== '运行'` 这类比较。所以值本身一个字都不能改，只在渲染的那一刻换成
 * 当前语言的标签；比较逻辑继续比中文，行为完全不变。
 *
 * 两套词汇的取值不重叠，因此共用一张表：
 * - 等待 / 运行 / 完成 / 异常：后端任务状态
 * - 空闲 / 运行 / 结束 / 异常：调度台标签状态
 */
const STATUS_KEY: Record<string, string> = {
  等待: 'waiting',
  运行: 'running',
  完成: 'done',
  异常: 'error',
  空闲: 'idle',
  结束: 'finished',
}

/**
 * 取状态值对应的显示标签。
 *
 * 表里没有的值原样返回——后端将来新增状态时宁可显示原文，也不要显示空白。
 */
export function useStatusLabel(): (raw: string | null | undefined) => string {
  const { t } = useI18n()
  return (raw: string | null | undefined): string => {
    if (!raw) return ''
    const key = STATUS_KEY[raw]
    return key ? t(`status.${key}`) : raw
  }
}
