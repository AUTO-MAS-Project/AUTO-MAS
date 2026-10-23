import { ref } from 'vue'
import type { TaskboardActivity } from '@/types/taskboard'

const GAMES_STORE_KEY = 'auto-mas.taskboard.games'
const CACHE_KEY = 'auto-mas.taskboard.events'
const DONE_AT_KEY = 'auto-mas.taskboard.done-at'

const readJson = <T>(key: string, fallback: T, isValid: (value: unknown) => boolean): T => {
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return fallback
    const parsed: unknown = JSON.parse(raw)
    return isValid(parsed) ? (parsed as T) : fallback
  } catch {
    // 本地存储不可用或内容损坏时按空数据处理
    return fallback
  }
}

const isStringArray = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every(item => typeof item === 'string')

const isActivityArray = (value: unknown): boolean =>
  Array.isArray(value) &&
  value.every(item => {
    if (!item || typeof item !== 'object') return false
    const row = item as Record<string, unknown>
    return (
      typeof row.id === 'string' &&
      typeof row.gameKey === 'string' &&
      typeof row.title === 'string' &&
      typeof row.start_time === 'string' &&
      typeof row.end_time === 'string'
    )
  })

const isStringRecord = (value: unknown): value is Record<string, string> =>
  !!value &&
  typeof value === 'object' &&
  !Array.isArray(value) &&
  Object.values(value).every(item => typeof item === 'string')

const writeJson = (key: string, value: unknown) => {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // 本地存储不可用时仅本次会话生效
  }
}

/**
 * 任务台的本地持久化：已选游戏、完成日期、已见过的活动缓存。
 *
 * 活动缓存用于补出「已归档」——官方活动源只保留当期活动，结束后就从数据里消失，
 * 所以在每次加载时把见过的活动累积下来，结束 45 天后由页面侧剔除。
 */
export const useTaskboardStorage = () => {
  const enabledKeys = ref<string[] | null>(
    readJson<string[] | null>(
      GAMES_STORE_KEY,
      null,
      value => value === null || isStringArray(value)
    )
  )
  const cachedEvents = ref<TaskboardActivity[]>(
    readJson<TaskboardActivity[]>(CACHE_KEY, [], isActivityArray)
  )
  /** 标记完成的时间（活动 id → 完成日期），撤销时清掉 */
  const doneAt = ref<Record<string, string>>(
    readJson<Record<string, string>>(DONE_AT_KEY, {}, isStringRecord)
  )

  return {
    enabledKeys,
    cachedEvents,
    doneAt,
    saveEnabledKeys: () => writeJson(GAMES_STORE_KEY, enabledKeys.value),
    saveCache: () => writeJson(CACHE_KEY, cachedEvents.value),
    saveDoneAt: () => writeJson(DONE_AT_KEY, doneAt.value),
  }
}
