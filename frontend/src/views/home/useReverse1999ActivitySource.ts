import { ref } from 'vue'
import type { SraActivityItem, SraActivityOverview } from '@/types/home'
import { useHomeActivitySource } from './useHomeActivitySource'

/** 与后端 Reverse1999ActivityService 对齐的请求超时 */
const FETCH_TIMEOUT_MS = 20_000

const SOURCE_URL = 'https://api.1999.fan/api/data/activity/cn.json'
const DISPLAY_NAME = '1999'
const BANNER_URL = 'https://re.bluepoch.com/assets/img/BG.jpg'

const ACTIVITY_KEY_FALLBACK: Record<string, string> = {
  combat: '版本活动',
  're-release': '复刻活动',
  anecdote: '轶事活动',
}

const EVENT_TYPE_NAME: Record<string, string> = {
  MainStory: '主线活动',
  SideStory: '限时活动',
}

interface RawActivity {
  event_type?: string
  name?: string
  alias?: string
  start_time?: number
  end_time?: number
}

interface RawVersion {
  version_name?: string
  start_time?: number
  end_time?: number
  activity?: Record<string, RawActivity>
}

/** 快照里存的是原始数据与当时选中的版本，恢复时重新算一遍概览 */
interface SnapshotPayload {
  versionId: string
  data: Record<string, RawVersion>
}

const parseTime = (value: unknown): Date | null => {
  if (!value) return null
  const ms = Number(value)
  if (!Number.isFinite(ms)) return null
  const d = new Date(ms)
  return Number.isNaN(d.getTime()) ? null : d
}

// 必须保留 toISOString() 末尾的 Z：切成裸 ISO 串后，消费端的 new Date(value) 会按
// 本机时区解析，倒计时与「已结束」判定整体提前一个时区偏移量（东八区提前 8 小时）。
// 被 #497 删掉的后端接口输出的也是带 +08:00 偏移的时间。
const formatTime = (date: Date | null): string => (date ? date.toISOString() : '')

/** 复刻后端的版本选择：进行中 > 即将开始 > 已结束 */
const selectVersion = (data: Record<string, RawVersion>): RawVersion | null => {
  const now = Date.now()
  const versions = Object.entries(data)
    .map(([key, version]) => ({
      key,
      version,
      s: parseTime(version.start_time),
      e: parseTime(version.end_time),
    }))
    .filter(item => item.version && typeof item.version === 'object')
  const active = versions.filter(v => v.s && v.e && v.s.getTime() <= now && now <= v.e.getTime())
  if (active.length > 0) return active[0].version
  const upcoming = versions.filter(v => v.s && v.s.getTime() > now)
  if (upcoming.length > 0)
    return upcoming.sort((a, b) => (a.s?.getTime() ?? 0) - (b.s?.getTime() ?? 0))[0].version
  const ended = versions.filter(v => v.e && v.e.getTime() <= now)
  if (ended.length > 0)
    return ended.sort((a, b) => (b.e?.getTime() ?? 0) - (a.e?.getTime() ?? 0))[0].version
  return null
}

/** 当前该报哪个版本：先找进行中的那个键，都没有就退回第一个 */
const pickVersionId = (data: Record<string, RawVersion>): string => {
  const now = Date.now()
  for (const [key, version] of Object.entries(data)) {
    const s = parseTime(version?.start_time)
    const e = parseTime(version?.end_time)
    if (s && e && s.getTime() <= now && now <= e.getTime()) return key
  }
  return Object.keys(data)[0] ?? ''
}

const formatActivity = (activity: RawActivity, key: string): SraActivityItem => ({
  name:
    activity.name ||
    activity.alias ||
    EVENT_TYPE_NAME[activity.event_type || ''] ||
    ACTIVITY_KEY_FALLBACK[key] ||
    key,
  description: EVENT_TYPE_NAME[activity.event_type || ''] ?? '',
  startTime: formatTime(parseTime(activity.start_time)),
  endTime: formatTime(parseTime(activity.end_time)),
  cover: '',
})

const buildOverview = (
  data: Record<string, RawVersion>,
  versionId: string
): SraActivityOverview => {
  const version = selectVersion(data)
  if (!version) {
    return {
      Available: false,
      Stale: false,
      Message: '',
      version: '',
      versionName: '',
      cover: '',
      startTime: '',
      endTime: '',
      activities: [],
    }
  }
  return {
    Available: true,
    Stale: false,
    Message: '',
    version: versionId,
    versionName: version.version_name || '',
    cover: BANNER_URL,
    startTime: formatTime(parseTime(version.start_time)),
    endTime: formatTime(parseTime(version.end_time)),
    activities: Object.entries(version.activity || {}).map(([key, activity]) =>
      formatActivity(activity, key)
    ),
  }
}

const SNAPSHOT_KEY = 'auto-mas.home.reverse1999-snapshot'

/**
 * 1999 活动数据的直连数据源（首页全前端化）。
 *
 * 取数带超时、失败退避重试、本地快照与独立失败态，这些节奏交给公共骨架；
 * 这里只负责取数、挑版本与字段收口。
 */
export const useReverse1999ActivitySource = () => {
  const overview = ref<SraActivityOverview>(buildOverview({}, ''))

  const source = useHomeActivitySource<SnapshotPayload>({
    label: () => DISPLAY_NAME,
    timeoutMs: FETCH_TIMEOUT_MS,
    restoreSnapshot: () => {
      try {
        const raw = localStorage.getItem(SNAPSHOT_KEY)
        if (!raw) return false
        const cached = JSON.parse(raw) as SnapshotPayload
        overview.value = buildOverview(cached.data, cached.versionId)
        return true
      } catch {
        // 快照损坏按无缓存处理
        return false
      }
    },
    saveSnapshot: payload => {
      try {
        localStorage.setItem(SNAPSHOT_KEY, JSON.stringify(payload))
      } catch {
        // 存储写不进去就算了，下次照常从网络取
      }
    },
    fetchData: async signal => {
      const response = await fetch(SOURCE_URL, {
        signal,
        headers: { Accept: 'application/json' },
      })
      if (!response.ok) throw new Error('HTTP ' + response.status)
      const data = (await response.json()) as Record<string, RawVersion>
      return { versionId: pickVersionId(data), data }
    },
    applyData: payload => {
      overview.value = buildOverview(payload.data, payload.versionId)
    },
    markStale: () => {
      overview.value = {
        ...overview.value,
        Stale: true,
        Message: '正在使用上次成功获取的活动数据',
      }
    },
    markUnavailable: () => {
      overview.value = { ...buildOverview({}, ''), Message: DISPLAY_NAME + '活动数据暂不可用' }
    },
  })

  return {
    overview,
    loading: source.loading,
    start: source.start,
    stop: source.stop,
    refresh: source.refresh,
  }
}
