import { GameCalendarActivityCompletionIn } from '@/api'
import { useStellaActivitySource } from '../useStellaActivitySource'
import type { ActivityBannerSource } from '../activityBanner'
import type { SraActivityOverview } from '@/types/home'
import {
  activityTimestamp,
  byActivityEnd,
  runningActivities,
  sraActivityEntry,
} from '../activitySections'
import { buildSraActivityPresentation, createSraActivityModule } from './sra'
import type { ActivityModuleBuilder, ActivityPresentation, SraPresentationContext } from './types'

// 来源分类原值不随界面语言改变。
const PERMANENT_KIND = '常驻活动'
export const buildStellaActivityPresentation = (
  context: SraPresentationContext
): ActivityPresentation => {
  const { overview, now, t } = context
  const presentation = {
    ...buildSraActivityPresentation(context),
    version: undefined,
    ...stellaActivityBanner(overview),
  }
  presentation.activities.source = {
    label: t('core.home.sra.poweredBy', { name: t('core.home.stella.sourceName') }),
    url: 'https://stellasora.yostar.cn/news',
  }
  presentation.activities.items = runningActivities(overview.activities, now)
    .filter(item => item.kind !== PERMANENT_KIND)
    .map(item => sraActivityEntry(item, overview))
  const permanent = overview.activities
    .filter(item => item.kind === PERMANENT_KIND && activityTimestamp(item.endTime) > now)
    .sort(byActivityEnd)
  presentation.extraSections = permanent.length
    ? [
        {
          id: 'permanent',
          title: t('core.home.stella.permanent'),
          layout: 'activity',
          completable: true,
          loading: false,
          available: true,
          emptyText: '',
          items: permanent.map(item => sraActivityEntry(item, overview)),
        },
      ]
    : []
  return presentation
}

export const createStellaActivityModule: ActivityModuleBuilder = context =>
  createSraActivityModule(
    {
      game: GameCalendarActivityCompletionIn.game.STELLASORA,
      accent: '#2b9fff',
      source: useStellaActivitySource(),
      buildPresentation: buildStellaActivityPresentation,
    },
    context
  )

/**
 * 星塔旅人的横幅只报「版本活动」。
 *
 * 那是会开限时活动关的版本大活动（「遥远的塔」这种），招募与拼图、经营之类的小玩法
 * 只留在下面的活动卡里；一期版本活动都没有时横幅空着，由轮播显示「暂无进行中的活动」。
 */
const STELLA_BANNER_KIND = '版本活动'

export const stellaActivityBanner = (overview: SraActivityOverview): ActivityBannerSource => {
  const now = Date.now()
  const versions = overview.activities.filter(item =>
    (item.kind ?? '').includes(STELLA_BANNER_KIND)
  )
  const activity =
    versions.find(
      item => activityTimestamp(item.startTime) <= now && activityTimestamp(item.endTime) > now
    ) ?? versions.find(item => activityTimestamp(item.startTime) > now)

  return {
    cover: activity?.cover ?? '',
    subtitle: activity?.name ?? '',
    startTime: activity?.startTime ?? '',
    endTime: activity?.endTime ?? '',
    available: overview.Available,
    stale: overview.Stale,
  }
}
