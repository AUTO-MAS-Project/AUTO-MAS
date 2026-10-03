import { onScopeDispose, ref, type Ref } from 'vue'

/**
 * 首页活动数据源的公共调度骨架。
 *
 * 各游戏的活动卡片都走同一套节奏：可见时才取数、失败按固定间隔退避重试、退避期间
 * 模块被隐藏就把这一轮挂起、成功后留一份快照下次先用。取数与成功/失败的处理各家不同，
 * 由调用方以钩子传进来；这里只管「什么时候取、失败了怎么退」。
 */

/** 失败后的重试间隔与上限：与各卡原有的节奏保持一致 */
const RETRY_DELAY_MS = 30_000
const MAX_RETRIES = 8

const logger = window.electronAPI.getLogger('活动数据')

export interface HomeActivitySourceOptions<T> {
  /** 日志与失败文案里用的名字，调用方翻译好再传 */
  label: () => string
  /** 取一次数据，失败直接抛；signal 用于超时中止，不需要的可以忽略 */
  fetchData: (signal: AbortSignal) => Promise<T>
  /** 成功：把数据落到概览上 */
  applyData: (data: T) => void
  /** 失败且手上已有内容：标记数据可能已过期 */
  markStale: () => void
  /** 失败且手上没有内容：给出空态与提示 */
  markUnavailable: (label: string) => void
  /** 启动时先用快照顶上，返回是否恢复成功 */
  restoreSnapshot?: () => boolean
  /** 成功后写入快照 */
  saveSnapshot?: (data: T) => void
  /** 请求超时（毫秒）；不给就不中止请求 */
  timeoutMs?: number
  /** 初始化时就点亮加载态（默认 true） */
  loadingOnInit?: boolean
  /** start 时按有没有内容决定加载态（默认 false） */
  loadingOnStart?: boolean
  /** 请求开始时的环境标记，响应回来时交给 isObsolete 比对 */
  requestTag?: () => unknown
  /** 标记已变（例如界面语言换了）时丢弃这次响应 */
  isObsolete?: (tag: unknown) => boolean
  /** 首次 start 时的额外动作（例如同时去取版本宣传图） */
  onFirstStart?: () => void
  /** 已经有同一份数据在取时返回 true：这一轮直接跳过，不重复发请求 */
  isBusy?: () => boolean
}

export interface HomeActivitySource {
  loading: Ref<boolean>
  hasData: Ref<boolean>
  /** 模块可见：首次进入时取数，之前挂起的重试在这里补上 */
  start: () => void
  /** 模块隐藏：停掉排队中的重试并挂起 */
  stop: () => void
  /** 手动刷新：清掉重试计数后立刻重取 */
  refresh: () => void
  /** 立即重取（换语言等场景用） */
  reload: () => void
  /** 可见性恢复后补一次挂起的重试 */
  resume: () => void
  /** 重试计数归零 */
  resetRetry: () => void
  /** 重新尝试用快照顶上，返回是否恢复成功 */
  restore: () => boolean
}

export const useHomeActivitySource = <T>(
  options: HomeActivitySourceOptions<T>
): HomeActivitySource => {
  const loading = ref(false)
  const hasData = ref(false)
  let retryTimer: number | null = null
  let retryCount = 0
  let disposed = false
  let active = false
  let started = false
  let retryPending = false

  const isObsolete = (tag: unknown) => tag !== undefined && options.isObsolete?.(tag) === true

  const clearRetry = () => {
    if (retryTimer !== null) {
      window.clearTimeout(retryTimer)
      retryTimer = null
    }
  }

  const load = async () => {
    if (disposed) return
    // 同一份数据已经在取：跳过这一轮，别把两个并发请求的结果来回盖
    if (options.isBusy?.() === true) return
    const tag = options.requestTag?.()
    let timer: number | null = null
    try {
      const controller = new AbortController()
      if (options.timeoutMs !== undefined) {
        timer = window.setTimeout(() => controller.abort(), options.timeoutMs)
      }
      const data = await options.fetchData(controller.signal)
      // 请求期间环境变了：丢弃这次结果，交给变化后触发的那一轮
      if (disposed || isObsolete(tag)) return
      options.applyData(data)
      hasData.value = true
      retryCount = 0
      options.saveSnapshot?.(data)
    } catch (requestError) {
      if (disposed || isObsolete(tag)) return
      const message = requestError instanceof Error ? requestError.message : String(requestError)
      const label = options.label()
      logger.warn(`获取${label}活动数据失败: ${message}`)
      if (hasData.value) {
        options.markStale()
      } else {
        options.markUnavailable(label)
      }
      if (retryCount < MAX_RETRIES) {
        retryCount += 1
        if (active) {
          scheduleRetry()
        } else {
          // 模块隐藏期间不重试，重新可见时补一次
          retryPending = true
        }
      }
    } finally {
      if (timer !== null) window.clearTimeout(timer)
      // 环境已变时不关新环境的加载态，交给新一轮请求收尾
      if (!disposed && !isObsolete(tag)) {
        loading.value = false
      }
    }
  }

  const scheduleRetry = () => {
    retryTimer = window.setTimeout(() => {
      retryTimer = null
      void load()
    }, RETRY_DELAY_MS)
  }

  const restore = () => {
    const ok = options.restoreSnapshot?.() === true
    if (ok) hasData.value = true
    return ok
  }

  if (restore() === false && (options.loadingOnInit ?? true)) {
    loading.value = true
  }

  const start = () => {
    if (disposed) return
    active = true
    if (!started) {
      started = true
      if (options.loadingOnStart) {
        loading.value = !hasData.value
      }
      void load()
    } else if (retryPending) {
      retryPending = false
      void load()
    }
  }

  const stop = () => {
    active = false
    if (retryTimer !== null) {
      clearRetry()
      retryPending = true
    }
  }

  const resume = () => {
    if (disposed) return
    // 排队中的重试先丢掉：留着它会在新请求之后再打一次，同一环境下出现重复请求
    if (retryTimer !== null) {
      clearRetry()
    }
    if (!started) return
    if (active) {
      void load()
    } else {
      retryPending = true
    }
  }

  onScopeDispose(() => {
    disposed = true
    clearRetry()
  })

  return {
    loading,
    hasData,
    start,
    stop,
    refresh: () => {
      retryCount = 0
      void load()
    },
    reload: () => {
      void load()
    },
    resume,
    resetRetry: () => {
      retryCount = 0
    },
    restore,
  }
}
