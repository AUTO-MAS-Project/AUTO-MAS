import { GameCalendarActivityCompletionIn } from '@/api'
import { useReverse1999ActivitySource } from '../useReverse1999ActivitySource'
import { buildSraActivityPresentation, createSraActivityModule } from './sra'
import type { ActivityModuleBuilder, ActivityPresentation, SraPresentationContext } from './types'

export const buildReverse1999ActivityPresentation = (
  context: SraPresentationContext
): ActivityPresentation => {
  const presentation = buildSraActivityPresentation(context)
  presentation.activities.source = {
    label: context.t('home.sra.poweredByM9A'),
    url: 'https://api.1999.fan',
  }
  presentation.activities.accent = '#e0484f'
  presentation.activities.items = presentation.activities.items
    .slice(0, 4)
    .map(item => ({ ...item, image: '', fallbackImage: '' }))
  return presentation
}

export const createReverse1999ActivityModule: ActivityModuleBuilder = context =>
  createSraActivityModule(
    {
      game: GameCalendarActivityCompletionIn.game.REVERSE1999,
      accent: '#f2a0c0',
      source: useReverse1999ActivitySource(),
      buildPresentation: buildReverse1999ActivityPresentation,
    },
    context
  )
