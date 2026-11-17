import type { RouteLocationNormalizedLoaded, Router } from 'vue-router'
import type { AnalyticsContext, AnalyticsScreen } from '@/types/analytics'
import {
  analyticsScriptType,
  captureAnalyticsContext,
  recordAnalyticsEvent,
} from '@/utils/analytics'

const screens: Record<string, AnalyticsScreen> = {
  Plugins: 'plugins',
  PluginMarket: 'plugin_market',
  PluginSettings: 'plugin_settings',
  PluginPage: 'plugin_settings',
  Tools: 'tools',
  Initialization: 'initialization',
  Home: 'home',
  Scripts: 'scripts',
  Plans: 'plans',
  OkNtePlanDetail: 'plans',
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
  script: 'script_edit',
  setup: 'script_setup',
  userAdd: 'user_add',
  userEdit: 'user_edit',
}

/** 页面分类来自真实路由登记，新增专项无需再同步类型正则。 */
function routeScreen(route: Pick<RouteLocationNormalizedLoaded, 'name' | 'meta'>) {
  const name = route.name
  if (typeof name !== 'string') return null
  if (screens[name]) return { screen: screens[name], script_type: 'none' as const }
  const kind = route.meta.scriptPage ?? route.meta.maafwPage
  return kind && route.meta.scriptType
    ? { screen: scriptScreens[kind], script_type: analyticsScriptType(route.meta.scriptType) }
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
    const target = routeScreen(to)
    if (!target) return
    const entry_source = !from.name ? 'initial' : (routeScreen(from)?.screen ?? 'other')
    recordAnalyticsEvent(context, { name: 'screen_view', props: { ...target, entry_source } })
  })
}
