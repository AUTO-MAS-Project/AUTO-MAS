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
 * 旧版运行后选项映射为运行前，否则保留合法值（与后端一致）。旧版的
 * `IfAutoUpdate` 开关由后端加载配置时迁成 `AutoUpdateMode`，前端读不到它。
 *
 * 只做读取映射，不回写。
 */
export const resolveAutoUpdateMode = (
  update: { AutoUpdateMode?: unknown } | null | undefined
): MaaFWAutoUpdateMode => {
  if (update?.AutoUpdateMode === 'AfterRun') return 'BeforeRun'
  if (isMaaFWAutoUpdateMode(update?.AutoUpdateMode)) return update.AutoUpdateMode
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

export {
  resolveCdkHint,
  CDK_EXPIRY_WARNING_DAYS,
  type MirrorCdkHint as MaaFWCdkHint,
  type MirrorCdkHintKind as MaaFWCdkHintKind,
} from '@/utils/mirrorCdk'
