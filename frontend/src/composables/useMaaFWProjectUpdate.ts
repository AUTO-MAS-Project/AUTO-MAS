/**
 * MaaFW 项目自动更新的纯逻辑：旧配置 → 自动更新时机的映射、更新结果里的
 * CDK 状态 → 页面提示。不依赖 Vue 实例，便于单测；页面组件只负责套 i18n 文案。
 */

import type { MaaFWAutoUpdateMode } from '@/types/script'

export type { MaaFWAutoUpdateMode }

export const MAAFW_AUTO_UPDATE_MODES: readonly MaaFWAutoUpdateMode[] = [
  'Off',
  'BeforeRun',
  'AfterRun',
] as const

export const isMaaFWAutoUpdateMode = (value: unknown): value is MaaFWAutoUpdateMode =>
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

export type MaaFWCdkStatus =
  | 'ok'
  | 'absent'
  | 'expired'
  | 'invalid'
  | 'quota'
  | 'mismatched'
  | 'blocked'

/** 这两种状态不是用户需要处理的问题：没填 CDK 时后端会自动改走 GitHub。 */
const CDK_SILENT_STATUSES: ReadonlySet<string> = new Set(['ok', 'absent'])

export interface MaaFWCdkResultLike {
  cdkStatus?: string | null
  cdkMessage?: string | null
  cdkExpiredTime?: number | string | null
}

export interface MaaFWCdkWarning {
  status: string
  /** 后端给的中文一句话；可能为空，页面需要兜底文案。 */
  message: string
}

/**
 * `cdkStatus` 不是 ok / absent 时返回需要用 warning 展示的内容，否则返回 null。
 */
export const resolveCdkWarning = (
  result: MaaFWCdkResultLike | null | undefined
): MaaFWCdkWarning | null => {
  const status = typeof result?.cdkStatus === 'string' ? result.cdkStatus.trim() : ''
  if (!status || CDK_SILENT_STATUSES.has(status)) return null
  const message = typeof result?.cdkMessage === 'string' ? result.cdkMessage.trim() : ''
  return { status, message }
}

export interface MaaFWCdkExpiry {
  /** 到期时间（本地时区），供页面格式化。 */
  expiresAt: Date
  /** 距今剩余天数，向上取整；已过期为 0 或负数。 */
  daysLeft: number
  /** `YYYY-MM-DD`（本地时区）。 */
  dateText: string
}

const DAY_MS = 24 * 60 * 60 * 1000

const pad2 = (value: number) => String(value).padStart(2, '0')

const toLocalDateText = (date: Date) =>
  `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`

/**
 * `cdkExpiredTime`（unix 秒）距今不超过 `withinDays` 天时返回到期信息，否则返回 null。
 * 后端没给、给了非数字或非正数时一律视为不提示。
 */
export const resolveCdkExpiry = (
  result: MaaFWCdkResultLike | null | undefined,
  now: number = Date.now(),
  withinDays = 7
): MaaFWCdkExpiry | null => {
  const raw = result?.cdkExpiredTime
  const seconds = typeof raw === 'string' ? Number(raw) : raw
  if (typeof seconds !== 'number' || !Number.isFinite(seconds) || seconds <= 0) return null
  const expiresAtMs = seconds * 1000
  const daysLeft = Math.ceil((expiresAtMs - now) / DAY_MS)
  if (daysLeft > withinDays) return null
  const expiresAt = new Date(expiresAtMs)
  return { expiresAt, daysLeft, dateText: toLocalDateText(expiresAt) }
}
