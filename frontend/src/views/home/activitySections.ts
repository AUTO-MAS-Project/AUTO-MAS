import type { Composer } from 'vue-i18n'
import { OpenAPI } from '@/api'
import type {
  HomeActivityEntry,
  HomeActivitySection,
  HomeModuleKey,
  ResourceItem,
  SraActivityItem,
  SraActivityOverview,
} from '@/types/home'

const MS_PER_DAY = 86_400_000
const LONG_RUNNING_DAYS = 60
// 活动源的分类原值不随界面语言改变。
const PERMANENT_KIND = '常驻活动'
// SRA 没有独立的玩法分类字段，中英文档都以玩法名称开头，后接当期副标题。
const STARRAIL_PERMANENT_PREFIXES = [
  '虚构叙事',
  '混沌回忆',
  '末日幻影',
  'pure fiction',
  'memory of chaos',
  'apocalyptic shadow',
]

/** 各来源的单标签或多标签统一成去空、去重的展示列表。 */
export const activityTags = (...values: (string | undefined)[]) => [
  ...new Set(values.map(value => value?.trim()).filter((value): value is string => Boolean(value))),
]

export const isStarRailPermanentActivity = (item: SraActivityItem) =>
  STARRAIL_PERMANENT_PREFIXES.some(prefix => item.name.trim().toLowerCase().startsWith(prefix))

const timestamp = (value: string) => new Date(value).getTime() || 0
const longRunning = (item: SraActivityItem) =>
  timestamp(item.endTime) - timestamp(item.startTime) > LONG_RUNNING_DAYS * MS_PER_DAY

/** 各源的筛选和展示口径集中在适配层，公共组件不认识游戏。 */
export const sraActivitySections = ({
  key,
  overview,
  loading,
  now,
  t,
}: {
  key: HomeModuleKey
  overview: SraActivityOverview
  loading: boolean
  now: number
  t: Composer['t']
}): { activities: HomeActivitySection; extraSections: HomeActivitySection[] } => {
  const running = (item: SraActivityItem) =>
    timestamp(item.startTime) <= now && timestamp(item.endTime) > now
  const byEnd = (a: SraActivityItem, b: SraActivityItem) =>
    timestamp(a.endTime) - timestamp(b.endTime)
  let displayed = overview.activities.filter(running).sort(byEnd)
  if (key === 'arknights') {
    // 生息演算、集成战略等长期玩法排到当期活动后面。
    displayed = overview.activities
      .filter(item => timestamp(item.endTime) > now)
      .sort(
        (a, b) =>
          Number(longRunning(a)) - Number(longRunning(b)) ||
          timestamp(a.startTime) - timestamp(b.startTime)
      )
      .slice(0, 8)
  } else if (key === 'bluearchive') {
    const upcoming = overview.activities
      .filter(item => timestamp(item.startTime) > now)
      .sort((a, b) => timestamp(a.startTime) - timestamp(b.startTime))
    displayed = [...displayed, ...upcoming].slice(0, 6)
  } else if (key === 'reverse1999') {
    displayed = displayed.slice(0, 4)
  } else if (key === 'stellasora') {
    displayed = displayed.filter(item => item.kind !== PERMANENT_KIND)
  } else if (key === 'starrail') {
    displayed = displayed.filter(item => !isStarRailPermanentActivity(item))
  }

  const versionCover = overview.cover || overview.activities.find(item => item.cover)?.cover || ''
  const toEntry = (item: SraActivityItem): HomeActivityEntry => ({
    id: JSON.stringify([item.name, item.startTime]),
    name: item.name,
    description: item.description,
    image: key === 'reverse1999' ? '' : item.cover,
    fallbackImage:
      key === 'arknights' || key === 'bluearchive' || key === 'reverse1999' ? '' : versionCover,
    tags: activityTags(key === 'arknights' || key === 'bluearchive' ? item.kind : undefined),
    startTime: item.startTime,
    endTime: item.endTime,
    countdownDaysOnly: key === 'arknights' && longRunning(item),
    countdownLabel: key === 'arknights',
  })
  const sources: Partial<Record<HomeModuleKey, { label: string; url: string }>> = {
    arknights: {
      label: t('home.arknights.source'),
      url: 'https://prts.wiki/w/%E6%B4%BB%E5%8A%A8%E4%B8%80%E8%A7%88',
    },
    bluearchive: {
      label: t('home.bluearchive.source'),
      url: 'https://www.gamekee.com/ba/huodong/16',
    },
    reverse1999: { label: t('home.sra.poweredByM9A'), url: 'https://api.1999.fan' },
    stellasora: {
      label: t('home.sra.poweredBy', { name: t('home.stella.sourceName') }),
      url: 'https://stellasora.yostar.cn/news',
    },
  }
  const activities: HomeActivitySection = {
    id: 'activities',
    title: t('home.activity.schedule'),
    completable: true,
    accent: key === 'reverse1999' ? '#e0484f' : undefined,
    source: sources[key] ?? {
      label: t('home.sra.poweredBy', { name: 'SRA' }),
      url: 'https://starrailassistant.top',
    },
    loading,
    available: overview.Available,
    stale: overview.Stale,
    emptyText:
      key === 'arknights' || key === 'bluearchive'
        ? t(`home.${key}.noActivity`)
        : t(`home.empty.${key}`),
    items: displayed.map(toEntry),
    alerts: overview.Message
      ? [
          {
            id: 'source',
            message: overview.Message,
            type: overview.Available ? 'warning' : 'error',
          },
        ]
      : [],
  }
  const permanent = overview.activities
    .filter(item => item.kind === PERMANENT_KIND && timestamp(item.endTime) > now)
    .sort(byEnd)
  const gameplay = overview.activities
    .filter(item => running(item) && isStarRailPermanentActivity(item))
    .sort(byEnd)
  return {
    activities,
    extraSections:
      key === 'stellasora' && permanent.length
        ? [
            {
              id: 'permanent',
              title: t('home.stella.permanent'),
              layout: 'activity',
              completable: true,
              loading: false,
              available: true,
              emptyText: '',
              items: permanent.map(toEntry),
            },
          ]
        : key === 'starrail' && gameplay.length
          ? [
              {
                id: 'permanent-gameplay',
                title: t('home.activity.permanentGameplay'),
                layout: 'activity',
                completable: true,
                loading: false,
                available: true,
                emptyText: '',
                items: gameplay.map(toEntry),
              },
            ]
          : [],
  }
}

export const resourceActivitySection = ({
  resources,
  error,
  t,
}: {
  resources: ResourceItem[]
  error: string
  t: Composer['t']
}): HomeActivitySection[] =>
  resources.length || error
    ? [
        {
          id: 'resources',
          title: t('home.arknights.resourceToday'),
          layout: 'resource',
          loading: false,
          available: true,
          emptyText: '',
          alerts: error
            ? [{ id: 'resource-error', message: error, type: 'error', closable: true }]
            : [],
          items: resources.map(item => ({
            id: item.Value,
            name: item.DropName,
            tags: activityTags(item.Display),
            description: item.Activity.Tip,
            image: item.Drop ? `${OpenAPI.BASE}/api/res/materials/${item.Drop}.png` : '',
            imageFit: 'contain',
          })),
        },
      ]
    : []
