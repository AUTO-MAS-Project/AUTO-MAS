import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { GetService } from '@/api'
import { createEmptySraActivityOverview } from '@/types/home'
import type { SraActivityItem, SraActivityOverview } from '@/types/home'
import { useHomeActivitySource } from './useHomeActivitySource'

/**
 * 数据取自 PRTS wiki 的「活动一览」，由本软件后端解析成 JSON 后转发。
 * 页面每行都带活动名、分类、起止时间与配图，筛选与格式转换在数据源里完成。
 */

/** 与其它活动源一致的请求超时 */
const FETCH_TIMEOUT_MS = 20_000

/** 往前多带几天已经结束的活动，让卡片在活动间隙里也有内容可显示 */
const RECENT_WINDOW_DAYS = 14
const SECONDS_PER_DAY = 86_400

/**
 * 上横幅的分类：支线故事、复刻活动、联动活动。
 * PRTS 的分类会叠着写（如「支线故事复刻活动」），所以按包含判断
 */
const BANNER_KINDS = ['支线故事', '复刻活动', '联动活动']

/** 快照里存整份 overview，恢复时重置 Stale / Message 这两个运行时元数据 */
const SNAPSHOT_KEY = 'auto-mas.home.arknights-snapshot'

/** 后端解析出来的条目 */
interface PrtsActivity {
  name?: string
  kind?: string
  startTime?: string
  endTime?: string
  cover?: string
}

interface PrtsActivityResponse {
  activities?: PrtsActivity[]
}

const toTimestamp = (value: string) => {
  const timestamp = new Date(value).getTime()
  return Number.isNaN(timestamp) ? 0 : timestamp
}

const isBannerActivity = (item: SraActivityItem) =>
  BANNER_KINDS.some(kind => (item.kind ?? '').includes(kind))

/** 原始条目 → 卡片形状：没有名字或时间不全的、已经结束太久的都丢掉 */
const buildActivities = (items: PrtsActivity[], nowSeconds: number): SraActivityItem[] => {
  const horizon = nowSeconds - RECENT_WINDOW_DAYS * SECONDS_PER_DAY
  const picked = new Map<string, SraActivityItem>()

  for (const item of items) {
    const name = (item.name ?? '').trim()
    const startTime = item.startTime ?? ''
    const endTime = item.endTime ?? ''
    if (!name || !startTime || !endTime) continue
    if (toTimestamp(endTime) / 1000 < horizon) continue
    if (toTimestamp(endTime) <= toTimestamp(startTime)) continue
    if (picked.has(name)) continue

    picked.set(name, {
      name,
      description: '',
      startTime,
      endTime,
      cover: item.cover || '',
      kind: item.kind ?? '',
    })
  }

  return [...picked.values()].sort(
    (left, right) => toTimestamp(left.startTime) - toTimestamp(right.startTime)
  )
}

/**
 * 横幅优先报「支线故事 / 复刻活动 / 联动活动」；这三类都断档时退回「其他活动」，
 * 免得横幅一直空着。每类里优先进行中的那一场，其次还没开始的那一场。
 */
const buildOverview = (items: PrtsActivity[]): SraActivityOverview => {
  const now = Date.now()
  const activities = buildActivities(items, now / 1000)

  const pickCurrent = (pool: SraActivityItem[]) => {
    const running = pool.filter(
      item => toTimestamp(item.startTime) <= now && toTimestamp(item.endTime) > now
    )
    const upcoming = pool.filter(item => toTimestamp(item.startTime) > now)
    return running[0] ?? upcoming[0]
  }

  const mainActivities = activities.filter(isBannerActivity)
  const otherActivities = activities.filter(item => (item.kind ?? '').includes('其他活动'))
  const current = pickCurrent(mainActivities) ?? pickCurrent(otherActivities)

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

const readSnapshot = (): SraActivityOverview | null => {
  try {
    const raw = localStorage.getItem(SNAPSHOT_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as SraActivityOverview
    if (!Array.isArray(parsed?.activities)) return null
    return { ...parsed, Stale: true, Message: '' }
  } catch {
    return null
  }
}

const writeSnapshot = (overview: SraActivityOverview) => {
  try {
    localStorage.setItem(SNAPSHOT_KEY, JSON.stringify({ ...overview, Stale: false, Message: '' }))
  } catch {
    // 存储写不进去就算了，下次照常从网络取
  }
}

/**
 * 明日方舟活动数据的数据源（PRTS 活动一览）。
 *
 * 取数带超时、失败退避重试、本地快照与独立失败态，这些节奏交给公共骨架；
 * 这里只负责取数与收口。区别只在数据本身：多了一个 kind（PRTS 的分类），
 * 卡片按它打标签，横幅按它挑活动。
 */
export const useArknightsActivitySource = () => {
  const { t } = useI18n()

  const overview = ref<SraActivityOverview>(createEmptySraActivityOverview())

  const source = useHomeActivitySource<SraActivityOverview>({
    label: () => '明日方舟',
    timeoutMs: FETCH_TIMEOUT_MS,
    loadingOnStart: true,
    restoreSnapshot: () => {
      const snapshot = readSnapshot()
      if (!snapshot || snapshot.activities.length === 0) return false
      // 先用上一次的成功结果顶上，网络回来再覆盖
      overview.value = snapshot
      return true
    },
    saveSnapshot: next => {
      writeSnapshot(next)
    },
    fetchData: async signal => {
      const request = GetService.getArknightsActivityApiInfoArknightsActivityGet()
      const cancelOnAbort = () => request.cancel()
      signal.addEventListener('abort', cancelOnAbort, { once: true })
      let payload: PrtsActivityResponse
      try {
        const result = await request
        if (result.code !== 200) {
          throw new Error(result.message || 'HTTP ' + result.code)
        }
        payload = result.data as unknown as PrtsActivityResponse
      } finally {
        signal.removeEventListener('abort', cancelOnAbort)
      }
      return buildOverview(payload.activities ?? [])
    },
    applyData: next => {
      overview.value = next
    },
    markStale: () => {
      // 已经有内容时不要把卡片打回失败态，保留上一份数据并提示
      overview.value = { ...overview.value, Stale: true, Message: '' }
    },
    markUnavailable: () => {
      overview.value = {
        ...createEmptySraActivityOverview(),
        Available: false,
        Message: t('home.arknights.unavailable'),
      }
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
