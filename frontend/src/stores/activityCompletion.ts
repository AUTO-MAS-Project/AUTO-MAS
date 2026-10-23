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

const scopeKey = (scope: ActivityCompletionScope) => `${scope.game}:${scope.server ?? 'cn'}`

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

const DONE_AT_KEY = 'auto-mas.activity-completion.done-at'

const readDoneAt = (): Record<string, string> => {
  try {
    const raw = localStorage.getItem(DONE_AT_KEY)
    if (!raw) return {}
    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    return Object.fromEntries(
      Object.entries(parsed as Record<string, unknown>).filter(
        ([, value]) => typeof value === 'string'
      )
    ) as Record<string, string>
  } catch {
    return {}
  }
}

const saveDoneAt = (value: Record<string, string>) => {
  try {
    localStorage.setItem(DONE_AT_KEY, JSON.stringify(value))
  } catch {
    // 本地存储不可用时仅本次会话生效
  }
}

const nowText = () => {
  const date = new Date()
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

/**
 * 活动完成状态的唯一归属：首页活动卡与任务台共用这一份。
 *
 * 数据本身由后端 `/api/info/activity/completions` 持久化，这里只做进程内缓存；
 * 首页活动卡与任务台读写同一份记录，标记后两边同步。
 */
export const useActivityCompletionStore = defineStore('activityCompletion', () => {
  const states = reactive<Record<string, ScopeState>>({})
  /** 完成日期：只用于展示，跟着完成状态一起由两个入口维护 */
  const doneAt = reactive<Record<string, string>>(readDoneAt())
  const doneKey = (scope: ActivityCompletionScope, item: GameCalendarActivityInfo) =>
    `${scopeKey(scope)}|${activityKey(item)}`
  const doneAtOf = (scope: ActivityCompletionScope, item: GameCalendarActivityInfo) =>
    doneAt[doneKey(scope, item)] ?? ''

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

  const queues = new Map<string, Promise<void>>()

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
      // 响应回来时如果正在保存，保留本地最新的完成状态，别被这次读覆盖。
      if (!state.pending.length) state.items = response.data ?? []
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

    // 同一作用域的读取串行排队：并发刷新不会同时发出多个 GET，
    // 旧响应也不会晚于新响应写回。非强制调用直接复用队列里的那一次。
    const queued = queues.get(key)
    if (queued) {
      if (!force) {
        await queued
        return
      }
    } else if (!force && state.ready) {
      return
    }

    const previous = queues.get(key) ?? Promise.resolve()
    const run = previous.catch(() => undefined).then(() => runLoad(scope))
    queues.set(key, run)
    try {
      await run
    } finally {
      if (queues.get(key) === run) queues.delete(key)
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
      const dateKey = doneKey(scope, item)
      if (completed) doneAt[dateKey] = nowText()
      else delete doneAt[dateKey]
      saveDoneAt({ ...doneAt })
    } catch (error) {
      throw completionError(error)
    } finally {
      state.pending = state.pending.filter(pending => pending !== key)
    }
  }

  return { stateOf, isCompleted, isSaving, doneAtOf, load, toggle }
})
