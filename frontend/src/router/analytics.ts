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
  Taskboard: 'taskboard',
}
const scriptScreens: Record<string, AnalyticsScreen> = {
  ScriptEdit: 'script_edit',
  SetupWizard: 'script_setup',
  UserAdd: 'user_add',
  UserEdit: 'user_edit',
}

/** 目标页与来源页复用四种专项后缀，避免引导或新增用户流量落入 other。 */
function routeScreen(name: unknown) {
  if (typeof name !== 'string') return null
  if (screens[name]) return { screen: screens[name], script_type: 'none' as const }
  const match =
    /^(MAA|SRC|MaaEnd|HSR|General|BAAH|MaaFW|M9A|MSS|BetterGI|Okww|OkNte|ZzzOd|Whimbox)(ScriptEdit|SetupWizard|UserAdd|UserEdit)$/.exec(
      name
    )
  return match
    ? { screen: scriptScreens[match[2]], script_type: analyticsScriptType(match[1]) }
    : null
}

export function registerRouterAnalytics(router: Router): void {
  const contexts = new WeakMap<object, Promise<AnalyticsContext>>()
  router.beforeResolve(to => {
    contexts.set(to, captureAnalyticsContext())
  })
  router.afterEach((to, from, failure) => {
    const context = contexts.get(to)
    contexts.delete(to)
    if (failure || !context) return
    const target = routeScreen(to.name)
    if (!target) return
    const entry_source = !from.name ? 'initial' : (routeScreen(from.name)?.screen ?? 'other')
    recordAnalyticsEvent(context, { name: 'screen_view', props: { ...target, entry_source } })
  })
}
