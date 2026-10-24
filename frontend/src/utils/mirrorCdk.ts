/** Mirror 酱 CDK 状态与到期日期的展示规则。 */

/**
 * CDK 输入框下那行小字的种类：
 * - `remaining`：CDK 正常，显示剩余天数与到期日期；
 * - `expired`：已过期（服务端 7001，或到期时间已过）；
 * - `invalid` / `quota` / `mismatched` / `blocked`：服务端 7002 / 7003 / 7004 / 7005。
 */
export type MirrorCdkHintKind =
  | 'remaining'
  | 'expired'
  | 'invalid'
  | 'quota'
  | 'mismatched'
  | 'blocked'

export interface MirrorCdkHint {
  kind: MirrorCdkHintKind
  /** 用警告色：CDK 有问题，或剩余不超过 7 天 */
  warning: boolean
  /**
   * 本地日历上距到期日还有几天；0 表示今天到期（不足 1 天）。
   * 只在到期时间已知且还没到时有（`remaining`，或 `quota` 顺带给出），否则为 null。
   */
  daysLeft: number | null
  /** 到期日期 `YYYY-MM-DD`（本地时区）；不知道到期时间时为 null */
  dateText: string | null
}

/** 剩余天数不超过这个数就用警告色 */
export const CDK_EXPIRY_WARNING_DAYS = 7

const DAY_MS = 24 * 60 * 60 * 1000

const CDK_PROBLEM_KINDS: Record<string, MirrorCdkHintKind> = {
  expired: 'expired',
  invalid: 'invalid',
  quota: 'quota',
  mismatched: 'mismatched',
  blocked: 'blocked',
}

const pad2 = (value: number) => String(value).padStart(2, '0')

const toLocalDateText = (date: Date) =>
  `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`

const startOfLocalDay = (ms: number) => {
  const date = new Date(ms)
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime()
}

/**
 * 按 Mirror 酱 CDK 状态查询的结果决定 CDK 输入框下显示什么；返回 null 就什么都不显示
 * （没填、项目不支持、查询失败、CDK 正常但服务端没给到期时间）。
 *
 * 剩余天数按本地时区的整天算：到期日减今天，今天到期记 0（页面写「不足 1 天」）。
 * `expiredTime` 是 unix 秒，非正数或非数字视为不知道。
 */
export const resolveCdkHint = (
  status: string | null | undefined,
  expiredTime: number | string | null | undefined,
  now: number = Date.now()
): MirrorCdkHint | null => {
  const seconds = typeof expiredTime === 'string' ? Number(expiredTime) : expiredTime
  const expiresAtMs =
    typeof seconds === 'number' && Number.isFinite(seconds) && seconds > 0 ? seconds * 1000 : null
  const dateText = expiresAtMs === null ? null : toLocalDateText(new Date(expiresAtMs))
  const isPast = expiresAtMs !== null && expiresAtMs <= now
  const daysLeft =
    expiresAtMs === null || isPast
      ? null
      : Math.round((startOfLocalDay(expiresAtMs) - startOfLocalDay(now)) / DAY_MS)

  const normalized = typeof status === 'string' ? status.trim() : ''
  if (normalized === 'ok') {
    if (expiresAtMs === null) return null
    if (isPast) return { kind: 'expired', warning: true, daysLeft: null, dateText }
    return {
      kind: 'remaining',
      warning: (daysLeft ?? 0) <= CDK_EXPIRY_WARNING_DAYS,
      daysLeft,
      dateText,
    }
  }
  const kind = CDK_PROBLEM_KINDS[normalized]
  if (!kind) return null
  return {
    kind,
    warning: true,
    daysLeft: kind === 'quota' ? daysLeft : null,
    dateText: kind === 'quota' && daysLeft === null ? null : dateText,
  }
}
