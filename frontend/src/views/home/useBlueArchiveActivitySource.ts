import { computed, onScopeDispose, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { BlueArchiveActivityIn, GetService, OpenAPI } from '@/api'
import { createEmptySraActivityOverview } from '@/types/home'
import type {
  BlueArchiveActivityOverview,
  BlueArchiveServerKey,
  BlueArchiveServerOverview,
} from '@/types/home'
import type { Ref } from 'vue'
import { useHomeActivitySource } from './useHomeActivitySource'
import type { HomeActivitySource } from './useHomeActivitySource'

/** 请求超时；重试节奏与快照调度交给公共骨架 */
const FETCH_TIMEOUT_MS = 20_000
const REFRESH_INTERVAL_MS = 10 * 60 * 1000

/**
 * 数据取自 GameKee 的活动表（三个服都有），那个接口认自定义头、响应也没给跨域头，
 * 浏览器直连取不到，因此统一走本软件后端中转。后端只做转发，筛选与格式转换在这里完成。
 */

/** 每页 100 条、两页足够放下三个服的当期活动与最近结束的那些 */
const PAGE_SIZE = 100
const MAX_PAGES = 2

/** 往前多带几天已经结束的活动，让卡片在活动间隙里也有内容可显示 */
const RECENT_WINDOW_DAYS = 14
const SECONDS_PER_DAY = 86_400

/** GameKee 的 description 与图片都很短，按卡片展示宽度截断 */
const DESCRIPTION_MAX_LENGTH = 200

/** 三个服与后端入参的对应关系（国际服的原文拼写就是 Globle） */
const SERVER_LINE_TYPES: Record<BlueArchiveServerKey, BlueArchiveActivityIn.line_type> = {
  jp: BlueArchiveActivityIn.line_type.JP,
  global: BlueArchiveActivityIn.line_type.GLOBLE,
  cn: BlueArchiveActivityIn.line_type.CN,
}

/** 默认展示顺序：国服优先（国服玩家最多），三个服的先后不影响各自独立取数 */
const SERVER_KEYS: BlueArchiveServerKey[] = ['cn', 'jp', 'global']
const SELECTED_SERVER_STORAGE_KEY = 'auto-mas.home.bluearchive-selected-server'

const readSelectedServer = (): BlueArchiveServerKey => {
  try {
    const stored = localStorage.getItem(SELECTED_SERVER_STORAGE_KEY)
    return SERVER_KEYS.find(key => key === stored) ?? SERVER_KEYS[0]
  } catch {
    return SERVER_KEYS[0]
  }
}

/**
 * 固定 +08:00 偏移（Asia/Shanghai 无夏令时）。
 * GameKee 的时间戳是 Unix 秒，而 SRA 格式的时间字段不带时区标记、按其惯例填北京时间。
 */
const TIMEZONE_OFFSET_MS = 8 * 60 * 60 * 1000

interface GameKeeActivity {
  title?: string
  picture?: string
  description?: string
  /** 中文分类名：活动 / 总力大决 / 爬塔 / 多倍活动 / 战术测试 / 指引任务 / 其他 */
  activity_kind_name?: string
  begin_at?: number
  end_at?: number
}

interface GameKeeResponse {
  code?: number
  data?: GameKeeActivity[]
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

/**
 * GameKee 的图片地址是协议相对 URL（//cdnimg...），补全成 https 后还要走后端中转：
 * 那个 CDN 校验 Referer，页面直连（Referer 是本软件）必定被拒。
 */
const normalizeImage = (image: string | undefined): string => {
  if (!image) return ''
  const absolute = image.startsWith('//') ? 'https:' + image : image
  return `${OpenAPI.BASE}/api/info/bluearchive/image?url=${encodeURIComponent(absolute)}`
}

/**
 * 原始时间轴 → SRA 活动条目：筛分类、去重、按开始时间升序。
 *
 * 与数据源的取值口径保持一致：同一活动可能被拆成「活动」与
 * 「活动介绍PV」等多条记录，只保留结束时间最晚的那条。
 */
const buildActivities = (items: GameKeeActivity[], nowSeconds: number) => {
  const horizon = nowSeconds - RECENT_WINDOW_DAYS * SECONDS_PER_DAY
  const picked = new Map<string, { item: GameKeeActivity; start: number; end: number }>()

  for (const item of items) {
    const start = item.begin_at
    const end = item.end_at
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
      description: (row.item.description ?? '').trim().slice(0, DESCRIPTION_MAX_LENGTH),
      startTime: formatTime(row.start),
      endTime: formatTime(row.end),
      cover: normalizeImage(row.item.picture),
      kind: row.item.activity_kind_name ?? '',
    }))
}

