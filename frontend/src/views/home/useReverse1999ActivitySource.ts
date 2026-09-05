import { onScopeDispose, ref } from 'vue'
import type { SraActivityItem, SraActivityOverview } from '@/types/home'

const logger = window.electronAPI.getLogger('活动数据')

/** 与后端 Reverse1999ActivityService 对齐的请求超时与失败重试节奏 */
const FETCH_TIMEOUT_MS = 20_000
const RETRY_DELAY_MS = 30_000
const MAX_RETRIES = 8

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

const parseTime = (value: unknown): Date | null => {
  if (!value) return null
  const ms = Number(value)
  if (!Number.isFinite(ms)) return null
  const d = new Date(ms)
  return Number.isNaN(d.getTime()) ? null : d
}

const formatTime = (date: Date | null): string =>
  date ? date.toISOString().slice(0, 19) : ''

/** 复刻后端的版本选择：进行中 > 即将开始 > 已结束 */
const selectVersion = (data: Record<string, RawVersion>): RawVersion | null => {
  const now = Date.now()
  const versions = Object.entries(data)
    .map(([key, version]) => ({ key, version, s: parseTime(version.start_time), e: parseTime(version.end_time) }))
    .filter(item => item.version && typeof item.version === 'object')
  const active = versions.filter(v => v.s && v.e && v.s.getTime() <= now && now <= v.e.getTime())
  if (active.length > 0) return active[0].version
  const upcoming = versions.filter(v => v.s && v.s.getTime() > now)
  if (upcoming.length > 0) return upcoming.sort((a, b) => (a.s?.getTime() ?? 0) - (b.s?.getTime() ?? 0))[0].version
  const ended = versions.filter(v => v.e && v.e.getTime() <= now)
  if (ended.length > 0) return ended.sort((a, b) => (b.e?.getTime() ?? 0) - (a.e?.getTime() ?? 0))[0].version
  return null
}

const formatActivity = (activity: RawActivity, key: string): SraActivityItem => ({
  name: activity.name || activity.alias || EVENT_TYPE_NAME[activity.event_type || ''] || ACTIVITY_KEY_FALLBACK[key] || key,
  description: EVENT_TYPE_NAME[activity.event_type || ''] ?? '',
  startTime: formatTime(parseTime(activity.start_time)),
  endTime: formatTime(parseTime(activity.end_time)),
  cover: '',
})

const buildOverview = (data: Record<string, RawVersion>, versionId: string): SraActivityOverview => {
  const version = selectVersion(data)
  if (!version) {
    return { Available: false, Stale: false, Message: '', version: '', versionName: '', cover: '', startTime: '', endTime: '', activities: [] }
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
    activities: Object.entries(version.activity || {}).map(([key, activity]) => formatActivity(activity, key)),
  }
}

const snapshotKey = 'auto-mas.home.reverse1999-snapshot'

/** 1999 活动数据的直连数据源（首页全前端化）。与后端职责对齐，带快照与独立失败态。 */
export const useReverse1999ActivitySource = () => {
  const overview = ref<SraActivityOverview>(buildOverview({}, ''))
  const loading = ref(false)
  const hasData = ref(false)
  let retryTimer: number | null = null
  let retryCount = 0
  let disposed = false

  try {
    const raw = localStorage.getItem(snapshotKey)
    if (raw) {
      const cached = JSON.parse(raw) as { versionId: string; data: Record<string, RawVersion> }
      overview.value = buildOverview(cached.data, cached.versionId)
      hasData.value = true
    }
  } catch {
    // 快照损坏按无缓存处理
  }
  if (!hasData.value) {
    loading.value = true
  }

  const load = async () => {
    if (disposed) return
    try {
      const controller = new AbortController()
      const timer = window.setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS)
      let response: Response
      try {
        response = await fetch(SOURCE_URL, { signal: controller.signal, headers: { Accept: 'application/json' } })
      } finally {
        window.clearTimeout(timer)
      }
      if (!response.ok) throw new Error('HTTP ' + response.status)
      const data = (await response.json()) as Record<string, RawVersion>
      const versionId = (() => {
        const now = Date.now()
        for (const [key, v] of Object.entries(data)) {
          const s = parseTime(v?.start_time), e = parseTime(v?.end_time)
          if (s && e && s.getTime() <= now && now <= e.getTime()) return key
        }
        return Object.keys(data)[0] ?? ''
      })()
      overview.value = buildOverview(data, versionId)
      hasData.value = true
      retryCount = 0
      try { localStorage.setItem(snapshotKey, JSON.stringify({ versionId, data })) } catch { /* 跳过快照 */ }
    } catch (requestError) {
      if (disposed) return
      const errorMessage = requestError instanceof Error ? requestError.message : String(requestError)
      logger.warn('获取' + DISPLAY_NAME + '活动数据失败: ' + errorMessage)
      if (hasData.value) {
        overview.value = { ...overview.value, Stale: true, Message: '正在使用上次成功获取的活动数据' }
      } else {
        overview.value = buildOverview({}, '')
        overview.value.Message = DISPLAY_NAME + '活动数据暂不可用'
      }
      if (retryCount < MAX_RETRIES) {
        retryCount += 1
        retryTimer = window.setTimeout(() => { retryTimer = null; void load() }, RETRY_DELAY_MS)
      }
    } finally {
      if (!disposed) loading.value = false
    }
  }

  onScopeDispose(() => {
    disposed = true
    if (retryTimer !== null) { window.clearTimeout(retryTimer); retryTimer = null }
  })

  void load()

  return { overview, loading, refresh: () => { retryCount = 0; void load() } }
}
