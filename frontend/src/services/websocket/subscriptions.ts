// WebSocket 订阅注册表
// 只按 id + type 精确路由；同一键可多次订阅并按注册顺序调用。
// 无缓存、无重放，找不到订阅者的消息由连接层直接丢弃。

import type {
  WSDataForType,
  WSEnvelope,
  WSJsonObject,
  WSMessageHandler,
  WSSubscriptionKey,
} from './types'

const logger = window.electronAPI.getLogger('WS订阅')

interface SubscriptionRecord {
  subscriptionId: string
  key: WSSubscriptionKey
  handler: WSMessageHandler<unknown>
}

// 使用两层 Map 表示 (id, type)，避免字符串拼接分隔符造成键碰撞，
// 也避免在 TypeScript 源码中嵌入 NUL 字节。
const subscriptions = new Map<string, Map<string, SubscriptionRecord[]>>()
const subscriptionIndex = new Map<string, SubscriptionRecord>()
let subscriptionCounter = 0

const validateKey = (key: WSSubscriptionKey): void => {
  if (
    typeof key.id !== 'string' ||
    !key.id.trim() ||
    typeof key.type !== 'string' ||
    !key.type.trim()
  ) {
    throw new Error('订阅键必须包含非空 id 和 type')
  }
}

const recordsFor = (key: WSSubscriptionKey): SubscriptionRecord[] | undefined =>
  subscriptions.get(key.id)?.get(key.type)

const logHandlerError = (
  record: SubscriptionRecord,
  message: WSEnvelope<WSJsonObject>,
  error: unknown
): void => {
  const errorMsg = error instanceof Error ? error.message : String(error)
  logger.warn(
    `订阅处理器错误 [${record.subscriptionId}] (${message.id}/${message.type}): ${errorMsg}`
  )
}

/**
 * 订阅一类精确消息。
 *
 * @returns 稳定订阅 ID，用于幂等 unsubscribe
 */
export function subscribe<TType extends string>(
  key: WSSubscriptionKey<TType>,
  handler: WSMessageHandler<WSDataForType<TType>>
): string {
  validateKey(key)
  const subscriptionId = `sub_${++subscriptionCounter}`
  const record: SubscriptionRecord = {
    subscriptionId,
    key: { ...key },
    handler: handler as WSMessageHandler<unknown>,
  }

  let byType = subscriptions.get(key.id)
  if (!byType) {
    byType = new Map<string, SubscriptionRecord[]>()
    subscriptions.set(key.id, byType)
  }
  const records = byType.get(key.type)
  if (records) {
    records.push(record)
  } else {
    byType.set(key.type, [record])
  }
  subscriptionIndex.set(subscriptionId, record)
  return subscriptionId
}

/** 取消订阅，幂等：重复取消或取消不存在的订阅安全无副作用。 */
export function unsubscribe(subscriptionId: string): void {
  const record = subscriptionIndex.get(subscriptionId)
  if (!record) return
  subscriptionIndex.delete(subscriptionId)

  const byType = subscriptions.get(record.key.id)
  const records = byType?.get(record.key.type)
  if (!byType || !records) return
  const index = records.indexOf(record)
  if (index >= 0) records.splice(index, 1)
  if (records.length === 0) byType.delete(record.key.type)
  if (byType.size === 0) subscriptions.delete(record.key.id)
}

/**
 * 分发一条入站消息。
 *
 * @returns 是否至少有一个精确订阅者收到该消息
 */
export function dispatchMessage(message: WSEnvelope<WSJsonObject>): boolean {
  const records = recordsFor(message)
  if (!records?.length) return false

  // 迭代副本，允许 handler 内取消/新增订阅；单个 handler 异常不影响其他订阅者。
  for (const record of [...records]) {
    if (!subscriptionIndex.has(record.subscriptionId)) continue
    try {
      const result = record.handler(message)
      if (result instanceof Promise) {
        void result.catch(error => logHandlerError(record, message, error))
      }
    } catch (error) {
      logHandlerError(record, message, error)
    }
  }
  return true
}

/** 当前订阅总数（诊断用）。 */
export function subscriptionCount(): number {
  return subscriptionIndex.size
}
