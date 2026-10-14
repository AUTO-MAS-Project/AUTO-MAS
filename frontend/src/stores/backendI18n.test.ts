import { beforeEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { ref } from 'vue'
import { i18n } from '@/i18n'

const mocks = vi.hoisted(() => ({
  getLocales: vi.fn(),
  getMessages: vi.fn(),
  subscribe: vi.fn(() => 'resource-sub'),
  unsubscribe: vi.fn(),
}))
vi.mock('@/composables/useBackendI18nApi', () => ({ useBackendI18nApi: () => mocks }))
vi.mock('@/services/websocket/subscriptions', () => ({
  subscribe: mocks.subscribe,
  unsubscribe: mocks.unsubscribe,
}))
vi.mock('@/services/websocket/connection', () => ({ connectionState: () => ref('open') }))

const { useBackendI18nStore } = await import('./backendI18n')

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  i18n.global.locale.value = 'zh-CN'
  mocks.getLocales.mockResolvedValue({ data: { available: ['zh_CN', 'en'], fallback: 'en' } })
})

it('replaces removed plugin resources and retains local page messages', async () => {
  const store = useBackendI18nStore()
  mocks.getMessages.mockResolvedValueOnce({
    data: {
      revision: '1',
      messages: {
        plugins: { demo: { title: '演示', missing: 'plugins.demo.missing' } },
      },
    },
  })
  await store.refresh()
  expect(i18n.global.t('plugins.demo.title')).toBe('演示')
  expect(i18n.global.te('plugins.demo.missing')).toBe(false)
  expect(i18n.global.t('plugins.title')).toBe('插件中心')
  mocks.getMessages.mockResolvedValueOnce({ data: { revision: '2', messages: { plugins: {} } } })
  await store.refresh()
  expect(i18n.global.te('plugins.demo.title')).toBe(false)
  expect(store.pluginNames).toEqual([])
})

it('ignores a previous-language response after a newer request finishes', async () => {
  let finishOld: (value: unknown) => void = () => {}
  const oldResponse = new Promise(resolve => {
    finishOld = resolve
  })
  mocks.getMessages.mockReturnValueOnce(oldResponse)
  const store = useBackendI18nStore()
  const old = store.refresh()
  await vi.waitFor(() => expect(mocks.getMessages).toHaveBeenCalledWith('zh_CN'))
  i18n.global.locale.value = 'en-US'
  mocks.getMessages.mockResolvedValueOnce({
    data: { revision: '2', messages: { plugins: { demo: { title: 'Demo' } } } },
  })
  await store.refresh()
  finishOld({ data: { revision: '1', messages: { plugins: { demo: { title: '旧响应' } } } } })
  await old
  expect(i18n.global.t('plugins.demo.title')).toBe('Demo')
  expect(store.revision).toBe('2')
})

it('uses the backend fallback for an unavailable locale and exposes failure for manual retry', async () => {
  i18n.global.locale.value = 'ja-JP'
  mocks.getMessages.mockRejectedValueOnce(new Error('offline'))
  const store = useBackendI18nStore()
  await store.refresh()
  expect(mocks.getMessages).toHaveBeenCalledWith('en')
  expect(store.error).toBe('offline')
  mocks.getMessages.mockResolvedValueOnce({ data: { revision: '3', messages: {} } })
  await store.refresh()
  expect(store.error).toBeNull()
  expect(store.loading).toBe(false)
})
