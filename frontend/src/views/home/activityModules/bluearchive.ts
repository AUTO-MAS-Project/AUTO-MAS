import { GameCalendarActivityCompletionIn } from '@/api'
import { createEmptySraActivityOverview } from '@/types/home'
import { useBlueArchiveActivitySource } from '../useBlueArchiveActivitySource'
import { blueArchivePresentation } from '../blueArchivePresentation'
import {
  activityTags,
  activityTimestamp,
  runningActivities,
  sraActivityEntry,
} from '../activitySections'
import { buildSraActivityPresentation } from './sra'
import type { ActivityModuleBuilder, ActivityPresentation, SraPresentationContext } from './types'

export const buildBlueArchiveActivityPresentation = (
  context: SraPresentationContext
): ActivityPresentation => {
  const { overview, now, t } = context
  const presentation = buildSraActivityPresentation(context)
  presentation.activities.source = {
    label: t('home.bluearchive.source'),
    url: 'https://www.gamekee.com/ba/huodong/16',
  }
  presentation.activities.emptyText = t('home.bluearchive.noActivity')
  const upcoming = overview.activities
    .filter(item => activityTimestamp(item.startTime) > now)
    .sort((a, b) => activityTimestamp(a.startTime) - activityTimestamp(b.startTime))
  presentation.activities.items = [...runningActivities(overview.activities, now), ...upcoming]
    .slice(0, 6)
    .map(item => ({
      ...sraActivityEntry(item, overview),
      fallbackImage: '',
      tags: activityTags(item.kind),
    }))
  return presentation
}

export const createBlueArchiveActivityModule: ActivityModuleBuilder = ({ t }) => {
  const source = useBlueArchiveActivitySource()
  const servers = Object.values(GameCalendarActivityCompletionIn.server)
  const selectedServer = () => servers.find(server => server === source.selectedServer.value)!
  return {
    game: GameCalendarActivityCompletionIn.game.BLUEARCHIVE,
    source,
    completionServers: servers,
    selectedServer,
    select: value => {
      const server = source.servers.value.find(item => item.key === value)
      if (server) source.selectServer(server.key)
    },
    buildPanel: now => {
      const selected = source.selectedServer.value
      const server = source.servers.value.find(item => item.key === selected)
      const overview = blueArchivePresentation(server?.overview ?? createEmptySraActivityOverview())
      const presentation = buildBlueArchiveActivityPresentation({
        game: GameCalendarActivityCompletionIn.game.BLUEARCHIVE,
        overview,
        loading: source.loadingByServer[selected],
        now,
        t,
      })
      presentation.activities.choices = {
        label: t('home.bluearchive.serverLabel'),
        selected,
        options: source.servers.value.map(item => ({ value: item.key, label: item.label })),
      }
      // 横幅只报限时活动，缺活动时不拿战斗玩法填充版本。
      return {
        key: 'bluearchive',
        title: t('home.game.bluearchive'),
        accent: '#3ba9ee',
        ...presentation,
        ...(!overview.versionName ? { subtitle: '', startTime: '', endTime: '' } : {}),
        cover: overview.cover || '',
      }
    },
  }
}
