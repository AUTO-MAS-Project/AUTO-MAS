import { GameCalendarActivityCompletionIn } from '@/api'
import { useAzurlaneActivitySource } from '../useAzurlaneActivitySource'
import { buildSraActivityPresentation, createSraActivityModule } from './sra'
import type { ActivityModuleBuilder, ActivityPresentation, SraPresentationContext } from './types'

const Game = GameCalendarActivityCompletionIn.game

/** 活动日历页；点来源链接直接去这一页 */
const CALENDAR_URL = 'https://wiki.biligame.com/blhx/活动日历'

/**
 * 来源要写成 WIKI。
 *
 * 展示层默认标「由 SRA 强力支持」，但碧蓝航线的活动是碧蓝海事局 WIKI 的活动日历
 * 解析出来的，沿用那行文案会误导。
 */
export const buildAzurlaneActivityPresentation = (
  context: SraPresentationContext
): ActivityPresentation => {
  const presentation = buildSraActivityPresentation(context)
  presentation.activities.source = {
    label: context.t('core.home.sra.poweredBy', {
      name: context.t('core.home.azurlane.sourceName'),
    }),
    url: CALENDAR_URL,
  }
  return presentation
}

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
      buildPresentation: buildAzurlaneActivityPresentation,
    },
    context
  )
