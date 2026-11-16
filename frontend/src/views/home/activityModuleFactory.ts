import { GameCalendarActivityCompletionIn } from '@/api'
import type { HomeModuleKey } from '@/types/home'
import { createEndfieldActivityModule } from './activityModules/endfield'
import { createStarRailActivityModule } from './activityModules/starrail'
import { createArknightsActivityModule } from './activityModules/arknights'
import { createBlueArchiveActivityModule } from './activityModules/bluearchive'
import { createReverse1999ActivityModule } from './activityModules/reverse1999'
import { createStellaActivityModule } from './activityModules/stellasora'
import { createAzurlaneActivityModule } from './activityModules/azurlane'
import { sraActivityModuleBuilder } from './activityModules/sra'
import type {
  ActivityModuleBuilder,
  ActivityModuleContext,
  HomeActivityModule,
} from './activityModules/types'

const Game = GameCalendarActivityCompletionIn.game
/** 新游戏只在此登记构建器；游戏规则由各模块持有。 */
export const HOME_ACTIVITY_MODULE_BUILDERS: Record<
  GameCalendarActivityCompletionIn.game,
  ActivityModuleBuilder
> = {
  endfield: createEndfieldActivityModule,
  starrail: createStarRailActivityModule,
  genshin: sraActivityModuleBuilder({ game: Game.GENSHIN, sourceGame: 'ys', accent: '#8fe3b0' }),
  zenless: sraActivityModuleBuilder({ game: Game.ZENLESS, sourceGame: 'zzz', accent: '#ffd24a' }),
  wutheringwaves: sraActivityModuleBuilder({
    game: Game.WUTHERINGWAVES,
    sourceGame: 'ww',
    accent: '#7aa2ff',
  }),
  nte: sraActivityModuleBuilder({ game: Game.NTE, sourceGame: 'nte', accent: '#c9a7ff' }),
  infinitynikki: sraActivityModuleBuilder({
    game: Game.INFINITYNIKKI,
    sourceGame: 'infinitynikki',
    accent: '#f2a0c0',
  }),
  arknights: createArknightsActivityModule,
  bluearchive: createBlueArchiveActivityModule,
  reverse1999: createReverse1999ActivityModule,
  stellasora: createStellaActivityModule,
  azurlane: createAzurlaneActivityModule,
}

export const createHomeActivityModules = (context: ActivityModuleContext) =>
  new Map<HomeModuleKey, HomeActivityModule>(
    Object.values(HOME_ACTIVITY_MODULE_BUILDERS).map(build => {
      const module = build(context)
      return [module.game, module]
    })
  )

export const createActivityPanel = ({
  modules,
  key,
  now,
}: {
  modules: ReadonlyMap<HomeModuleKey, HomeActivityModule>
  key: HomeModuleKey
  now: number
}) => modules.get(key)?.buildPanel(now)
