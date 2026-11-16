import { GameCalendarActivityCompletionIn } from '@/api'
import type { SraActivityItem } from '@/types/home'
import { useSraActivitySource } from '../useSraActivitySource'
import { runningActivities, sraActivityEntry } from '../activitySections'
import { buildSraActivityPresentation, createSraActivityModule } from './sra'
import type { ActivityModuleBuilder, ActivityPresentation, SraPresentationContext } from './types'

// SRA 没有独立玩法字段；中英文档均以玩法名称开头，后接当期副标题。
const PERMANENT_PREFIXES = [
  '虚构叙事',
  '混沌回忆',
  '末日幻影',
  'pure fiction',
  'memory of chaos',
  'apocalyptic shadow',
]
export const isStarRailPermanentActivity = (item: SraActivityItem) =>
  PERMANENT_PREFIXES.some(prefix => item.name.trim().toLowerCase().startsWith(prefix))

export const buildStarRailActivityPresentation = (
  context: SraPresentationContext
): ActivityPresentation => {
  const { overview, now, t } = context
  const presentation = buildSraActivityPresentation({
    ...context,
    overview: {
      ...overview,
      activities: overview.activities.filter(item => !isStarRailPermanentActivity(item)),
    },
  })
  // 活动卡片仍以原始版本封面兜底，主视觉兜底则不取常驻玩法。
  presentation.activities.items = runningActivities(overview.activities, now)
    .filter(item => !isStarRailPermanentActivity(item))
    .map(item => sraActivityEntry(item, overview))
  const gameplay = runningActivities(overview.activities, now).filter(isStarRailPermanentActivity)
  presentation.extraSections = gameplay.length
    ? [
        {
          id: 'permanent-gameplay',
          title: t('core.home.activity.permanentGameplay'),
          layout: 'activity',
          completable: true,
          loading: false,
          available: true,
          emptyText: '',
          items: gameplay.map(item => sraActivityEntry(item, overview)),
        },
      ]
    : []
  return presentation
}

export const createStarRailActivityModule: ActivityModuleBuilder = context =>
  createSraActivityModule(
    {
      game: GameCalendarActivityCompletionIn.game.STARRAIL,
      accent: '#62c4e7',
      source: useSraActivitySource('sr', 'core.home.game.starrail'),
      buildPresentation: buildStarRailActivityPresentation,
    },
    context
  )
