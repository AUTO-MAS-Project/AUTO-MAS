import { GameCalendarActivityCompletionIn } from '@/api'
import { useEndfieldActivitySource } from '../useEndfieldActivitySource'
import type { ActivityBannerSource } from '../activityBanner'
import type { EndfieldActivityOverview } from '@/types/home'
import { activityTimestamp } from '../activitySections'
import { endfieldActivitySections } from '../endfieldActivitySections'
import type { ActivityModuleBuilder } from './types'

export const createEndfieldActivityModule: ActivityModuleBuilder = ({ t }) => {
  const source = useEndfieldActivitySource()
  return {
    game: GameCalendarActivityCompletionIn.game.ENDFIELD,
    source,
    buildPanel: now => ({
      key: 'endfield',
      title: t('home.game.endfield'),
      accent: '#ffb45a',
      ...endfieldActivityBanner(source.overview.value),
      loading: source.loading.value,
      ...endfieldActivitySections({
        overview: source.overview.value,
        loading: source.loading.value,
        now,
        t,
      }),
    }),
  }
}

export const endfieldActivityBanner = (
  overview: EndfieldActivityOverview
): ActivityBannerSource => {
  const now = Date.now()
  const versionValid = Boolean(
    overview.VersionName &&
    activityTimestamp(overview.VersionStartTime ?? '') > 0 &&
    activityTimestamp(overview.VersionEndTime ?? '') > now
  )
  // 无有效版本时仅使用同一活动的标题、封面和时间，不拿卡池伪造版本周期。
  const activities = [...overview.Activities]
    .filter(item => activityTimestamp(item.EndTime) > now)
    .sort((left, right) => activityTimestamp(left.StartTime) - activityTimestamp(right.StartTime))
  const activity =
    activities.find(item => activityTimestamp(item.StartTime) <= now) ?? activities[0]
  return {
    // AKE 原生活动图可能数十 MB；兜底只显示文字，不直接加载这些大图。
    cover: versionValid
      ? (overview.VersionCover ?? '')
      : overview.SourceName === 'SRA'
        ? (activity?.CoverUrl ?? '')
        : '',
    version: versionValid ? overview.Version : '',
    subtitle: versionValid ? (overview.VersionName ?? '') : (activity?.Name ?? ''),
    startTime: versionValid ? (overview.VersionStartTime ?? '') : (activity?.StartTime ?? ''),
    endTime: versionValid ? (overview.VersionEndTime ?? '') : (activity?.EndTime ?? ''),
    available: overview.Available,
    stale: versionValid ? (overview.VersionStale ?? overview.Stale) : overview.Stale,
  }
}
