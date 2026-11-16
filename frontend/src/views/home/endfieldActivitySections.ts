import type { Composer } from 'vue-i18n'
import type { EndfieldActivityOverview, HomeActivityEntry, HomeActivitySection } from '@/types/home'
import { activityTags } from './activitySections'

/** 终末地的来源差异在此转换，展示组件仅消费统一条目。 */
export const endfieldActivitySections = ({
  overview,
  loading,
  now,
  t,
}: {
  overview: EndfieldActivityOverview
  loading: boolean
  now: number
  t: Composer['t']
}): { activities: HomeActivitySection; extraSections: HomeActivitySection[] } => {
  const timestamp = (value: string) => new Date(value).getTime()
  const versionValid =
    timestamp(overview.VersionStartTime ?? '') <= now &&
    timestamp(overview.VersionEndTime ?? '') > now
  const items = overview.Activities.filter(item => timestamp(item.EndTime) > now)
    .sort((a, b) => timestamp(a.EndTime) - timestamp(b.EndTime))
    .map((item): HomeActivityEntry => {
      const activity = { name: item.Name, startTime: item.StartTime, endTime: item.EndTime }
      const upcoming = timestamp(item.StartTime) > now
      return {
        id: `activity-${item.Id}`,
        ...activity,
        image: item.ImageUrl,
        fallbackImage: versionValid ? overview.VersionCover : '',
        tags: activityTags(...item.Tags),
        progress: upcoming
          ? undefined
          : Math.min(
              100,
              Math.max(
                0,
                ((now - timestamp(item.StartTime)) /
                  (timestamp(item.EndTime) - timestamp(item.StartTime))) *
                  100
              )
            ),
      }
    })
    .sort(
      (a, b) =>
        Number(timestamp(a.startTime ?? '') > now) - Number(timestamp(b.startTime ?? '') > now)
    )
  const activities: HomeActivitySection = {
    id: 'activities',
    title: t('core.home.activity.schedule'),
    completable: true,
    source: {
      label: t('core.home.sra.poweredBy', { name: 'SRA&AKEData' }),
      url: overview.SourceUrl,
    },
    loading,
    available: overview.Available,
    stale: overview.Stale,
    timeZone: 'Asia/Shanghai',
    timeZoneLabel: 'UTC+8',
    emptyText: t('core.home.endfield.noActivity'),
    items,
    alerts: [],
  }
  if (overview.Message) {
    activities.alerts!.push({
      id: 'source',
      message: overview.Message,
      type: overview.Available ? 'warning' : 'error',
    })
  }
  const pools: HomeActivitySection = {
    id: 'pools',
    title: t('core.home.endfield.pools'),
    layout: 'horizontal',
    loading: Boolean(overview.PoolLoading && !overview.Pools.length),
    available: !overview.PoolMessage,
    stale: overview.PoolStale,
    timeZone: 'Asia/Shanghai',
    timeZoneLabel: 'UTC+8',
    emptyText: t('core.home.endfield.noPools'),
    alerts: overview.PoolMessage
      ? [{ id: 'source', message: overview.PoolMessage, type: 'warning' }]
      : [],
    items: overview.Pools.filter(item => timestamp(item.EndTime) > now)
      .sort((a, b) => timestamp(a.EndTime) - timestamp(b.EndTime))
      .map(item => ({
        id: `pool-${item.Id}`,
        name: item.Name,
        tags: activityTags(item.Type),
        image: item.ImageUrl,
        imageFit: 'contain',
        description: item.UpCharacters.length
          ? t('core.home.endfield.upCharacters', { names: item.UpCharacters.join('、') })
          : '',
        startTime: item.StartTime,
        endTime: item.EndTime,
        countdownLabel: true,
      })),
  }
  return { activities, extraSections: [pools] }
}
