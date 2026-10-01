import { describe, expect, it } from 'vitest'
import { createSSRApp, defineComponent, h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createI18n } from 'vue-i18n'
import zhCN from '@/i18n/locales/zh-CN'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import SchedulerTaskControl from './SchedulerTaskControl.vue'

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
        h(
          'div',
          {
            class: name,
            'data-placeholder': attrs.placeholder,
            'data-value': JSON.stringify(attrs.value),
          },
          slots.default?.()
        )
    },
  })

const taskOptions = [
  { label: '队列 - 日常', value: 'queue-1' },
  { label: 'MAA - 官服', value: 'script-1' },
]

const renderControl = async (props: Record<string, unknown>): Promise<string> => {
  const app = createSSRApp(SchedulerTaskControl, {
    selectedMode: TaskCreateIn.mode.AUTO_PROXY,
    taskOptions,
    taskOptionsLoading: false,
    status: '空闲',
    ...props,
  })
  app.use(i18n)
  for (const name of [
    'ASelect',
    'ASelectOption',
    'ASpace',
    'AButton',
    'ATag',
    'ACheckbox',
    'ADivider',
  ]) {
    app.component(name, stub(name))
  }
  return renderToString(app)
}

const placeholders = async (props: Record<string, unknown>): Promise<string[]> => {
  const html = await renderControl(props)
  return [...html.matchAll(/<div class="ASelect" data-placeholder="([^"]*)"/g)].map(
    match => match[1]
  )
}

describe('SchedulerTaskControl 用户范围', () => {
  it('脚本用户列表为空时仍显示下拉，允许用户打开重试', async () => {
    expect(await placeholders({ selectedTaskId: 'script-1', userOptions: [] })).toContain(
      zhCN.scheduler.control.runUsersPlaceholder
    )
  })

  it('选队列时只显示恢复脚本下拉', async () => {
    const shown = await placeholders({ selectedTaskId: 'queue-1' })
    expect(shown).toContain(zhCN.scheduler.control.resumePlaceholder)
    expect(shown).not.toContain(zhCN.scheduler.control.runUsersPlaceholder)
  })

  it('从父状态恢复 A+C，不在初次渲染时覆盖', async () => {
    const html = await renderControl({
      selectedTaskId: 'script-1',
      selectedUserIds: ['u1', 'u3'],
      userOptions: [
        { label: '甲', value: 'u1' },
        { label: '乙', value: 'u2' },
        { label: '丙', value: 'u3' },
      ],
    })
    expect(html).toContain('data-value="[&quot;u1&quot;,&quot;u3&quot;]"')
  })
})
