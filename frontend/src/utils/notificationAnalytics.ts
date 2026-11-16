import { beginAnalyticsOperation } from './analytics'
import type { AnalyticsNotificationChannel } from '@/types/analytics'

const channelFields: Record<string, AnalyticsNotificationChannel> = {
  IfPushPlyer: 'system',
  IfSendMail: 'mail',
  IfServerChan: 'serverchan',
  IfCMCCNewMsg: 'cmcc',
  IfKoishiSupport: 'koishi',
  IfOpenClawQQ: 'openclaw_qq',
}

/** 只观察内置渠道布尔开关的实际写入；不遍历或转发通知配置内容。 */
export function beginNotificationChannelChanges(notify: object | null | undefined) {
  return Object.entries(channelFields).flatMap(([field, channel_kind]) => {
    const enabled = notify && Reflect.get(notify, field)
    if (typeof enabled !== 'boolean') return []
    const operation = beginAnalyticsOperation('notification_channel_changed')
    const action = enabled ? ('enable' as const) : ('disable' as const)
    return [(outcome: 'success' | 'failure') => operation.finish({ channel_kind, action, outcome })]
  })
}
