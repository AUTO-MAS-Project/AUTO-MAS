// WebSocket 订阅注册表
// 按 id + type 精确路由；同一 id + type 可多次订阅，按订阅顺序调用；
// 无缓存、无重放，找不到订阅者的消息由连接层丢弃。

import type { WSEnvelope, WSMessageHandler, WSSubscriptionKey } from './types'

const logger = window.electronAPI.getLogger('WS订阅')

interface SubscriptionRecord {
  subscriptionId: string
  key: WSSubscriptionKey
  handler: WSMessageHandler
}

// 精确订阅是正式路径；单字段与全局订阅只服务旧页面迁移，不缓存或重放消息。
const exactSubscriptions = new Map<string, SubscriptionRecord[]>()
const idSubscriptions = new Map<string, SubscriptionRecord[]>()
const typeSubscriptions = new Map<string, SubscriptionRecord[]>()
const globalSubscriptions = new Map<string, SubscriptionRecord[]>()
const subscriptionIndex = new Map<string, SubscriptionRecord>()
let subscriptionCounter = 0

const exactKey = (id: string, type: string): string => `${id}\u0000${type}`

const bucketOf = (
  key: WSSubscriptionKey
): { map: Map<string, SubscriptionRecord[]>; mapKey: string } => {
  if (key.id !== undefined && key.type !== undefined) {
    return { map: exactSubscriptions, mapKey: exactKey(key.id, key.type) }
  }
  if (key.id !== undefined) return { map: idSubscriptions, mapKey: key.id }
  if (key.type !== undefined) return { map: typeSubscriptions, mapKey: key.type }
  return { map: globalSubscriptions, mapKey: '*' }
}

/**
 * 订阅消息。
 *
 * @param key 订阅键；省略字段仅用于旧页面迁移
 * @param handler 消息处理器
 * @returns 稳定订阅 ID，用于 unsubscribe
 */
export function subscribe(key: WSSubscriptionKey, handler: WSMessageHandler): string {
  const subscriptionId = `sub_${++subscriptionCounter}`
  const record: SubscriptionRecord = { subscriptionId, key: { ...key }, handler }

  const { map, mapKey } = bucketOf(key)
  const records = map.get(mapKey)
  if (records) {
    records.push(record)
  } else {
    map.set(mapKey, [record])
  }
  subscriptionIndex.set(subscriptionId, record)
  return subscriptionId
}

/** 取消订阅，幂等：重复取消或取消不存在的订阅安全无副作用。 */
export function unsubscribe(subscriptionId: string): void {
  const record = subscriptionIndex.get(subscriptionId)
  if (!record) return
  subscriptionIndex.delete(subscriptionId)

  const { map, mapKey } = bucketOf(record.key)
  const records = map.get(mapKey)
  if (!records) return
  const index = records.indexOf(record)
  if (index >= 0) records.splice(index, 1)
  if (records.length === 0) map.delete(mapKey)
}

/**
 * 分发一条入站消息。
 *
 * @returns 是否至少有一个订阅者收到该消息
 */
export function dispatchMessage(message: WSEnvelope): boolean {
  const exact = exactSubscriptions.get(exactKey(message.id, message.type))
  const byId = idSubscriptions.get(message.id)
  const byType = typeSubscriptions.get(message.type)
  const global = globalSubscriptions.get('*')
  if (!exact?.length && !byId?.length && !byType?.length && !global?.length) return false

  // 迭代副本，允许 handler 内取消/新增订阅；单个 handler 异常不影响其他订阅者
  for (const record of [...(exact ?? []), ...(byId ?? []), ...(byType ?? []), ...(global ?? [])]) {
    if (!subscriptionIndex.has(record.subscriptionId)) continue
    try {
      record.handler(message)
    } catch (e) {
      const errorMsg = e instanceof Error ? e.message : String(e)
      logger.warn(
        `订阅处理器错误 [${record.subscriptionId}] (${message.id}/${message.type}): ${errorMsg}`
      )
    }
  }
  return true
}

/** 当前订阅总数（诊断用） */
export function subscriptionCount(): number {
  return subscriptionIndex.size
}
