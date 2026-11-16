import { OpenAPI, GameCalendarActivityCompletionIn } from '@/api'
import type { Composer } from 'vue-i18n'
import type { HomeActivitySection, ResourceItem, SraActivityItem } from '@/types/home'
import { useArknightsActivitySource } from '../useArknightsActivitySource'
import { activityTags, activityTimestamp, sraActivityEntry } from '../activitySections'
import { buildSraActivityPresentation, createSraActivityModule } from './sra'
import type { ActivityModuleBuilder, ActivityPresentation, SraPresentationContext } from './types'

const LONG_RUNNING_MS = 60 * 86_400_000
const longRunning = (item: SraActivityItem) =>
  activityTimestamp(item.endTime) - activityTimestamp(item.startTime) > LONG_RUNNING_MS

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
          title: t('core.home.arknights.resourceToday'),
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

export const buildArknightsActivityPresentation = (
  context: SraPresentationContext
): ActivityPresentation => {
  const { overview, now, t } = context
  const presentation = buildSraActivityPresentation(context)
  presentation.activities.source = {
    label: t('core.home.arknights.source'),
    url: 'https://prts.wiki/w/%E6%B4%BB%E5%8A%A8%E4%B8%80%E8%A7%88',
  }
  presentation.activities.emptyText = t('core.home.arknights.noActivity')
  // 生息演算、集成战略等长期玩法排在当期活动后，仍展示尚未开始的活动。
  presentation.activities.items = overview.activities
    .filter(item => activityTimestamp(item.endTime) > now)
    .sort(
      (a, b) =>
        Number(longRunning(a)) - Number(longRunning(b)) ||
        activityTimestamp(a.startTime) - activityTimestamp(b.startTime)
    )
    .slice(0, 8)
    .map(item => ({
      ...sraActivityEntry(item, overview),
      fallbackImage: '',
      tags: activityTags(item.kind),
      countdownDaysOnly: longRunning(item),
      countdownLabel: true,
    }))
  return presentation
}

export const createArknightsActivityModule: ActivityModuleBuilder = context =>
  createSraActivityModule(
    {
      game: GameCalendarActivityCompletionIn.game.ARKNIGHTS,
      accent: '#9fb4cc',
      source: useArknightsActivitySource(),
      buildPresentation: input => ({
        ...buildArknightsActivityPresentation(input),
        extraSections: resourceActivitySection({
          resources: context.resources.value,
          error: context.resourceError.value,
          t: context.t,
        }),
      }),
    },
    context
  )
