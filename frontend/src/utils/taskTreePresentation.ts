import type { WSTaskScriptInfoData } from '@/services/websocket/types'

const record = (value: unknown): Record<string, unknown> =>
  value !== null && typeof value === 'object' ? (value as Record<string, unknown>) : {}

const entries = (value: unknown): [string, Record<string, unknown>][] => {
  const collection = record(value)
  const data = record(collection.data)
  const order = Array.isArray(collection.order) ? collection.order : []
  return order.flatMap(item => {
    const uid = record(item).uid
    return typeof uid === 'string' && uid in data ? [[uid, record(data[uid])]] : []
  })
}

/** 由新任务树投影出旧页面的脚本/用户行，顺序以集合声明为准。 */
export function taskInfoFromTree(value: unknown): WSTaskScriptInfoData[] {
  return entries(record(value).scripts).map(([scriptId, script]) => {
    const info = record(script.info)
    return {
      script_id: scriptId,
      name: String(info.name ?? ''),
      status: String(info.status ?? ''),
      userList: entries(script.users).map(([userId, user]) => {
        const userInfo = record(user.info)
        return {
          user_id: userId,
          name: String(userInfo.name ?? ''),
          status: String(userInfo.status ?? ''),
        }
      }),
    }
  })
}
