import { beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { createSSRApp, defineComponent, h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createI18n } from 'vue-i18n'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import Antd from 'ant-design-vue'
import type { GameBindingOptionsOut } from '@/api'
import type { GameBindingValue } from '@/types/games'
import GameBindingSection from './GameBindingSection.vue'

const { updateScript, updateUser } = vi.hoisted(() => ({
  updateScript: vi.fn(),
  updateUser: vi.fn(),
}))
vi.mock('@/composables/useScriptApi', () => ({ useScriptApi: () => ({ updateScript }) }))
vi.mock('@/composables/useUserApi', () => ({ useUserApi: () => ({ updateUser }) }))
vi.mock('@/services/websocket/connection', () => ({
  connectionState: vi.fn(),
  onConnected: vi.fn(),
  onDisconnected: vi.fn(),
}))
vi.mock('@/services/websocket/subscriptions', () => ({ subscribe: vi.fn(), unsubscribe: vi.fn() }))
const emptyBinding = { game_id: '-', device_id: '-' }
const unsupported = { supported: false, accountOverrideSupported: false, data: [] }

async function render({
  userId,
  options,
  binding = emptyBinding,
}: {
  userId?: string
  options?: GameBindingOptionsOut
  binding?: GameBindingValue
}) {
  const client = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity } } })
  if (options) client.setQueryData(['game-binding-options', 'script', userId], options)
  client.setQueryData(['game-binding', 'script', userId], { binding })
  const route = { component: GameBindingSection }
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { ...route, path: '/scripts/:scriptId' },
      { ...route, path: '/scripts/:scriptId/users/:userId' },
      { ...route, path: '/games' },
    ],
  })
  await router.push(userId ? `/scripts/script/users/${userId}` : '/scripts/script')
  const app = createSSRApp(() => h(GameBindingSection, { scriptId: 'script' }))
  app.use(router)
  app.use(Antd)
  app.use(VueQueryPlugin, { queryClient: client })
  app.use(createI18n({ legacy: false, locale: 'en', missingWarn: false, fallbackWarn: false }))
  const controls: Record<string, { attrs: Record<string, unknown>; trigger: () => void }> = {}
  for (const name of ['a-switch', 'a-button']) {
    app.component(
      name,
      defineComponent({
        inheritAttrs: false,
        setup(_, { attrs, emit, slots }) {
          controls[name] = {
            attrs,
            trigger: () => (name === 'a-switch' ? emit('change', false) : emit('click')),
          }
          return () => h('button', slots.default?.())
        },
      })
    )
  }
  const html = await renderToString(app)
  return { html, controls }
}

beforeEach(() => {
  updateScript.mockReset().mockResolvedValue(true)
  updateUser.mockReset().mockResolvedValue(true)
})

describe('游戏绑定显示和清理', () => {
  it('等待能力响应期间保留托管绑定区，确认不支持后隐藏空绑定', async () => {
    expect((await render({})).html).toContain('core.games.defaultBinding')
    expect((await render({ options: unsupported })).html).not.toContain('core.games.defaultBinding')
  })

  it('仅禁止账号覆写时，托管仍可绑定，空账号覆写条隐藏', async () => {
    const options = { supported: true, accountOverrideSupported: false, data: [] }
    expect((await render({ options })).html).toContain('core.games.defaultBinding')
    const { html } = await render({ userId: 'user', options })
    expect(html).not.toContain('core.games.accountBinding')
  })

  it('账号仍有旧目标时显示告警，关闭覆写提交复位', async () => {
    const { html, controls } = await render({
      userId: 'user',
      options: { supported: true, accountOverrideSupported: false, data: [] },
      binding: { game_id: 'old-target', device_id: 'old-device' },
    })
    expect(html).toContain('core.games.bindingUnsupported')
    const toggle = controls['a-switch']!
    expect(toggle.attrs).toMatchObject({ checked: true, disabled: false })
    toggle.trigger()
    await vi.waitFor(() =>
      expect(updateUser).toHaveBeenCalledWith('script', 'user', { game: emptyBinding })
    )
  })

  it('已选目标类型不一致时只提示，不清空绑定', async () => {
    const { html } = await render({
      options: {
        supported: true,
        accountOverrideSupported: true,
        data: [{ value: 'client-target', label: '客户端', warning: '类型不一致提示' }],
      },
      binding: { game_id: 'client-target', device_id: '-' },
    })
    expect(html).toMatch(/ant-alert-warning[^]*?ant-alert-message[^>]*>类型不一致提示</)
    // 只是提示，绑定照常可用，不提供清空入口
    expect(html).not.toContain('core.edit.clear')
    expect(updateScript).not.toHaveBeenCalled()
  })

  it('托管只剩不可用原因时仍可清除旧绑定', async () => {
    const { html, controls } = await render({
      options: unsupported,
      binding: { ...emptyBinding, unavailable_reason: '旧目标不可用' },
    })
    expect(html).toContain('旧目标不可用')
    expect(html).toContain('core.edit.clear')
    controls['a-button']!.trigger()
    await vi.waitFor(() =>
      expect(updateScript).toHaveBeenCalledWith('script', { game: emptyBinding })
    )
  })
})