/**
 * 横幅的起始 / 结束取**当前这批活动**的区间。
 *
 * 直接拿整份数据里最晚的结束时间是不对的：数据源会提前放出后面的活动，
 * 于是「剩余时间」倒数的会是还没开始的那一期。所以先看正在进行中的活动，
 * 没有进行中的就退回最近结束的那一次（横幅如实显示「已结束」），
 * 两者都没有才用还没开始的活动。
 */
const buildOverview = (
  items: GameKeeActivity[],
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

/** 拉取一个服的完整活动列表（分页直到空页或达到页数上限） */
const fetchTimeline = async (
  server: BlueArchiveServerKey,
  signal: AbortSignal
): Promise<GameKeeActivity[]> => {
  const items: GameKeeActivity[] = []
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

    let payload: GameKeeResponse
    try {
      const result = await request
      if (result.code !== 200) {
        throw new Error(result.message || 'HTTP ' + result.code)
      }
      // 后端把 GameKee 的响应原样放在 data 里
      payload = result.data as unknown as GameKeeResponse
    } finally {
      signal.removeEventListener('abort', cancelOnAbort)
    }

    if (payload.code !== 0) {
      throw new Error(payload.code ? `GameKee ${payload.code}` : 'GameKee 响应异常')
    }

    const batch = payload.data
    if (!Array.isArray(batch) || batch.length === 0) break
    items.push(...batch)
  }
  return items
}

/**
 * 碧蓝档案活动数据的直连数据源（GameKee 活动表）。
 *
 * 与其它活动源一样，取数、超时、失败退避重试、快照与失败态都交给公共骨架；区别在于
 * 碧蓝档案分日 / 国际 / 国三个服，所以这里给每个服各起一份骨架实例：请求、重试、快照、
 * 加载态互相不打扰，一个服取不到时另外两个照常显示，卡片只需切显示、无需重新请求。
 */
