import { createSSRApp } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createI18n } from 'vue-i18n'
import { afterEach, expect, it, vi } from 'vite-plus/test'
import zh from '../../../res/i18n/zh_CN.json'
import en from '../../../res/i18n/en.json'
import ja from '../../../res/i18n/ja.json'
import { bootstrapSystemNotices, disposeSystemNotices } from './systemNotices'
import { WS_ID_MAIN, WS_SYSTEM_NOTICE } from './websocket/types'

const boundary = vi.hoisted(() => ({
  callbacks: new Map(),
  warning: vi.fn(),
  translate: vi.fn(),
}))
vi.mock('ant-design-vue', () => ({ notification: { warning: boundary.warning } }))
vi.mock('@/i18n', () => ({ translate: (key: string) => boundary.translate(key) }))
vi.mock('@/services/websocket/subscriptions', () => ({
  subscribe: (criteria: { id: string; type: string }, handler: unknown) => {
    const key = `${criteria.id}:${criteria.type}`
    boundary.callbacks.set(key, handler)
    return key
  },
  unsubscribe: (id: string) => boundary.callbacks.delete(id),
}))
afterEach(() => {
  disposeSystemNotices()
  boundary.warning.mockClear()
})

it.each([
  ['zh-CN', zh],
  ['en-US', en],
  ['ja-JP', ja],
] as const)('renders wake-up errors in %s', async (locale, catalog) => {
  const i18n = createI18n({
    legacy: false,
    locale,
    flatJson: true,
    messages: { [locale]: structuredClone(catalog) },
  })
  boundary.translate.mockImplementation((key: string) => i18n.global.t(key))
  bootstrapSystemNotices()
  boundary.callbacks.get(`${WS_ID_MAIN}:${WS_SYSTEM_NOTICE}`)({
    data: {
      level: 'warning',
      title: '定时唤醒同步失败',
      lines: ['请检查日志'],
      titleKey: 'core.setting.func.scheduledWakeupFailure',
      lineKeys: ['core.setting.func.scheduledWakeupFailureTip'],
    },
  })
  const args = boundary.warning.mock.calls[0][0]
  expect(args.message).toBe(catalog['core.setting.func.scheduledWakeupFailure'])
  const rendered = await renderToString(createSSRApp({ render: args.description }))
  expect(rendered).toContain(catalog['core.setting.func.scheduledWakeupFailureTip'])
})

it('preserves plain messages from older backends', async () => {
  bootstrapSystemNotices()
  boundary.callbacks.get(`${WS_ID_MAIN}:${WS_SYSTEM_NOTICE}`)({
    data: { level: 'warning', title: 'Existing title', lines: ['Existing body'] },
  })
  const args = boundary.warning.mock.calls[0][0]
  expect(args.message).toBe('Existing title')
  expect(await renderToString(createSSRApp({ render: args.description }))).toContain(
    'Existing body'
  )
})
