import { reactive, ref } from 'vue'
import { defineStore } from 'pinia'
import { ApiError, GetService, SetService, type TaskboardArchivedActivity } from '@/api'
import type { TaskboardActivity } from '@/types/taskboard'

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
 * 任务台持久化状态的唯一归属：已选游戏、归档缓存、完成日期都存后端配置目录，
 * 渲染进程不再保留业务数据的本地副本。
 */
export const useTaskboardStateStore = defineStore('taskboardState', () => {
  const selectedGames = ref<string[] | null>(null)
  const archived = ref<TaskboardActivity[]>([])
  const doneAt = reactive<Record<string, TaskboardDoneRecord>>({})
  const loaded = ref(false)
  const loading = ref(false)
  const errorMessage = ref('')

  const load = async () => {
    if (loaded.value || loading.value) return
    loading.value = true
    try {
      const response = await GetService.getTaskboardStateApiInfoTaskboardStateGet()
      if (response.code !== 200) throw new Error(response.message)
      const data = response.data
      selectedGames.value = data?.selected_games ?? null
      archived.value = (data?.archived ?? []).map(toActivity)
      for (const key of Object.keys(doneAt)) delete doneAt[key]
      Object.assign(doneAt, data?.done_at ?? {})
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

  let lastArchiveJson = ''
  const saveArchive = async (list: TaskboardActivity[]): Promise<string | null> => {
    const payload = list.map(toPayload)
    const json = JSON.stringify(payload)
    if (json === lastArchiveJson) return null
    try {
      const response = await SetService.setTaskboardArchiveApiInfoTaskboardArchivePut({
        archived: payload,
      })
      if (response.code !== 200) throw new Error(response.message)
      archived.value = list
      lastArchiveJson = json
      return null
    } catch (error) {
      return errorText(error)
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

  return {
    selectedGames,
    archived,
    doneAt,
    loaded,
    loading,
    errorMessage,
    load,
    saveSelection,
    saveArchive,
    setDone,
    doneAtOf,
  }
})
