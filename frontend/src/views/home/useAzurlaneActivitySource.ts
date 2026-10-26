import { ref } from 'vue'
import type { Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { GetService } from '@/api'
import { createEmptySraActivityOverview } from '@/types/home'
import type { SraActivityItem, SraActivityOverview } from '@/types/home'
import { useHomeActivitySource } from './useHomeActivitySource'

/** 后端从碧蓝海事局 WIKI 的活动日历里解析出来的条目 */
interface AzurlaneActivity {
  name?: string
  description?: string
  startTime?: string
  endTime?: string
  cover?: string
  kind?: string
}

/** 后端回包：`stale` 为真表示这是取数失败后退回的上一次缓存 */
interface AzurlanePayload {
  activities?: AzurlaneActivity[]
  stale?: boolean
}

const toTimestamp = (value: string) => {
  const timestamp = new Date(value).getTime()
  return Number.isNaN(timestamp) ? 0 : timestamp
}

/** 日历条目 → 卡片形状；缺名字或时间的条目界面没法展示，按不存在处理 */
const buildActivities = (raw: AzurlaneActivity[]): SraActivityItem[] =>
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
 * 横幅报当前那一期。
 *
 * 碧蓝航线会同时开着好几期：世界巡游、信标这类是长期玩法，当期海域活动才是主线，
 * 所以取「最新开的那一场」而不是最早开的那一场。同一时刻开的（如海域活动与它的
 * 故事集）保持日历里的先后，取先出现的那个。
 *
 * `stale` 是后端回退旧缓存时给的标记，透出到概览上让卡片提示「可能已过期」。
 */
const buildOverview = (payload: AzurlanePayload, staleMessage: string): SraActivityOverview => {
  const activities = buildActivities(payload.activities ?? [])
  const now = Date.now()

  const running = activities.filter(
    activity => toTimestamp(activity.startTime) <= now && toTimestamp(activity.endTime) > now
  )
  const upcoming = activities.filter(activity => toTimestamp(activity.startTime) > now)
  const ended = activities.filter(activity => toTimestamp(activity.endTime) <= now)
  const current = running.length
    ? running.reduce((best, item) =>
        toTimestamp(item.startTime) > toTimestamp(best.startTime) ? item : best
      )
    : (upcoming[0] ?? ended[ended.length - 1])
  const stale = payload.stale === true

  return {
    Available: true,
    Stale: stale,
    Message: stale ? staleMessage : '',
    version: '',
    versionName: current?.name ?? '',
    cover: current?.cover ?? '',
    startTime: current?.startTime ?? '',
    endTime: current?.endTime ?? '',
    activities,
  }
}

/**
 * 碧蓝航线活动数据的后端中转数据源。
 *
 * 数据取自碧蓝海事局 WIKI 的活动日历：官方站与日服站都是纯前端渲染、GameKee 也没
 * 开放这条线，能稳定拿到的只有那份维基文本；日历只写月日，年份与时刻由后端补齐。
 * 取数走后端 `POST /api/info/azurlane/activity`，这里只做收口与失败降级——与星塔旅人、
 * 碧蓝档案那两条链路同一形状。重试节奏与可见性挂起交给公共骨架。
 */
export const useAzurlaneActivitySource = () => {
  const { t } = useI18n()
  const overview = ref<SraActivityOverview>(createEmptySraActivityOverview())
  /** 后端回了旧缓存时先存在这里：数据要显示，但这次取数不算成功，见 fetchData */
  let stalePayload: AzurlanePayload | null = null
  /**
   * 骨架的 hasData。拿到 stale 回包时得先把它置真，否则骨架会走「还没有数据」的
   * 不可用分支把卡片清空，后端刚给的那份缓存就白给了（首次进首页就是这种情形）。
   */
  let hasData: Ref<boolean> | null = null
  const staleMessage = () => t('home.sra.staleMessage')

  const source = useHomeActivitySource<AzurlanePayload>({
    // 日志里沿用原本的中文名字，不随界面语言变
    label: () => '碧蓝航线',
    // 后端要现去 WIKI 取数，慢起来比其它源久，但也不能让卡片一直转
    timeoutMs: 20_000,
    loadingOnInit: false,
    loadingOnStart: true,
    fetchData: async signal => {
      const request = GetService.getAzurlaneActivityApiInfoAzurlaneActivityPost()
      // 生成的客户端只认自己的 cancel，得把骨架的 signal 接上去，
      // 否则超时后 abort 结束不了这个 Promise，卡片会一直转
      const cancelOnAbort = () => request.cancel()
      signal.addEventListener('abort', cancelOnAbort, { once: true })
      try {
        const response = await request
        // 生成的客户端对 200 响应一律 resolve，后端用 code=500 表达取数失败，
        // 不查这一层就会把失败当成「拿到了空排期」，卡片显示「暂无进行中的活动」
        if (response.code !== 200) {
          throw new Error(response.message || 'HTTP ' + response.code)
        }
        const payload = (response.data ?? {}) as AzurlanePayload
        if (payload.stale === true) {
          // 后端取数失败、退回了上次缓存：数据要显示，但这次没取成功。
          // 先认下「有数据」，骨架才会走 markStale 保留内容而不是 markUnavailable 清空；
          // 再抛出走骨架的失败分支，让它释放加载态并安排退避重试——否则 WIKI 恢复后
          // 这一轮不会自动重拉。数据在 markStale 里消费
          stalePayload = payload
          if (hasData) hasData.value = true
          throw new Error('活动数据取数失败，已回退上次结果')
        }
        return payload
      } finally {
        signal.removeEventListener('abort', cancelOnAbort)
      }
    },
    applyData: payload => {
      // 新数据到手就把暂存清掉，免得之后一次普通失败又把更旧的缓存翻出来
      stalePayload = null
      overview.value = buildOverview(payload, staleMessage())
    },
    markStale: () => {
      const fallback = stalePayload
      stalePayload = null
      // 有回退数据就照常展示并挂上「可能已过期」，没有就保留上一份内容
      overview.value = fallback
        ? buildOverview(fallback, staleMessage())
        : { ...overview.value, Stale: true, Message: staleMessage() }
    },
    markUnavailable: () => {
      // 走不到这里也清一下，避免暂存值跨轮残留
      stalePayload = null
      // 不能只清空：展示器只看 Message 决定要不要出错误提示，空着一句话都不给
      overview.value = createEmptySraActivityOverview(
        t('home.sra.unavailable', { name: '碧蓝航线' })
      )
    },
  })
  hasData = source.hasData

  return {
    overview,
    loading: source.loading,
    whenLoaded: source.whenLoaded,
    start: source.start,
    stop: source.stop,
    refresh: source.refresh,
  }
}
