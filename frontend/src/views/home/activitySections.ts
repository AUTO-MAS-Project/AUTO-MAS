import type { Composer } from 'vue-i18n'
import type {
  HomeActivityEntry,
  HomeActivitySection,
  SraActivityItem,
  SraActivityOverview,
} from '@/types/home'

/** 各来源的单标签或多标签统一成去空、去重的展示列表。 */
export const activityTags = (...values: (string | undefined)[]) => [
  ...new Set(values.map(value => value?.trim()).filter((value): value is string => Boolean(value))),
]

export const activityTimestamp = (value: string) => new Date(value).getTime() || 0
export const byActivityEnd = (a: SraActivityItem, b: SraActivityItem) =>
  activityTimestamp(a.endTime) - activityTimestamp(b.endTime)
export const runningActivities = (items: SraActivityItem[], now: number) =>
  items
    .filter(
      item => activityTimestamp(item.startTime) <= now && activityTimestamp(item.endTime) > now
    )
    .sort(byActivityEnd)

export const sraActivityEntry = (
  item: SraActivityItem,
  overview: SraActivityOverview
): HomeActivityEntry => ({
  id: JSON.stringify([item.name, item.startTime]),
  name: item.name,
  description: item.description,
  image: item.cover,
  tags: [],
  fallbackImage: overview.cover || overview.activities.find(item => item.cover)?.cover || '',
  startTime: item.startTime,
  endTime: item.endTime,
  countdownDaysOnly: false,
  countdownLabel: false,
})

/** 公共适配只组装展示结构；筛选、分组和来源文案由游戏模块传入。 */
export const sraActivitySections = ({
  overview,
  loading,
  t,
  items,
  emptyText,
  source,
  accent,
}: {
  overview: SraActivityOverview
  loading: boolean
  t: Composer['t']
  items: HomeActivityEntry[]
  emptyText: string
  source?: HomeActivitySection['source']
  accent?: string
}): { activities: HomeActivitySection; extraSections: HomeActivitySection[] } => ({
  activities: {
    id: 'activities',
    title: t('home.activity.schedule'),
    completable: true,
    accent,
    source: source ?? {
      label: t('home.sra.poweredBy', { name: 'SRA' }),
      url: 'https://starrailassistant.top',
    },
    loading,
    available: overview.Available,
    stale: overview.Stale,
    emptyText,
    items,
    alerts: overview.Message
      ? [
          {
            id: 'source',
            message: overview.Message,
            type: overview.Available ? 'warning' : 'error',
          },
        ]
      : [],
  },
  extraSections: [],
})
