/**
 * MaaFW 项目自动更新的纯逻辑：旧配置 → 自动更新时机的映射、更新结果里的
 * CDK 状态 → 页面提示、CDK 状态查询 → 输入框下的剩余时间小字。不依赖 Vue 实例，
 * 便于单测；页面组件只负责套 i18n 文案。
 */

import type { MaaFWAutoUpdateMode } from '@/types/script'

export type { MaaFWAutoUpdateMode }

const MAAFW_AUTO_UPDATE_MODES: readonly MaaFWAutoUpdateMode[] = [
  'Off',
  'BeforeRun',
  'AfterRun',
] as const

const isMaaFWAutoUpdateMode = (value: unknown): value is MaaFWAutoUpdateMode =>
  typeof value === 'string' && (MAAFW_AUTO_UPDATE_MODES as readonly string[]).includes(value)

/**
 * 从后端返回的 Update 段解析自动更新时机。
 *
 * - 新字段 `AutoUpdateMode` 合法时直接采用；
 * - 旧配置只有 `IfAutoUpdate`：`false` → 不更新，`true` / 缺失 → 运行前（与后端默认一致）。
 *
 * 只做读取映射，不回写：旧配置在用户改动之前保持原样。
 */
export const resolveAutoUpdateMode = (
  update: { AutoUpdateMode?: unknown; IfAutoUpdate?: unknown } | null | undefined
): MaaFWAutoUpdateMode => {
  if (isMaaFWAutoUpdateMode(update?.AutoUpdateMode)) return update.AutoUpdateMode
  if (update?.IfAutoUpdate === false) return 'Off'
  return 'BeforeRun'
}

/** 项目更新的下载源；与 MaaFWScriptConfig['Update']['Source'] 一致。 */
type MaaFWUpdateSource = 'MirrorChyan' | 'GitHub'

interface MaaFWCdkResultLike {
  cdkStatus?: string | null
  cdkMessage?: string | null
}

interface MaaFWCdkWarning {
  status: string
  /** 后端给的中文一句话；可能为空，页面需要兜底文案。 */
  message: string
}

/**
 * `cdkStatus` 有问题时返回需要用 warning 展示的内容，否则返回 null。
 *
 * - `ok` 永远不提示；
 * - `absent` 只在更新源是 Mirror 酱时才是问题：没填 CDK 就下不了，后端不会替用户
 *   改走 GitHub。更新源是 GitHub 时 CDK 不参与下载，缺失不提示；
 * - 其余状态（过期 / 错误 / 次数用尽 / 类型不符 / 封禁）一律提示，文案优先用后端给的。
 */
export const resolveCdkWarning = (
  result: MaaFWCdkResultLike | null | undefined,
  source?: MaaFWUpdateSource | string | null
): MaaFWCdkWarning | null => {
  const status = typeof result?.cdkStatus === 'string' ? result.cdkStatus.trim() : ''
  if (!status || status === 'ok') return null
  if (status === 'absent' && source !== 'MirrorChyan') return null
  const message = typeof result?.cdkMessage === 'string' ? result.cdkMessage.trim() : ''
  return { status, message }
}

/**
 * CDK 输入框下那行小字的种类：
 * - `remaining`：CDK 正常，显示剩余天数与到期日期；
 * - `expired`：已过期（服务端 7001，或到期时间已过）；
 * - `invalid` / `quota` / `mismatched` / `blocked`：服务端 7002 / 7003 / 7004 / 7005。
 */
export type MaaFWCdkHintKind =
  | 'remaining'
  | 'expired'
  | 'invalid'
  | 'quota'
  | 'mismatched'
  | 'blocked'

export interface MaaFWCdkHint {
  kind: MaaFWCdkHintKind
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

const CDK_PROBLEM_KINDS: Record<string, MaaFWCdkHintKind> = {
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
 * 按 `/maafw/mirror-cdk` 的结果决定 CDK 输入框下显示什么；返回 null 就什么都不显示
 * （没填、项目不支持、查询失败、CDK 正常但服务端没给到期时间）。
 *
 * 剩余天数按本地时区的整天算：到期日减今天，今天到期记 0（页面写「不足 1 天」）。
 * `expiredTime` 是 unix 秒，非正数或非数字视为不知道。
 */
export const resolveCdkHint = (
  status: string | null | undefined,
  expiredTime: number | string | null | undefined,
  now: number = Date.now()
): MaaFWCdkHint | null => {
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
