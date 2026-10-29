import type { Ref } from 'vue'
import type { Composer } from 'vue-i18n'
import type { GameCalendarActivityCompletionIn } from '@/api'
import type { HomeActivityPanel, ResourceItem, SraActivityOverview } from '@/types/home'
import type { HomeActivitySource } from '../useHomeActivitySource'

export interface ActivityModuleContext {
  t: Composer['t']
  resources: Ref<ResourceItem[]>
  resourceError: Ref<string>
}

/** 游戏模块声明来源、展示构建和专属交互；公共完成状态由编排层管理。 */
export interface HomeActivityModule {
  game: GameCalendarActivityCompletionIn.game
  source: Pick<HomeActivitySource, 'start' | 'stop' | 'refresh' | 'whenLoaded'>
  buildPanel: (now: number) => HomeActivityPanel
  completionServers?: GameCalendarActivityCompletionIn.server[]
  selectedServer?: () => GameCalendarActivityCompletionIn.server
  select?: (value: string) => void
}

export type ActivityModuleBuilder = (context: ActivityModuleContext) => HomeActivityModule
export type ActivityPresentation = Omit<HomeActivityPanel, 'key' | 'title' | 'accent'>

export interface SraPresentationContext {
  game: GameCalendarActivityCompletionIn.game
  overview: SraActivityOverview
  loading: boolean
  now: number
  t: Composer['t']
}

export type SraActivitySource = HomeActivityModule['source'] & {
  overview: Ref<SraActivityOverview>
  loading: Ref<boolean>
}
