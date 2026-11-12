import { describe, expect, it, vi } from 'vite-plus/test'
import { createSSRApp, defineComponent, h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createI18n } from 'vue-i18n'
import messages from '../../../../res/i18n/zh_CN.json'
import type { TaskboardVersionStoryRecord } from '@/types/taskboard'
import VersionStoryPanel from './components/VersionStoryPanel.vue'

const mocks = vi.hoisted(() => ({
  store: {
    versionStory: {} as Record<string, TaskboardVersionStoryRecord>,
    versionStorySaving: [] as string[],
    versionStoryError: '',
    loading: false,
    isVersionStoryDone: () => false,
    setVersionStoryDone: vi.fn(),
    retryVersionStory: vi.fn(),
  },
}))

vi.mock('@/stores/taskboardState', () => ({
  useTaskboardStateStore: () => mocks.store,
}))

const record = (version: string, start: string, end: string): TaskboardVersionStoryRecord => ({
  game: 'wutheringwaves',
  version,
  version_name: version,
  start,
  end,
  cover_url: '',
  first_seen: '',
  last_seen: '',
})

const renderPanel = async (now: number) => {
  mocks.store.versionStory = {
    'wutheringwaves|3.7': record('3.7', '2026-09-30T11:00:00+08:00', '2026-11-11T03:59:59+08:00'),
    'wutheringwaves|3.8': record('3.8', '2026-11-12T11:00:00+08:00', '2026-12-22T03:59:59+08:00'),
  }

  const app = createSSRApp({
    render: () =>
      h(VersionStoryPanel, {
        options: [{ key: 'wutheringwaves', name: '鸣潮', cover: '' }],
        now,
      }),
  })
  app.use(
    createI18n({
      legacy: false,
      locale: 'zh-CN',
      flatJson: true,
      messages: { 'zh-CN': messages },
    })
  )
  const passthrough = defineComponent({
    setup:
      (_, { slots }) =>
      () =>
        h('div', slots.default?.()),
  })
  for (const name of ['ASpin', 'AAlert', 'AButton', 'NoData']) {
    app.component(name, passthrough)
  }
  return await renderToString(app)
}

describe('版本主线时间状态', () => {
  it('uses the provided clock to show the gap before the next version starts', async () => {
    const html = await renderPanel(Date.parse('2026-11-11T12:00:00+08:00'))
    expect(html).toContain('活动已结束，1天后更新')
  })

  it('stops treating the new version start as the next update after it begins', async () => {
    const html = await renderPanel(Date.parse('2026-11-12T12:00:00+08:00'))
    expect(html).toContain('还有 40 天')
    expect(html).not.toContain('当天更新，等待新版本')
    expect(html).not.toContain('还有 1 天')
  })
})
