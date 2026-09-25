import { describe, expect, it } from 'vitest'
import { createSSRApp, defineComponent, h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createI18n } from 'vue-i18n'
import zhCN from '@/i18n/locales/zh-CN'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import SchedulerTaskControl from './SchedulerTaskControl.vue'

// 没有 DOM 环境，用 SSR 渲染器出 HTML，断言「选队列 / 选脚本时右侧出现哪些下拉」。
const i18n = createI18n({
  legacy: false,
  locale: 'zh-CN',
  fallbackLocale: 'zh-CN',
  missingWarn: false,
  fallbackWarn: false,
  messages: { 'zh-CN': zhCN },
})

const stub = (name: string) =>
  defineComponent({
    name,
    inheritAttrs: false,
    setup(_props, { attrs, slots }) {
      return () =>
        h('div', { class: name, 'data-placeholder': attrs.placeholder }, slots.default?.())
    },
  })

const taskOptions = [
  { label: '队列 - 日常', value: 'queue-1' },
  { label: 'MAA - 官服', value: 'script-1' },
]
const userOptions = [
  { label: '甲', value: 'u1' },
  { label: '乙', value: 'u2' },
]

async function renderPlaceholders(props: Record<string, unknown>): Promise<string[]> {
  const app = createSSRApp(SchedulerTaskControl, {
    selectedMode: TaskCreateIn.mode.AUTO_PROXY,
    taskOptions,
    taskOptionsLoading: false,
    status: '空闲',
    ...props,
  })
  app.use(i18n)
  for (const name of ['ASelect', 'ASelectOption', 'ASpace', 'AButton', 'ATag']) {
    app.component(name, stub(name))
  }
  const html = await renderToString(app)
  return [...html.matchAll(/<div class="ASelect" data-placeholder="([^"]*)"/g)].map(m => m[1])
}

const zh = zhCN.scheduler.control

describe('SchedulerTaskControl 右侧下拉', () => {
  it('选队列时只出现「从某一脚本开始」', async () => {
    const placeholders = await renderPlaceholders({ selectedTaskId: 'queue-1' })
    expect(placeholders).toContain(zh.resumePlaceholder)
    expect(placeholders).not.toContain(zh.resumeUserPlaceholder)
    expect(placeholders).not.toContain(zh.userPlaceholder)
  })

  it('选脚本时那一格换成「从某一用户开始」，与「单独运行指定用户」并列', async () => {
    const placeholders = await renderPlaceholders({ selectedTaskId: 'script-1', userOptions })
    expect(placeholders).not.toContain(zh.resumePlaceholder)
    expect(placeholders).toContain(zh.userPlaceholder)
    expect(placeholders).toContain(zh.resumeUserPlaceholder)
  })

  it('脚本没有可运行用户时两个用户下拉都不出现', async () => {
    const placeholders = await renderPlaceholders({ selectedTaskId: 'script-1', userOptions: [] })
    expect(placeholders).not.toContain(zh.userPlaceholder)
    expect(placeholders).not.toContain(zh.resumeUserPlaceholder)
  })

  it('运行中不显示任何选择下拉', async () => {
    const placeholders = await renderPlaceholders({
      selectedTaskId: 'script-1',
      userOptions,
      status: '运行',
    })
    expect(placeholders).toEqual([])
  })
})
