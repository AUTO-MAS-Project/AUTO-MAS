import { computed, onScopeDispose, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { BlueArchiveActivityIn, GetService } from '@/api'
import { createEmptySraActivityOverview } from '@/types/home'
import type {
  BlueArchiveActivityOverview,
  BlueArchiveServerKey,
  BlueArchiveServerOverview,
} from '@/types/home'
import type { Ref } from 'vue'

const logger = window.electronAPI.getLogger('活动数据')

/** 与其它活动源一致的请求超时与失败重试节奏 */
const FETCH_TIMEOUT_MS = 20_000
const RETRY_DELAY_MS = 30_000
const MAX_RETRIES = 8
const REFRESH_INTERVAL_MS = 10 * 60 * 1000

/**
 * 数据取自 Kivo 古书馆时间轴，但那个接口对 Origin 做了白名单校验（只放行
 * kivo.wiki 自己的来源），浏览器直连必定 403，因此统一走本软件后端中转。
 * 后端只做转发，筛选与格式转换仍在这里完成。
 */

/** 每页 50 条且按时间倒序，3 页足以覆盖最近数周 */
const PAGE_SIZE = 50
const MAX_PAGES = 3

/** 往前多带几天已经结束的活动，让卡片在活动间隙里也有内容可显示 */
const RECENT_WINDOW_DAYS = 14
const SECONDS_PER_DAY = 86_400

/** Kivo 的 body_summary 很长（含话题标签），按卡片展示宽度截断 */
const DESCRIPTION_MAX_LENGTH = 200

/** 只取「活动」；卡池、掉落加倍、维护等分类不进卡片 */
const WANTED_TYPE = 'Event'

/** 三个服与 Kivo 的 line_type 对应关系（国际服的原文拼写就是 Globle） */
const SERVER_LINE_TYPES: Record<BlueArchiveServerKey, BlueArchiveActivityIn.line_type> = {
  jp: BlueArchiveActivityIn.line_type.JP,
  global: BlueArchiveActivityIn.line_type.GLOBLE,
  cn: BlueArchiveActivityIn.line_type.CN,
}

/** 默认展示顺序：国服优先（国服玩家最多），三个服的先后不影响各自独立取数 */
const SERVER_KEYS: BlueArchiveServerKey[] = ['cn', 'jp', 'global']

/**
 * 固定 +08:00 偏移（Asia/Shanghai 无夏令时）。
 * Kivo 的时间戳是 Unix 秒，而 SRA 格式的时间字段不带时区标记、按其惯例填北京时间。
 */
const TIMEZONE_OFFSET_MS = 8 * 60 * 60 * 1000

interface KivoTimelineItem {
  title?: string
  image?: string
  body_summary?: string
  type?: string
  start_time?: number
  end_time?: number
}

interface KivoTimelineResponse {
  data?: { timeline?: KivoTimelineItem[] }
}

/** 快照里存整份 overview，恢复时重置 Stale / Message 这两个运行时元数据 */
const snapshotKey = (server: BlueArchiveServerKey) => 'auto-mas.home.bluearchive-snapshot.' + server

const pad = (value: number) => String(value).padStart(2, '0')

/**
 * Unix 秒 → 带 +08:00 偏移的北京时间 ISO 串。
 *
 * 偏移不能省：卡片的消费端一律 `new Date(值)` 解析，没有时区标记的裸字符串
 * 会被当成本地时间，在北京时间以外的设备上活动状态与倒计时会整体偏掉
 * （1999 活动源也踩过同一个坑）。
 */
const formatTime = (seconds: number): string => {
  const shifted = new Date(seconds * 1000 + TIMEZONE_OFFSET_MS)
  return (
    shifted.getUTCFullYear() +
    '-' +
    pad(shifted.getUTCMonth() + 1) +
    '-' +
    pad(shifted.getUTCDate()) +
    'T' +
    pad(shifted.getUTCHours()) +
    ':' +
    pad(shifted.getUTCMinutes()) +
    ':' +
    pad(shifted.getUTCSeconds()) +
    '+08:00'
  )
}

/** 碧蓝档案没有版本号概念，用北京时间当月占位，保证字段齐全 */
const currentMonth = (): string => {
  const shifted = new Date(Date.now() + TIMEZONE_OFFSET_MS)
  return shifted.getUTCFullYear() + '-' + pad(shifted.getUTCMonth() + 1)
}

/** Kivo 的图片地址是协议相对 URL（//static...），补全为 https */
const normalizeImage = (image: string | undefined): string => {
  if (!image) return ''
  return image.startsWith('//') ? 'https:' + image : image
}

/**
 * 原始时间轴 → SRA 活动条目：筛分类、去重、按开始时间升序。
 *
 * 与 Kivo 时间轴的取值口径保持一致：同一活动可能被拆成「活动」与
 * 「活动介绍PV」等多条记录，只保留结束时间最晚的那条。
 */
const buildActivities = (items: KivoTimelineItem[], nowSeconds: number) => {
  const horizon = nowSeconds - RECENT_WINDOW_DAYS * SECONDS_PER_DAY
  const picked = new Map<string, { item: KivoTimelineItem; start: number; end: number }>()

  for (const item of items) {
    if (item.type !== WANTED_TYPE) continue
    const start = item.start_time
    const end = item.end_time
    if (typeof start !== 'number' || typeof end !== 'number') continue
    if (end < horizon) continue

    const name = (item.title ?? '').trim()
    if (!name) continue

    const existing = picked.get(name)
    if (existing && existing.end >= end) continue
    picked.set(name, { item, start, end })
  }

  return [...picked.entries()]
    .sort((left, right) => left[1].start - right[1].start)
    .map(([name, row]) => ({
      name,
      description: (row.item.body_summary ?? '').trim().slice(0, DESCRIPTION_MAX_LENGTH),
      startTime: formatTime(row.start),
      endTime: formatTime(row.end),
      cover: normalizeImage(row.item.image),
    }))
}

/**
 * 横幅的起始 / 结束取**当前这批活动**的区间。
 *
 * 直接拿整份数据里最晚的结束时间是不对的：Kivo 会提前放出后面的活动，
 * 于是「剩余时间」倒数的会是还没开始的那一期。所以先看正在进行中的活动，
 * 没有进行中的就退回最近结束的那一次（横幅如实显示「已结束」），
 * 两者都没有才用还没开始的活动。
 */
const buildOverview = (
  items: KivoTimelineItem[],
  versionName: string
): BlueArchiveActivityOverview => {
  const activities = buildActivities(items, Date.now() / 1000)
  const now = Date.now()
  const toTimestamp = (value: string) => new Date(value).getTime()

  // activities 已按开始时间升序，所以取首尾即可
  const running = activities.filter(
    activity => toTimestamp(activity.startTime) <= now && toTimestamp(activity.endTime) > now
  )
  const ended = activities.filter(activity => toTimestamp(activity.endTime) <= now)
  const upcoming = activities.filter(activity => toTimestamp(activity.startTime) > now)
  const current = running.length ? running : ended.length ? ended : upcoming

  return {
    Available: true,
    Stale: false,
    Message: '',
    version: currentMonth(),
    versionName,
    startTime: current[0]?.startTime ?? '',
    endTime: current[current.length - 1]?.endTime ?? '',
    activities,
  }
}

/** 一个服务器的运行时状态：重试计数与定时器按服隔离，一个服挂掉不拖累另外两个 */
interface ServerRuntime {
  key: BlueArchiveServerKey
  overview: Ref<BlueArchiveActivityOverview>
  retryTimer: number | null
  retryCount: number
  hasData: boolean
  retryPending: boolean
  requesting: boolean
}

/** 拉取一个服的完整时间轴（分页直到空页或达到页数上限） */
const fetchTimeline = async (
  server: BlueArchiveServerKey,
  signal: AbortSignal
): Promise<KivoTimelineItem[]> => {
  const items: KivoTimelineItem[] = []
  for (let page = 1; page <= MAX_PAGES; page += 1) {
    const request = GetService.getBluearchiveActivityApiInfoBluearchiveActivityPost({
      line_type: SERVER_LINE_TYPES[server],
      page,
      page_size: PAGE_SIZE,
    })

    // 生成的客户端返回 CancelablePromise、不接受 AbortSignal，
    // 用它自带的 cancel 桥接外层的整体超时，避免超时后请求还悬着
    const cancelOnAbort = () => request.cancel()
    signal.addEventListener('abort', cancelOnAbort, { once: true })

    let payload: KivoTimelineResponse
    try {
      const result = await request
      if (result.code !== 200) {
        throw new Error(result.message || 'HTTP ' + result.code)
      }
      // 后端把 Kivo 的响应原样放在 data 里
      payload = result.data as unknown as KivoTimelineResponse
    } finally {
      signal.removeEventListener('abort', cancelOnAbort)
    }

    const batch = payload.data?.timeline
    if (!Array.isArray(batch) || batch.length === 0) break
    items.push(...batch)
  }
  return items
}

/**
 * 碧蓝档案活动数据的直连数据源（Kivo 古书馆时间轴）。
 *
 * 与其它活动源的职责一致：带超时、失败退避重试、本地快照
 * （stale-while-revalidate）与独立失败态。区别在于碧蓝档案分日/国际/国
 * 三个服，这里为每个服各跑一份完整状态——请求、重试、快照、错误都不互通，
 * 所以一个服不可用时另外两个服照常显示，卡片也只需切显示、无需重新请求。
 */
export const useBlueArchiveActivitySource = () => {
  const { t } = useI18n()

  const serverLabel = (server: BlueArchiveServerKey) => t(`home.bluearchive.server.${server}`)
  const serverVersionName = (server: BlueArchiveServerKey) =>
    t('home.bluearchive.versionName', { server: serverLabel(server) })

  const runtimes: ServerRuntime[] = SERVER_KEYS.map(key => ({
    key,
    overview: ref<BlueArchiveActivityOverview>(createEmptySraActivityOverview()),
    retryTimer: null,
    retryCount: 0,
    hasData: false,
    retryPending: false,
    requesting: false,
  }))

  const loadingByServer: Record<BlueArchiveServerKey, boolean> = reactive({
    jp: false,
    global: false,
    cn: false,
  })
  const selectedServer = ref<BlueArchiveServerKey>(SERVER_KEYS[0])

  let active = false
  let started = false
  let disposed = false
  let refreshTimer: number | null = null

  // 启动先用上次快照填卡片，不等网络
  for (const runtime of runtimes) {
    try {
      const raw = localStorage.getItem(snapshotKey(runtime.key))
      if (raw) {
        const cached = JSON.parse(raw) as BlueArchiveActivityOverview
        runtime.overview.value = {
          ...createEmptySraActivityOverview(),
          ...cached,
          Stale: true,
          Message: t('home.bluearchive.staleMessage'),
          // 服名随界面语言变化，按当前语言重算，避免切换语言后残留旧语言的版本名
          versionName: serverVersionName(runtime.key),
        }
        runtime.hasData = true
      }
    } catch {
      // 快照损坏按无缓存处理
    }
    if (!runtime.hasData) {
      loadingByServer[runtime.key] = true
    }
  }

  const loadServer = async (runtime: ServerRuntime) => {
    if (disposed || runtime.requesting) return
    runtime.requesting = true
    try {
      const controller = new AbortController()
      const timer = window.setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS)
      let items: KivoTimelineItem[]
      try {
        items = await fetchTimeline(runtime.key, controller.signal)
      } finally {
        window.clearTimeout(timer)
      }
      if (disposed) return

      const overview = buildOverview(items, serverVersionName(runtime.key))
      runtime.overview.value = overview
      runtime.hasData = true
      runtime.retryCount = 0
      try {
        localStorage.setItem(snapshotKey(runtime.key), JSON.stringify(overview))
      } catch {
        // 本地存储不可用时仅跳过快照缓存
      }
    } catch (requestError) {
      if (disposed) return
      const errorMessage =
        requestError instanceof Error ? requestError.message : String(requestError)
      logger.warn('获取碧蓝档案' + serverLabel(runtime.key) + '活动数据失败: ' + errorMessage)

      runtime.overview.value = runtime.hasData
        ? {
            ...runtime.overview.value,
            Stale: true,
            Message: t('home.bluearchive.staleMessage'),
          }
        : {
            ...createEmptySraActivityOverview(),
            Message: t('home.bluearchive.unavailable', { server: serverLabel(runtime.key) }),
          }

      if (runtime.retryCount < MAX_RETRIES) {
        runtime.retryCount += 1
        if (active) {
          scheduleRetry(runtime)
        } else {
          // 模块隐藏期间不重试，重新可见时补一次
          runtime.retryPending = true
        }
      }
    } finally {
      runtime.requesting = false
      if (!disposed) {
        loadingByServer[runtime.key] = false
      }
    }
  }

  const scheduleRetry = (runtime: ServerRuntime) => {
    runtime.retryTimer = window.setTimeout(() => {
      runtime.retryTimer = null
      void loadServer(runtime)
    }, RETRY_DELAY_MS)
  }

  const scheduleRefresh = () => {
    if (!active || disposed || refreshTimer !== null) return
    refreshTimer = window.setTimeout(() => {
      refreshTimer = null
      for (const runtime of runtimes) void loadServer(runtime)
      scheduleRefresh()
    }, REFRESH_INTERVAL_MS)
  }

  // 模块可见时才发请求；隐藏时停掉重试定时器，重新可见时把攒下的重试补上
  const start = () => {
    if (disposed) return
    active = true
    if (!started) {
      started = true
      for (const runtime of runtimes) void loadServer(runtime)
    } else {
      // 栏目重新显示时立即校验，避免继续展示隐藏期间已经过期的活动。
      for (const runtime of runtimes) {
        runtime.retryPending = false
        void loadServer(runtime)
      }
    }
    scheduleRefresh()
  }

  const stop = () => {
    active = false
    if (refreshTimer !== null) {
      window.clearTimeout(refreshTimer)
      refreshTimer = null
    }
    for (const runtime of runtimes) {
      if (runtime.retryTimer !== null) {
        window.clearTimeout(runtime.retryTimer)
        runtime.retryTimer = null
        runtime.retryPending = true
      }
    }
  }

  onScopeDispose(() => {
    disposed = true
    if (refreshTimer !== null) {
      window.clearTimeout(refreshTimer)
      refreshTimer = null
    }
    for (const runtime of runtimes) {
      if (runtime.retryTimer !== null) {
        window.clearTimeout(runtime.retryTimer)
        runtime.retryTimer = null
      }
    }
  })

  return {
    servers: computed<BlueArchiveServerOverview[]>(() =>
      runtimes.map(runtime => ({
        key: runtime.key,
        label: serverLabel(runtime.key),
        overview: runtime.overview.value,
      }))
    ),
    selectedServer,
    loadingByServer,
    selectServer: (server: BlueArchiveServerKey) => {
      selectedServer.value = server
    },
    start,
    stop,
    refresh: () => {
      for (const runtime of runtimes) {
        runtime.retryCount = 0
        void loadServer(runtime)
      }
    },
  }
}
