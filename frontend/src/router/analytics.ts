import type { Router } from 'vue-router'
import type { AnalyticsContext, AnalyticsScreen } from '@/types/analytics'
import {
  analyticsScriptType,
  captureAnalyticsContext,
  recordAnalyticsEvent,
} from '@/utils/analytics'

const screens: Record<string, AnalyticsScreen> = {
  Initialization: 'initialization',
  Home: 'home',
  Scripts: 'scripts',
  Plans: 'plans',
  Emulators: 'emulators',
  Queue: 'queue',
  Scheduler: 'scheduler',
  History: 'history',
  GameSign: 'gamesign',
  CommunityToolSign: 'community_sign',
  CommunityToolActivity: 'community_activity',
  ThemeStore: 'theme_store',
  Settings: 'settings',
}
const scriptScreens: Record<string, AnalyticsScreen> = {
  ScriptEdit: 'script_edit',
  SetupWizard: 'script_setup',
  UserAdd: 'user_add',
  UserEdit: 'user_edit',
}

export function registerRouterAnalytics(router: Router): void {
  const contexts = new WeakMap<object, Promise<AnalyticsContext>>()
  router.beforeResolve(to => {
    contexts.set(to, captureAnalyticsContext())
  })
  router.afterEach((to, _from, failure) => {
    const context = contexts.get(to)
    contexts.delete(to)
    if (failure || !context || typeof to.name !== 'string') return
    const screen = screens[to.name]
    if (screen) {
      recordAnalyticsEvent(context, { name: 'screen_view', props: { screen, script_type: 'none' } })
      return
    }
    const match =
      /^(MAA|SRC|MaaEnd|HSR|General|BAAH|MaaFW|M9A|MSS|BetterGI|Okww|OkNte|ZzzOd|Whimbox)(ScriptEdit|SetupWizard|UserAdd|UserEdit)$/.exec(
        to.name
      )
    if (!match) return
    recordAnalyticsEvent(context, {
      name: 'screen_view',
      props: { screen: scriptScreens[match[2]], script_type: analyticsScriptType(match[1]) },
    })
  })
}