export const useBlueArchiveActivitySource = () => {
  const { t } = useI18n()

  const serverLabel = (server: BlueArchiveServerKey) => t(`home.bluearchive.server.${server}`)
  const serverVersionName = (server: BlueArchiveServerKey) =>
    t('home.bluearchive.versionName', { server: serverLabel(server) })

  const overviewByServer: Record<BlueArchiveServerKey, Ref<BlueArchiveActivityOverview>> = {
    jp: ref(createEmptySraActivityOverview()),
    global: ref(createEmptySraActivityOverview()),
    cn: ref(createEmptySraActivityOverview()),
  }
  const loadingByServer: Record<BlueArchiveServerKey, boolean> = reactive({
    jp: false,
    global: false,
    cn: false,
  })
  const selectedServer = ref<BlueArchiveServerKey>(readSelectedServer())

  // 每个服各跑一份完整调度：请求、重试、快照、加载态互相不打扰，
  // 一个服取不到时另外两个照常显示，卡片只切显示、不必重新请求
  const sources = {} as Record<BlueArchiveServerKey, HomeActivitySource>

  for (const key of SERVER_KEYS) {
    // 这个服是否已有请求在飞：交给骨架的 isBusy 钩子，同一份数据不会被并发拉两次
    let busy = false
    const source = useHomeActivitySource<GameKeeActivity[]>({
      // 日志与失败文案里用这个服自己的名字
      label: () => serverLabel(key),
      timeoutMs: FETCH_TIMEOUT_MS,
      isBusy: () => busy,
      restoreSnapshot: () => {
        try {
          const raw = localStorage.getItem(snapshotKey(key))
          if (!raw) return false
          const cached = JSON.parse(raw) as BlueArchiveActivityOverview
          overviewByServer[key].value = {
            ...createEmptySraActivityOverview(),
            ...cached,
            Stale: true,
            Message: t('home.bluearchive.staleMessage'),
            // 服名随界面语言变化，按当前语言重算，避免切换语言后残留旧语言的版本名
            versionName: serverVersionName(key),
          }
          return true
        } catch {
          // 快照损坏按无缓存处理
          return false
        }
      },
      saveSnapshot: overview => {
        try {
          localStorage.setItem(snapshotKey(key), JSON.stringify(overview))
        } catch {
          // 本地存储不可用时仅跳过快照缓存
        }
      },
      fetchData: async signal => {
        busy = true
        try {
          return await fetchTimeline(key, signal)
        } finally {
          busy = false
        }
      },
      applyData: items => {
        overviewByServer[key].value = buildOverview(items, serverVersionName(key))
      },
      markStale: () => {
        overviewByServer[key].value = {
          ...overviewByServer[key].value,
          Stale: true,
          Message: t('home.bluearchive.staleMessage'),
        }
      },
      markUnavailable: label => {
        overviewByServer[key].value = {
          ...createEmptySraActivityOverview(),
          Message: t('home.bluearchive.unavailable', { server: label }),
        }
      },
    })
    sources[key] = source
    // 加载态按服同步给卡片（骨架每个实例各有一个 loading）
    watch(
      source.loading,
      value => {
        loadingByServer[key] = value
      },
      { immediate: true }
    )
  }

  let active = false
  let started = false
  let disposed = false
  let refreshTimer: number | null = null

  /** 卡片还挂在页面上时，每 10 分钟把三个服都刷一遍 */
  const scheduleRefresh = () => {
    if (!active || disposed || refreshTimer !== null) return
    refreshTimer = window.setTimeout(() => {
      refreshTimer = null
      for (const key of SERVER_KEYS) sources[key].reload()
      scheduleRefresh()
    }, REFRESH_INTERVAL_MS)
  }

  // 模块可见时才发请求；隐藏时停掉重试定时器，重新可见时立即重校验一遍
  const start = () => {
    if (disposed) return
    active = true
    for (const key of SERVER_KEYS) {
      if (started) {
        // 栏目重新显示：隐藏期间活动可能已经过期，直接重取而不是等退避重试
        sources[key].resume()
      } else {
        sources[key].start()
      }
    }
    started = true
    scheduleRefresh()
  }

  const stop = () => {
    active = false
    if (refreshTimer !== null) {
      window.clearTimeout(refreshTimer)
      refreshTimer = null
    }
    for (const key of SERVER_KEYS) sources[key].stop()
  }

  onScopeDispose(() => {
    disposed = true
    if (refreshTimer !== null) {
      window.clearTimeout(refreshTimer)
      refreshTimer = null
    }
  })

  return {
    servers: computed<BlueArchiveServerOverview[]>(() =>
      SERVER_KEYS.map(key => ({
        key,
        label: serverLabel(key),
        overview: overviewByServer[key].value,
      }))
    ),
    selectedServer,
    loadingByServer,
    selectServer: (server: BlueArchiveServerKey) => {
      if (!SERVER_KEYS.includes(server)) return
      selectedServer.value = server
      try {
        localStorage.setItem(SELECTED_SERVER_STORAGE_KEY, server)
      } catch {
        // 存储不可用时仍允许切换，保留当前会话的选择。
      }
    },
    start,
    stop,
    refresh: () => {
      for (const key of SERVER_KEYS) sources[key].refresh()
    },
  }
}
