import { computed, ref } from 'vue'
import {
  ApiError,
  GetService,
  SetService,
  type GameCalendarActivityInfo,
  type GameCalendarActivityCompletionIn,
} from '@/api'

export type ActivityCompletionScope = Pick<GameCalendarActivityCompletionIn, 'game' | 'server'>
const activityKey = (item: GameCalendarActivityInfo) =>
  JSON.stringify([item.name.trim(), new Date(item.startTime).getTime()])

const completionError = (error: unknown): Error => {
  if (error instanceof ApiError) {
    const body: unknown = error.body
    if (body && typeof body === 'object' && 'message' in body && typeof body.message === 'string') {
      return new Error(body.message)
    }
  }
  return error instanceof Error ? error : new Error(String(error))
}

/** 各游戏及服务器独立保存完成状态，继续与后台日历共用持久化记录。 */
export const useActivityCompletionApi = (scope: ActivityCompletionScope) => {
  const completedActivities = ref<GameCalendarActivityInfo[]>([])
  const completedKeys = computed(() => new Set(completedActivities.value.map(activityKey)))
  const savingKeys = ref(new Set<string>())
  const loading = ref(false)
  const ready = ref(false)
  const errorMessage = ref('')
  const isCompleted = (item: GameCalendarActivityInfo) => completedKeys.value.has(activityKey(item))
  const isSaving = (item: GameCalendarActivityInfo) => savingKeys.value.has(activityKey(item))

  const load = async () => {
    if (loading.value) return
    loading.value = true
    errorMessage.value = ''
    try {
      const response = await GetService.getActivityCompletionsApiInfoActivityCompletionsGet(
        scope.game,
        scope.server
      )
      if (response.code !== 200) throw new Error(response.message)
      completedActivities.value = response.data ?? []
      ready.value = true
    } catch (error) {
      ready.value = false
      errorMessage.value = completionError(error).message
    } finally {
      loading.value = false
    }
  }

  const toggle = async (item: GameCalendarActivityInfo) => {
    if (!ready.value || isSaving(item)) return
    const key = activityKey(item)
    const completed = !isCompleted(item)
    savingKeys.value = new Set(savingKeys.value).add(key)
    try {
      const response = await SetService.setActivityCompletionApiInfoActivityCompletionsPost({
        ...scope,
        ...item,
        startTime: new Date(item.startTime).toISOString(),
        endTime: new Date(item.endTime).toISOString(),
        completed,
      })
      if (response.code !== 200) throw new Error(response.message)
      completedActivities.value = completedActivities.value.filter(
        activity => activityKey(activity) !== key
      )
      if (completed) completedActivities.value.push(item)
    } catch (error) {
      throw completionError(error)
    } finally {
      const pending = new Set(savingKeys.value)
      pending.delete(key)
      savingKeys.value = pending
    }
  }

  return { loading, ready, errorMessage, isCompleted, isSaving, load, toggle }
}
