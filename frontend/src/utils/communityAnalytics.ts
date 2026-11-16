import type { GameSignAccountGroupConfig, OutBase } from '@/api'
import { apiOutcome } from './featureAnalytics'

/** 明确的总体结果口径；不解析签到正文或凭据，也不推断逐平台完成。 */
export function communitySignOutcome(result: OutBase) {
  return result.code === 200 && result.status === 'warning'
    ? ('partial' as const)
    : apiOutcome(result)
}
export function communityAccountAction(data: GameSignAccountGroupConfig) {
  // 当前独立启停入口只提交 Enabled；编辑凭据的整组保存仍计作 save。
  return Object.keys(data).length === 1 && typeof data.Enabled === 'boolean'
    ? data.Enabled
      ? ('enable' as const)
      : ('disable' as const)
    : ('save' as const)
}
