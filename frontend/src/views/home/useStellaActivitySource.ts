import { onScopeDispose, ref } from 'vue'
import { GetService } from '@/api'
import { createEmptySraActivityOverview } from '@/types/home'
import type { SraActivityItem, SraActivityOverview } from '@/types/home'

const logger = window.electronAPI.getLogger('活动数据')

/** 与其它活动源一致的失败重试节奏 */
const RETRY_DELAY_MS = 30_000
const MAX_RETRIES = 8

/** 后端从官网活动公告里解析出来的条目 */
interface StellaOfficialActivity {
  name?: string
  kind?: string
  startTime?: string
  endTime?: string
  cover?: string
  description?: string
}

const toTimestamp = (value: string) => {
  const timestamp = new Date(value).getTime()
  return Number.isNaN(timestamp) ? 0 : timestamp
}

/**
 * 官网条目 → 卡片形状。后端已经把维护公告之类的杂项筛掉了，这里只做
 * 字段收口与排序；缺名字或时间的条目界面没法展示，按不存在处理。
 */
const buildActivities = (raw: StellaOfficialActivity[]): SraActivityItem[] =>
  raw
    .filter(item => item.name && item.startTime && item.endTime)
    .map(item => ({
      name: item.name as string,
      description: item.description ?? '',
      startTime: item.startTime as string,
      endTime: item.endTime as string,
      cover: item.cover ?? '',
      kind: item.kind ?? '',
    }))
    .sort((left, right) => toTimestamp(left.startTime) - toTimestamp(right.startTime))

/**
 * 横幅报「当前那一期」：优先进行中的（同时有多期时取最早结束的），
 * 其次还没开始的，最后退回最近结束的那场——与其它活动源同一套口径。
 */
const buildOverview = (raw: StellaOfficialActivity[]): SraActivityOverview => {
  const activities = buildActivities(raw)
  const now = Date.now()

  const running = activities.filter(
    activity => toTimestamp(activity.startTime) <= now && toTimestamp(activity.endTime) > now
  )
  const upcoming = activities.filter(activity => toTimestamp(activity.startTime) > now)
  const ended = activities.filter(activity => toTimestamp(activity.endTime) <= now)
  const current = running[0] ?? upcoming[0] ?? ended[ended.length - 1]

  return {
    Available: true,
    Stale: false,
    Message: '',
    version: '',
    versionName: current?.name ?? '',
    cover: current?.cover ?? '',
    startTime: current?.startTime ?? '',
    endTime: current?.endTime ?? '',
    activities,
  }
}

/**
 * 星塔旅人活动数据的后端中转数据源。
 *
 * 官网 CMS 不放开跨域、也认 Referer，浏览器直连拿不到，所以取数走后端
 * `POST /api/info/stella/activity`：后端把官网公告整理成与其它游戏一致的形状
 * （活动名、分类、起止时间、封面），这里只做收口与失败降级——与碧蓝档案、
 * 明日方舟那两条链路同一形状。
 */
export const useStellaActivitySource = () => {
  const overview = ref<SraActivityOverview>(createEmptySraActivityOverview())
  const loading = ref(false)
  const hasData = ref(false)
  let retryTimer: number | null = null
  let retryCount = 0
  let disposed = false
  let active = false
  let started = false
  let retryPending = false

  const load = async () => {
    if (disposed) return
    try {
      const response = await GetService.getStellaActivityApiInfoStellaActivityPost()
      // 生成的客户端对 200 响应一律 resolve，后端用 code=500 表达取数失败，
      // 不查这一层就会把失败当成「拿到了空排期」，卡片显示「暂无进行中的活动」
      if (response.code !== 200) {
        throw new Error(response.message || 'HTTP ' + response.code)
      }
      const payload = (response.data ?? {}) as { activities?: StellaOfficialActivity[] }
      overview.value = buildOverview(payload.activities ?? [])
      hasData.value = true
      retryCount = 0
    } catch (requestError) {
      if (disposed) return
      const errorMessage =
        requestError instanceof Error ? requestError.message : String(requestError)
      logger.warn('获取星塔旅人活动数据失败: ' + errorMessage)

      overview.value = hasData.value
        ? // 保留上一次的内容并挂上 stale 标记，卡片据此提示数据可能已过期
          { ...overview.value, Stale: true }
        : createEmptySraActivityOverview()

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
      if (!disposed) {
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

  const start = () => {
    if (disposed) return
    active = true
    if (!started) {
      started = true
      loading.value = !hasData.value
      void load()
    } else if (retryPending) {
      retryPending = false
      void load()
    }
  }

  const stop = () => {
    active = false
    if (retryTimer !== null) {
      window.clearTimeout(retryTimer)
      retryTimer = null
      retryPending = true
    }
  }

  onScopeDispose(() => {
    disposed = true
    if (retryTimer !== null) {
      window.clearTimeout(retryTimer)
      retryTimer = null
    }
  })

  return {
    overview,
    loading,
    start,
    stop,
    refresh: () => {
      retryCount = 0
      void load()
    },
  }
}
