import { reactive, ref } from 'vue'
import { defineStore } from 'pinia'
import { ApiError, GetService, SetService, type TaskboardArchivedActivity } from '@/api'
import { analyticsCountBucket } from '@/utils/analytics'
import { beijingNowText } from '@/utils/activityTime'
import { apiOutcome, observeFeature } from '@/utils/featureAnalytics'
import { nextWeekResetAt, weekKeyOf } from '@/utils/taskboardWeek'
import type {
  TaskboardActivity,
  TaskboardVersionStoryRecord,
  TaskboardVersionStoryUpdate,
  TaskboardWeeklyRecord,
} from '@/types/taskboard'

export interface TaskboardDoneRecord {
  at: string
  end: string
}

const errorText = (error: unknown): string => {
  if (error instanceof ApiError) {
    const body: unknown = error.body
    if (body && typeof body === 'object' && 'message' in body && typeof body.message === 'string') {
      return body.message
    }
  }
  return error instanceof Error ? error.message : String(error)
}

const nowText = () => beijingNowText()

const toActivity = (row: TaskboardArchivedActivity): TaskboardActivity => ({
  id: row.id,
  gameKey: row.game_key,
  title: row.title,
  start_time: row.start_time ?? '',
  end_time: row.end_time ?? '',
  description: row.description ?? '',
  image_url: row.image_url ?? '',
})

const toPayload = (row: TaskboardActivity): TaskboardArchivedActivity => ({
  id: row.id,
  game_key: row.gameKey,
  title: row.title,
  start_time: row.start_time,
  end_time: row.end_time,
  description: row.description,
  image_url: row.image_url,
})

/**
 * 任务台持久化状态的唯一归属：任务台/每周任务的游戏勾选、归档缓存、完成日期、
 * 版本主线与版本标记都存后端配置目录，
 * 渲染进程不保留业务数据的本地副本。
 */
