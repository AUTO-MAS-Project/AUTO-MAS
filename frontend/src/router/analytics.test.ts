import { SCRIPT_PLUGIN_ROUTES } from '@/plugins/scriptAdapters'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { MAAFW_FLAVORS } from '@/composables/useMaaFWFlavor'
import { recordAnalyticsEvent } from '@/utils/analytics'
import { registerRouterAnalytics } from './analytics'
import { buildMaaFWRoutes } from './maafwFlavorRoutes'
import { buildScriptEditorRoutes } from './scriptEditorRoutes'

vi.mock('@/utils/analytics', async importOriginal => ({
  ...(await importOriginal<typeof import('@/utils/analytics')>()),
  captureAnalyticsContext: () => Promise.resolve(1),
  recordAnalyticsEvent: vi.fn(),
}))

afterEach(() => vi.clearAllMocks())

describe('registered editor screen analytics', () => {
  it('keeps ordinary and MFW screen categories and entry sources without identifiers', async () => {
    const routes = [
      ...buildScriptEditorRoutes(),
      ...SCRIPT_PLUGIN_ROUTES,
      ...Object.values(buildMaaFWRoutes(MAAFW_FLAVORS, {})).flat(),
    ].map(route => ({ path: route.path, name: route.name, meta: route.meta, component: {} }))
    const router = createRouter({ history: createMemoryHistory(), routes })
    registerRouterAnalytics(router)

    await router.push('/scripts/private-script/edit/general')
    await router.push('/scripts/private-script/users/add/zzzod')
    await router.push('/scripts/private-script/setup/m9a')
    await router.push('/scripts/private-script/users/private-user/edit/mss')
    await router.push('/scripts/private-script/users/private-user/cultivate/maa')

    expect(vi.mocked(recordAnalyticsEvent).mock.calls.map(([, event]) => event)).toEqual([
      {
        name: 'screen_view',
        props: { screen: 'script_edit', script_type: 'General', entry_source: 'initial' },
      },
      {
        name: 'screen_view',
        props: { screen: 'user_add', script_type: 'ZzzOd', entry_source: 'script_edit' },
      },
      {
        name: 'screen_view',
        props: { screen: 'script_setup', script_type: 'M9A', entry_source: 'user_add' },
      },
      {
        name: 'screen_view',
        props: { screen: 'user_edit', script_type: 'MSS', entry_source: 'script_setup' },
      },
    ])
  })
})
