import { GameCalendarActivityCompletionIn } from '@/api'
import { useAzurlaneActivitySource } from '../useAzurlaneActivitySource'
import { createSraActivityModule } from './sra'
import type { ActivityModuleBuilder } from './types'

const Game = GameCalendarActivityCompletionIn.game

/**
 * 碧蓝航线的活动卡。
 *
 * 数据来自 WIKI 的活动日历，形状与 SRA 那几家一致（活动名、起止、分类），
 * 所以展示直接复用同一套：横幅报当前那一期，下面的分栏按进行中的活动排。
 */
export const createAzurlaneActivityModule: ActivityModuleBuilder = context =>
  createSraActivityModule(
    {
      game: Game.AZURLANE,
      accent: '#4cc2ff',
      source: useAzurlaneActivitySource(),
    },
    context
  )
