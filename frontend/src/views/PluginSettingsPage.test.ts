import { expect, it, vi } from 'vite-plus/test'
import { createSSRApp, h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import Antd, { message } from 'ant-design-vue'
import { BackgroundTaskState, Service } from '@/api'
import PluginSettingsPage from '@/views/PluginSettingsPage.vue'

vi.mock('@/views/plugins/usePluginCenterData', () => ({
  usePluginModelContext: () => ({ value: {} }),
}))
vi.mock('@/utils/analytics', () => ({ beginAnalyticsOperation: () => ({ finish: vi.fn() }) }))
vi.mock('@/i18n', () => ({
  translate: (key: string) => key,
  normalizeLocale: (language: string) => language,
  i18n: { global: { locale: { value: 'en-US' } } },
}))
vi.mock('@/composables/useAppLifecycle', () => ({
  beginIntentionalBackendRestart: vi.fn(),
  endIntentionalBackendRestart: vi.fn(),
}))
vi.mock('@/services/websocket/subscriptions', () => ({ subscribe: vi.fn(), unsubscribe: vi.fn() }))
vi.mock('@/services/websocket/connection', () => ({ reconnectNow: vi.fn() }))

it('插件设置页把所选动作交给后台执行，保留普通按钮的启动命令', async () => {
  const menu = {
    field: 'run',
    editable: true,
    component: 'dropdown-button',
    options: [{ value: 'refresh' }],
  }
  const button = { field: 'check', editable: true, component: 'button' }
  const config = {
    uid: 'config',
    advanced: { name: 'later-step-value' },
    ui: {
      hints: { actions: [menu, button], advanced: [{ field: 'name' }] },
      steps: [{ key: 'actions', title: 'Actions' }, { key: 'advanced' }],
      sections: { 'group:advanced': { step: 'advanced' } },
    },
  }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const locale = 'en-US'
  client.setQueryData(['plugins', 'settings', 'record', locale], {
    value: { requestedId: 'record', requestedLocale: locale, config, registry: {} },
  })
  vi.spyOn(Service, 'getPluginRegistryApiPluginRegistryGetPost').mockResolvedValue({ code: 200 })
  vi.spyOn(Service, 'getPluginConfigApiPluginConfigGetPost').mockResolvedValue({
    code: 200,
    data: config,
  })
  vi.spyOn(Service, 'getActiveConfigTriggersApiConfigTriggersActiveGet').mockResolvedValue({
    code: 200,
    data: [],
  })
  const start = vi
    .spyOn(Service, 'writeConfigTriggerApiConfigTriggersWritePost')
    .mockResolvedValue({ code: 200, data: 'task' })
  vi.spyOn(Service, 'getConfigTriggerResultApiConfigTriggersResultPost').mockResolvedValue({
    code: 200,
    data: { state: BackgroundTaskState.SUCCEEDED },
  })
  const success = vi.spyOn(message, 'success').mockImplementation(vi.fn())
  vi.spyOn(message, 'error').mockImplementation(vi.fn())
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:pluginId', component: PluginSettingsPage }],
  })
  try {
    await router.push('/record')
    const app = createSSRApp(() => h(RouterView))
    app.use(router).use(Antd).use(VueQueryPlugin, { queryClient: client })
    app.use(createI18n({ legacy: false, locale, missingWarn: false, fallbackWarn: false }))
    let action!: (hint: typeof button, value: string | boolean) => void
    app.mixin({
      created() {
        if (this.$options.__name === 'DeclarativeForm')
          action = (hint, value) => this.$emit('action', 'actions', hint, value)
      },
    })
    const html = await renderToString(app)
    expect(html).toContain('ant-steps')
    expect(html).toContain('Actions')
    expect(html).toContain('advanced')
    expect(html).not.toContain('later-step-value')
    action(menu, 'refresh')
    await vi.waitFor(() => expect(success).toHaveBeenCalledTimes(1))
    await vi.waitFor(() => expect(client.isFetching()).toBe(0))
    action(button, true)
    await vi.waitFor(() => expect(success).toHaveBeenCalledTimes(2))
    expect(start.mock.calls.map(([body]) => body)).toEqual([
      { configUid: 'config', group: 'actions', field: 'run', value: true, option: 'refresh' },
      { configUid: 'config', group: 'actions', field: 'check', value: true },
    ])
  } finally {
    client.clear()
    vi.restoreAllMocks()
  }
})
