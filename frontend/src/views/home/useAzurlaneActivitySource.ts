import { ref } from 'vue'
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

/** 横幅报当前那一期，口径与其它活动源一致：进行中的优先，其次未开始，最后退到刚结束的 */
const buildOverview = (raw: AzurlaneActivity[]): SraActivityOverview => {
  const activities = buildActivities(raw)
  const now = Date.now()

  const running = activities.filter(
    activity => toTimestamp(activity.startTime) <= now && toTimestamp(activity.endTime) > now
  )
  const upcoming = activities.filter(activity => toTimestamp(activity.startTime) > now)
  const ended = activities.filter(activity => toTimestamp(activity.endTime) <= now)
  // 碧蓝航线会同时开着好几期：世界巡游、信标这类是长期玩法，当期海域活动才是主线，
  // 所以横幅报「最新开的那一场」而不是最早开的那一场。同一时刻开的（如海域活动与
  // 它的故事集）保持日历里的先后，取先出现的那个
  const current = running.length
    ? running.reduce((best, item) =>
        toTimestamp(item.startTime) > toTimestamp(best.startTime) ? item : best
      )
    : (upcoming[0] ?? ended[ended.length - 1])

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
 * 碧蓝航线活动数据的后端中转数据源。
 *
 * 数据取自碧蓝海事局 WIKI 的活动日历：官方站与日服站都是纯前端渲染、GameKee 也没
 * 开放这条线，能稳定拿到的只有那份维基文本；日历只写月日，时刻由后端补齐。
 * 取数走后端 `POST /api/info/azurlane/activity`，这里只做收口与失败降级——与星塔旅人、
 * 碧蓝档案那两条链路同一形状。重试节奏与可见性挂起交给公共骨架。
 */
export const useAzurlaneActivitySource = () => {
  const overview = ref<SraActivityOverview>(createEmptySraActivityOverview())

  const source = useHomeActivitySource<AzurlaneActivity[]>({
    // 日志里沿用原本的中文名字，不随界面语言变
    label: () => '碧蓝航线',
    loadingOnInit: false,
    loadingOnStart: true,
    fetchData: async () => {
      const response = await GetService.getAzurlaneActivityApiInfoAzurlaneActivityPost()
      // 生成的客户端对 200 响应一律 resolve，后端用 code=500 表达取数失败，
      // 不查这一层就会把失败当成「拿到了空排期」，卡片显示「暂无进行中的活动」
      if (response.code !== 200) {
        throw new Error(response.message || 'HTTP ' + response.code)
      }
      const payload = (response.data ?? {}) as { activities?: AzurlaneActivity[] }
      return payload.activities ?? []
    },
    applyData: activities => {
      overview.value = buildOverview(activities)
    },
    markStale: () => {
      // 保留上一次的内容并挂上 stale 标记，卡片据此提示数据可能已过期
      overview.value = { ...overview.value, Stale: true }
    },
    markUnavailable: () => {
      overview.value = createEmptySraActivityOverview()
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
