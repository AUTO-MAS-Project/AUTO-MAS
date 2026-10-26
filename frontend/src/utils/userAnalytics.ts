import { beginAnalyticsOperation } from './analytics'
import type { AnalyticsScriptType } from '@/types/analytics'

type UserState = { Status?: boolean | null; Base?: string | null }
const users = new Map<string, UserState>()
export function rememberUserAnalytics(
  scriptId: string,
  userId: string,
  info: UserState | null | undefined
) {
  const key = scriptId + ':' + userId
  if (!users.has(key) && users.size >= 128) users.delete(users.keys().next().value!)
  users.set(key, { Status: info?.Status, Base: info?.Base })
}
/** 只比较 MAS 自己的启用和配置来源；整表保存中未变的值不重复计作切换。 */
export function beginUserChanges(
  scriptId: string,
  userId: string,
  script_type: AnalyticsScriptType,
  info: UserState | null | undefined
) {
  const previous = users.get(scriptId + ':' + userId)
  const status =
    typeof info?.Status === 'boolean' && previous?.Status !== info.Status
      ? beginAnalyticsOperation('user_manage_finished')
      : null
  const base =
    typeof info?.Base === 'string' && previous?.Base !== info.Base
      ? beginAnalyticsOperation('config_mode_changed')
      : null
  const modes = { shared: 'script', independent: 'user', native: 'native' } as const
  return (outcome: 'success' | 'failure' | 'blocked') => {
    status?.finish({
      action: info?.Status ? 'enable' : 'disable',
      script_type,
      count_bucket: '1',
      outcome,
    })
    base?.finish({
      script_type,
      mode: modes[info?.Base as keyof typeof modes] ?? 'unknown',
      outcome,
    })
    if (outcome === 'success') rememberUserAnalytics(scriptId, userId, { ...previous, ...info })
  }
}
