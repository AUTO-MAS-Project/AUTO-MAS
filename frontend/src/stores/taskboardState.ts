import { reactive, ref } from 'vue'
import { defineStore } from 'pinia'
import { ApiError, GetService, SetService, type TaskboardArchivedActivity } from '@/api'
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

const nowText = () => {
  const date = new Date()
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

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
  const weeklyWeek = ref('')
  const versionStory = reactive<Record<string, TaskboardVersionStoryRecord>>({})
  const versionStoryDone = reactive<Record<string, TaskboardDoneRecord>>({})
  const weeklySaving = ref<string[]>([])
  const versionStorySaving = ref<string[]>([])
  const versionStoryError = ref('')
  const loaded = ref(false)
  const loading = ref(false)
  const errorMessage = ref('')
  const archiveError = ref('')

  const load = async () => {
    if (loaded.value || loading.value) return
    loading.value = true
    try {
      const response = await GetService.getTaskboardStateApiInfoTaskboardStateGet()
      if (response.code !== 200) throw new Error(response.message)
      const data = response.data
      selectedGames.value = data?.selected_games ?? null
      weeklyGames.value = data?.weekly_games ?? null
      archived.value = (data?.archived ?? []).map(toActivity)
      for (const key of Object.keys(doneAt)) delete doneAt[key]
      Object.assign(doneAt, data?.done_at ?? {})
      for (const key of Object.keys(weekly)) delete weekly[key]
      Object.assign(weekly, data?.weekly ?? {})
      weeklyWeek.value = response.weekly_week ?? ''
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
    try {
      const response =
        await SetService.setTaskboardWeeklySelectionApiInfoTaskboardWeeklySelectionPut({ games })
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

  const isWeeklyDone = (key: string) => weekly[key]?.week === weeklyWeek.value

  const saveWeekly = async (key: string, done: boolean): Promise<string | null> => {
    if (weeklySaving.value.includes(key)) return null
    const previous = weekly[key]
    const previousWeek = weeklyWeek.value
    weeklySaving.value = [...weeklySaving.value, key]
    if (done) weekly[key] = { week: previousWeek, done_at: nowText() }
    else delete weekly[key]
    try {
      const response = await SetService.setTaskboardWeeklyApiInfoTaskboardWeeklyPut({
        key,
        done,
      })
      if (response.code !== 200) throw new Error(response.message)
      weeklyWeek.value = response.week ?? previousWeek
      if (done) {
        weekly[key] = {
          week: weeklyWeek.value,
          done_at: weekly[key]?.done_at ?? nowText(),
        }
      }
      return null
    } catch (error) {
      if (previous) weekly[key] = previous
      else delete weekly[key]
      return errorText(error)
    } finally {
      weeklySaving.value = weeklySaving.value.filter(item => item !== key)
    }
  }

  let lastVersionStoryJson = ''
  let lastVersionStoryAttempt: TaskboardVersionStoryUpdate[] = []
  let versionStoryRequestId = 0
  const saveVersionStory = async (
    records: TaskboardVersionStoryUpdate[]
  ): Promise<string | null> => {
    if (!records.length) return null
    const json = JSON.stringify(records)
    // 同一批版本记录不重复写；上次失败时即使内容没变也要重试。
    if (json === lastVersionStoryJson && !versionStoryError.value) return null
    lastVersionStoryAttempt = [...records]
    const requestId = ++versionStoryRequestId
    try {
      const response = await SetService.setTaskboardVersionStoryApiInfoTaskboardVersionStoryPut({
        records,
      })
      if (response.code !== 200) throw new Error(response.message)
      if (requestId !== versionStoryRequestId) return null
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
    if (record) versionStoryDone[key] = record
    else delete versionStoryDone[key]
    try {
      const response =
        await SetService.setTaskboardVersionStoryDoneApiInfoTaskboardVersionStoryDonePut({
          key,
          record,
        })
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
    weeklyWeek,
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
