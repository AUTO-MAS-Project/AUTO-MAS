import { reactive } from 'vue'
import { defineStore } from 'pinia'
import {
  ApiError,
  GetService,
  SetService,
  type GameCalendarActivityCompletionIn,
  type GameCalendarActivityInfo,
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

interface ScopeState {
  items: GameCalendarActivityInfo[]
  loading: boolean
  ready: boolean
  errorMessage: string
  /** 正在保存的完成状态键，避免同一活动并发写入 */
  pending: string[]
}

const scopeKey = (scope: ActivityCompletionScope) => `${scope.game}:${scope.server ?? 'cn'}`

/**
 * 活动完成状态的唯一归属：首页活动卡与任务台共用这一份。
 *
 * 数据本身由后端 `/api/info/activity/completions` 持久化，这里只做进程内缓存；
 * 首页活动卡与任务台读写同一份记录，标记后两边同步。
 */
export const useActivityCompletionStore = defineStore('activityCompletion', () => {
  const states = reactive<Record<string, ScopeState>>({})

  const stateOf = (scope: ActivityCompletionScope): ScopeState => {
    const key = scopeKey(scope)
    if (!states[key]) {
      states[key] = {
        items: [],
        loading: false,
        ready: false,
        errorMessage: '',
        pending: [],
      }
    }
    // 必须返回 reactive 里的代理，直接返回刚建好的原始对象不会触发界面更新。
    return states[key]
  }

  const isCompleted = (scope: ActivityCompletionScope, item: GameCalendarActivityInfo) => {
    const key = activityKey(item)
    return stateOf(scope).items.some(activity => activityKey(activity) === key)
  }

  const isSaving = (scope: ActivityCompletionScope, item: GameCalendarActivityInfo) =>
    stateOf(scope).pending.includes(activityKey(item))

  const inFlight = new Map<string, Promise<void>>()

  const runLoad = async (scope: ActivityCompletionScope) => {
    const state = stateOf(scope)
    state.loading = true
    // 读取与保存互斥，避免较早的读取结果覆盖刚保存的完成状态。
    state.ready = false
    state.errorMessage = ''
    try {
      const response = await GetService.getActivityCompletionsApiInfoActivityCompletionsGet(
        scope.game,
        scope.server
      )
      if (response.code !== 200) throw new Error(response.message)
      state.items = response.data ?? []
      state.ready = true
    } catch (error) {
      state.ready = false
      state.errorMessage = completionError(error).message
    } finally {
      state.loading = false
    }
  }

  const load = async (scope: ActivityCompletionScope, force = false) => {
    const key = scopeKey(scope)
    const state = stateOf(scope)
    if (state.pending.length) return
    // 同一进程内复用已经取到的结果；手动刷新时传 force 重新拉。
    if (!force && state.ready) return

    const current = inFlight.get(key)
    if (current) {
      // 刷新撞上正在进行的请求时要等它结束，否则会带着旧数据收尾。
      await current
      if (!force) return
    }

    const task = runLoad(scope)
    inFlight.set(key, task)
    try {
      await task
    } finally {
      inFlight.delete(key)
    }
  }

  const toggle = async (scope: ActivityCompletionScope, item: GameCalendarActivityInfo) => {
    const state = stateOf(scope)
    if (!state.ready || isSaving(scope, item)) return
    const key = activityKey(item)
    const completed = !isCompleted(scope, item)
    state.pending = [...state.pending, key]
    try {
      const response = await SetService.setActivityCompletionApiInfoActivityCompletionsPost({
        ...scope,
        ...item,
        startTime: new Date(item.startTime).toISOString(),
        endTime: new Date(item.endTime).toISOString(),
        completed,
      })
      if (response.code !== 200) throw new Error(response.message)
      state.items = state.items.filter(activity => activityKey(activity) !== key)
      if (completed) state.items.push(item)
    } catch (error) {
      throw completionError(error)
    } finally {
      state.pending = state.pending.filter(pending => pending !== key)
    }
  }

  return { stateOf, isCompleted, isSaving, load, toggle }
})
