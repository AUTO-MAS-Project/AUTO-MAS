import { useSraActivitySource } from '../useSraActivitySource'
import { sraActivityBanner } from '../activityBanner'
import { runningActivities, sraActivityEntry, sraActivitySections } from '../activitySections'
import type {
  ActivityModuleContext,
  ActivityModuleBuilder,
  ActivityPresentation,
  HomeActivityModule,
  SraActivitySource,
  SraPresentationContext,
} from './types'

export const buildSraActivityPresentation = (
  context: SraPresentationContext
): ActivityPresentation => {
  const { game, overview, loading, now, t } = context
  return {
    ...sraActivityBanner(overview),
    loading,
    ...sraActivitySections({
      overview,
      loading,
      t,
      emptyText: t(`core.home.empty.${game}`),
      items: runningActivities(overview.activities, now).map(item =>
        sraActivityEntry(item, overview)
      ),
    }),
  }
}

export const createSraActivityModule = (
  {
    game,
    accent,
    source,
    buildPresentation = buildSraActivityPresentation,
  }: {
    game: HomeActivityModule['game']
    accent: string
    source: SraActivitySource
    buildPresentation?: (context: SraPresentationContext) => ActivityPresentation
  },
  { t }: ActivityModuleContext
): HomeActivityModule => ({
  game,
  source,
  buildPanel: now => ({
    key: game,
    title: t(`core.home.game.${game}`),
    accent,
    ...buildPresentation({
      game,
      overview: source.overview.value,
      loading: source.loading.value,
      now,
      t,
    }),
  }),
})

/** 同一来源且没有专属规则的游戏只需登记来源标识和主题色。 */
export const sraActivityModuleBuilder =
  ({
    game,
    sourceGame,
    accent,
  }: {
    game: HomeActivityModule['game']
    sourceGame: string
    accent: string
  }): ActivityModuleBuilder =>
  context =>
    createSraActivityModule(
      { game, accent, source: useSraActivitySource(sourceGame, `core.home.game.${game}`) },
      context
    )