export const useTaskboardStateStore = defineStore('taskboardState', () => {
  const selectedGames = ref<string[] | null>(null)
  const weeklyGames = ref<string[] | null>(null)
  const archived = ref<TaskboardActivity[]>([])
  const doneAt = reactive<Record<string, TaskboardDoneRecord>>({})
  const weekly = reactive<Record<string, TaskboardWeeklyRecord>>({})
  /* 前端自己维护当前周键，长期开着的窗口跨周后不会继续显示上周的完成状态。 */
  const currentWeek = ref(weekKeyOf())
  let weekTimer: ReturnType<typeof setTimeout> | null = null
  let weeklyGeneration = 0
  let versionStoryGeneration = 0

  const scheduleWeekRefresh = () => {
    if (weekTimer) clearTimeout(weekTimer)
    const delay = Math.max(1000, nextWeekResetAt() - Date.now() + 1000)
    weekTimer = setTimeout(() => {
      currentWeek.value = weekKeyOf()
      scheduleWeekRefresh()
    }, delay)
  }

  const syncWeek = () => {
    const next = weekKeyOf()
    if (next !== currentWeek.value) currentWeek.value = next
    scheduleWeekRefresh()
  }

  scheduleWeekRefresh()
  if (typeof window !== 'undefined') {
    window.addEventListener('focus', syncWeek)
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') syncWeek()
    })
  }
  const versionStory = reactive<Record<string, TaskboardVersionStoryRecord>>({})
  const versionStoryDone = reactive<Record<string, TaskboardDoneRecord>>({})
  const weeklySaving = ref<string[]>([])
  const versionStorySaving = ref<string[]>([])
  const versionStoryError = ref('')
  const loaded = ref(false)
  const loading = ref(false)
  const errorMessage = ref('')
  const archiveError = ref('')

  const load = async (force = false) => {
    if ((!force && loaded.value) || loading.value) return
    loading.value = true
    const weeklyGenAtStart = weeklyGeneration
    const versionGenAtStart = versionStoryGeneration
    try {
      const response = await GetService.getTaskboardStateApiInfoTaskboardStateGet()
      if (response.code !== 200) throw new Error(response.message)
      const data = response.data
      selectedGames.value = data?.selected_games ?? null
      weeklyGames.value = data?.weekly_games ?? null
      archived.value = (data?.archived ?? []).map(toActivity)
      for (const key of Object.keys(doneAt)) delete doneAt[key]
      Object.assign(doneAt, data?.done_at ?? {})
      /* 读取期间已经发生过本地保存时，保留本地较新的数据，不用旧快照覆盖。 */
      if (weeklyGenAtStart === weeklyGeneration) {
        for (const key of Object.keys(weekly)) delete weekly[key]
        Object.assign(weekly, data?.weekly ?? {})
        if (response.weekly_week) currentWeek.value = response.weekly_week
      }
      if (versionGenAtStart === versionStoryGeneration) {
        for (const key of Object.keys(versionStory)) delete versionStory[key]
        for (const [key, record] of Object.entries(data?.version_story ?? {})) {
          versionStory[key] = {
            game: record.game,
            version: record.version,
            version_name: record.version_name ?? '',
            start: record.start ?? '',
            end: record.end ?? '',
            cover_url: record.cover_url ?? '',
            first_seen: record.first_seen ?? '',
            last_seen: record.last_seen ?? '',
          }
        }
        for (const key of Object.keys(versionStoryDone)) delete versionStoryDone[key]
        Object.assign(versionStoryDone, data?.version_story_done ?? {})
      }
      loaded.value = true
      errorMessage.value = ''
    } catch (error) {
      errorMessage.value = errorText(error)
    } finally {
      loading.value = false
    }
  }

  const saveSelection = async (games: string[]): Promise<string | null> => {
    try {
      const response = await SetService.setTaskboardSelectionApiInfoTaskboardSelectionPut({ games })
      if (response.code !== 200) throw new Error(response.message)
      selectedGames.value = [...games]
      return null
    } catch (error) {
      return errorText(error)
    }
  }

  const saveWeeklySelection = async (games: string[]): Promise<string | null> => {
    weeklyGeneration += 1
    try {
      const response = await observeFeature(
        'taskboard_marking_finished',
        {
          target_kind: 'weekly_task',
          action: 'select',
          count_bucket: analyticsCountBucket(games.length),
        },
        () => SetService.setTaskboardWeeklySelectionApiInfoTaskboardWeeklySelectionPut({ games }),
        apiOutcome
      )
      if (response.code !== 200) throw new Error(response.message)
      weeklyGames.value = [...games]
      return null
    } catch (error) {
      return errorText(error)
    }
  }

  let lastArchiveJson = ''
  let archiveRequestId = 0
  const saveArchive = async (list: TaskboardActivity[]): Promise<string | null> => {
    const payload = list.map(toPayload)
    const json = JSON.stringify(payload)
    // 上次保存失败时即使内容没变也要重试，否则错误状态永远清不掉。
    if (json === lastArchiveJson && !archiveError.value) return null
    const requestId = ++archiveRequestId
    try {
      const response = await SetService.setTaskboardArchiveApiInfoTaskboardArchivePut({
        archived: payload,
      })
      if (requestId !== archiveRequestId) return null
      if (response.code !== 200) throw new Error(response.message)
      archived.value = list
      lastArchiveJson = json
      archiveError.value = ''
      return null
    } catch (error) {
      // 较早的请求晚失败时，不要把已经成功的新结果又标成失败。
      if (requestId !== archiveRequestId) return null
      const message = errorText(error)
      archiveError.value = message
      return message
    }
  }

  const setDone = async (key: string, record: TaskboardDoneRecord | null) => {
    if (record) doneAt[key] = record
    else delete doneAt[key]
    try {
      const response = await SetService.setTaskboardDoneAtApiInfoTaskboardDoneAtPut({ key, record })
      if (response.code !== 200) throw new Error(response.message)
    } catch (error) {
      errorMessage.value = errorText(error)
    }
  }

  const doneAtOf = (key: string) => doneAt[key]?.at ?? ''

  const isWeeklyDone = (key: string) => weekly[key]?.week === currentWeek.value

  const saveWeekly = async (
    key: string,
    done: boolean
  ): Promise<{ error: string | null; applied: boolean }> => {
    if (weeklySaving.value.includes(key)) return { error: null, applied: true }
    const previous = weekly[key]
    const weekAtStart = currentWeek.value
    weeklySaving.value = [...weeklySaving.value, key]
    weeklyGeneration += 1
    if (done) weekly[key] = { week: weekAtStart, done_at: nowText() }
    else delete weekly[key]
    try {
      const response = await observeFeature(
        'taskboard_marking_finished',
        {
          target_kind: 'weekly_task',
          action: done ? 'mark' : 'unmark',
          count_bucket: '1',
        },
        () =>
          SetService.setTaskboardWeeklyApiInfoTaskboardWeeklyPut({
            key,
            done,
            week: weekAtStart,
          }),
        result =>
          result.code !== 200
            ? apiOutcome(result)
            : result.applied === false
              ? 'blocked'
              : 'success'
      )
      if (response.code !== 200) throw new Error(response.message)
      if (response.week) currentWeek.value = response.week
      if (response.applied === false) {
        /* 客户端周键已过期，后端没有落盘：恢复乐观更新并按服务端周键重新对齐。 */
        if (previous) weekly[key] = previous
        else delete weekly[key]
        void load(true)
        return { error: null, applied: false }
      }
      if (done) {
        weekly[key] = {
          week: response.week ?? weekAtStart,
          done_at: weekly[key]?.done_at ?? nowText(),
        }
      }
      return { error: null, applied: true }
    } catch (error) {
      if (previous) weekly[key] = previous
      else delete weekly[key]
      return { error: errorText(error), applied: false }
    } finally {
      weeklySaving.value = weeklySaving.value.filter(item => item !== key)
    }
  }

  let lastVersionStoryJson = ''
  let lastVersionStoryAttempt: TaskboardVersionStoryUpdate[] = []
  let lastVersionStoryObservedJson = ''
  let lastVersionStoryObservedAt = 0
  let versionStoryRequestId = 0
  const saveVersionStory = async (
    records: TaskboardVersionStoryUpdate[]
  ): Promise<string | null> => {
    if (!records.length) return null
    const json = JSON.stringify(records)
    // 同一批版本记录不重复写；上次失败时即使内容没变也要重试。
    if (json === lastVersionStoryJson && !versionStoryError.value) return null
    /* 同一批数据复用采集时间，重试不刷新时间戳；内容变化才算一次新观察。 */
    if (json !== lastVersionStoryObservedJson) {
      lastVersionStoryObservedJson = json
      lastVersionStoryObservedAt = Date.now()
    }
    lastVersionStoryAttempt = [...records]
    const requestId = ++versionStoryRequestId
    try {
      const response = await SetService.setTaskboardVersionStoryApiInfoTaskboardVersionStoryPut({
        records,
        observed_at: lastVersionStoryObservedAt,
      })
      if (response.code !== 200) throw new Error(response.message)
      if (requestId !== versionStoryRequestId) return null
      versionStoryGeneration += 1
      const at = nowText()
      for (const item of records) {
        const key = `${item.game}|${item.version}`
        const existing = versionStory[key]
        versionStory[key] = {
          game: item.game,
          version: item.version,
          version_name: item.version_name || item.version,
          start: item.start,
          end: item.end,
          cover_url: item.cover_url,
          first_seen: existing?.first_seen || at,
          last_seen: at,
        }
      }
      lastVersionStoryJson = json
      versionStoryError.value = ''
      return null
    } catch (error) {
      if (requestId === versionStoryRequestId) {
        versionStoryError.value = errorText(error)
      }
      return errorText(error)
    }
  }

  const retryVersionStory = () => saveVersionStory(lastVersionStoryAttempt)

  const isVersionStoryDone = (key: string) => Boolean(versionStoryDone[key])
  const versionStoryDoneAtOf = (key: string) => versionStoryDone[key]?.at ?? ''

  const setVersionStoryDone = async (
    key: string,
    record: TaskboardDoneRecord | null
  ): Promise<string | null> => {
    if (versionStorySaving.value.includes(key)) return null
    const previous = versionStoryDone[key]
    versionStorySaving.value = [...versionStorySaving.value, key]
    versionStoryGeneration += 1
    if (record) versionStoryDone[key] = record
    else delete versionStoryDone[key]
    try {
      const response = await observeFeature(
        'taskboard_marking_finished',
        {
          target_kind: 'version',
          action: record ? 'mark' : 'unmark',
          count_bucket: '1',
        },
        () =>
          SetService.setTaskboardVersionStoryDoneApiInfoTaskboardVersionStoryDonePut({
            key,
            record,
          }),
        apiOutcome
      )
      if (response.code !== 200) throw new Error(response.message)
      return null
    } catch (error) {
      if (previous) versionStoryDone[key] = previous
      else delete versionStoryDone[key]
      return errorText(error)
    } finally {
      versionStorySaving.value = versionStorySaving.value.filter(item => item !== key)
    }
  }

  return {
    selectedGames,
    weeklyGames,
    saveWeeklySelection,
    archived,
    doneAt,
    weekly,
    weeklySaving,
    versionStory,
    versionStoryDone,
    versionStorySaving,
    versionStoryError,
    loaded,
    loading,
    errorMessage,
    archiveError,
    load,
    saveSelection,
    saveArchive,
    setDone,
    doneAtOf,
    isWeeklyDone,
    saveWeekly,
    saveVersionStory,
    retryVersionStory,
    isVersionStoryDone,
    versionStoryDoneAtOf,
    setVersionStoryDone,
  }
})
