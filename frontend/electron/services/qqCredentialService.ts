import { fetchProtectedLocal } from './protectedBackend'

const routes = {
  status: 'status',
  groups: 'groups',
  target: 'target',
  start: 'login/start',
  check: 'login/check',
  unbind: 'unbind',
  get: 'credentials/get',
  set: 'credentials/set',
} as const
export type QqAction = keyof typeof routes

/** 只向本机后端的固定凭据端点发送主进程持有的令牌。 */
export async function qqCredentials(
  baseUrl: string,
  action: QqAction,
  value?: unknown
): Promise<unknown> {
  if (!Object.prototype.hasOwnProperty.call(routes, action)) throw new Error('无效的 QQ 操作')
  let body: Record<string, unknown> = {}
  if (action === 'set' || action === 'target' || action === 'check') {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      throw new Error('QQ 凭据格式无效')
    }
    const data = value as Record<string, unknown>
    if (
      action === 'set' &&
      (typeof data.bindingId !== 'string' ||
        typeof data.appId !== 'string' ||
        typeof data.userOpenId !== 'string' ||
        (data.clientSecret != null && typeof data.clientSecret !== 'string'))
    ) {
      throw new Error('QQ 凭据格式无效')
    }
    if (action === 'set') {
      body = { bindingId: data.bindingId, appId: data.appId, userOpenId: data.userOpenId }
      if (typeof data.clientSecret === 'string') body.clientSecret = data.clientSecret
    } else if (action === 'target') {
      if (
        typeof data.bindingId !== 'string' ||
        !['c2c', 'group', 'all'].includes(String(data.targetType)) ||
        (data.groupCommandWhitelist != null &&
          (!Array.isArray(data.groupCommandWhitelist) ||
            !data.groupCommandWhitelist.every(item => typeof item === 'string')))
      )
        throw new Error('QQ 接收设置格式无效')
      body = { bindingId: data.bindingId, targetType: data.targetType }
      if (data.groupCommandWhitelist != null)
        body.groupCommandWhitelist = data.groupCommandWhitelist
    } else {
      if (typeof data.sessionId !== 'string') throw new Error('QQ 会话格式无效')
      body = { sessionId: data.sessionId }
    }
  }
  const response = await fetchProtectedLocal(
    baseUrl,
    `/api/setting/openclaw-qq/${routes[action]}`,
    body
  )
  const result: unknown = await response.json()
  if (response.status === 403) throw new Error('QQ 管理未授权，请使用桌面客户端重启后端')
  if (!response.ok) throw new Error(`QQ 请求失败 (${response.status})`)
  return result
}
