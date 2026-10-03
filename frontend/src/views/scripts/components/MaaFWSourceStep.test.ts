import { afterEach, describe, expect, it, vi } from 'vitest'
import { createSSRApp, defineComponent, h, type SetupContext } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createI18n } from 'vue-i18n'
import zhCN from '@/i18n/locales/zh-CN'
import type { MaaFWCreateSourceSectionProps } from '@/views/EditView/MaaFWFlavor/sectionContracts'
import MaaFWSourceStep from './MaaFWSourceStep.vue'
import type { MfwReuseChoice } from './scriptCreateFlow'

// 新建对话框 MFW 家族第二步的默认分节。仓库没有 DOM 测试环境，用 vue 自带的 SSR 渲染器出 HTML；
// antd 组件换成把入参写出来的壳，点击 / 选择在壳的 setup 里替用户做一次。

const i18n = createI18n({
  legacy: false,
  locale: 'zh-CN',
  fallbackLocale: 'zh-CN',
  missingWarn: false,
  fallbackWarn: false,
  messages: { 'zh-CN': zhCN },
})

const actions: { select?: string; clickRetry?: boolean } = {}

type StubAttrs = SetupContext['attrs'] & Record<string, unknown>
const call = (attrs: StubAttrs, name: string, ...args: unknown[]) =>
  (attrs[name] as ((...values: unknown[]) => void) | undefined)?.(...args)

const stubs = {
  ARadioGroup: defineComponent({
    inheritAttrs: false,
    setup(_props, { attrs, slots }) {
      const a = attrs as StubAttrs
      if (actions.select !== undefined) call(a, 'onUpdate:value', actions.select)
      return () =>
        h('div', { class: ['ARadioGroup', a.class], 'data-value': a.value }, slots.default?.())
    },
  }),
  ARadio: defineComponent({
    inheritAttrs: false,
    setup(_props, { attrs }) {
      return () =>
        h(
          'i',
          { class: 'ARadio' },
          JSON.stringify({ value: attrs.value, disabled: attrs.disabled })
        )
    },
  }),
  AAlert: defineComponent({
    inheritAttrs: false,
    setup(_props, { attrs, slots }) {
      return () =>
        h('div', { class: ['AAlert', attrs.class] }, [String(attrs.message), slots.action?.()])
    },
  }),
  AButton: defineComponent({
    inheritAttrs: false,
    setup(_props, { attrs, slots }) {
      if (actions.clickRetry) call(attrs as StubAttrs, 'onClick')
      return () => h('button', slots.default?.())
    },
  }),
  ASpin: defineComponent({ inheritAttrs: false, setup: () => () => h('i', { class: 'ASpin' }) }),
}

const choices: MfwReuseChoice[] = [
  {
    scriptId: 'a1',
    scriptName: '早上',
    projectName: '项目A',
    version: 'v1',
    busy: false,
    scriptCount: 2,
  },
  {
    scriptId: 'b1',
    scriptName: '没读出来',
    projectName: '',
    version: '',
    busy: true,
    scriptCount: 1,
  },
]

const render = async (
  props: Partial<MaaFWCreateSourceSectionProps> = {},
  listeners: Record<string, (...args: never[]) => void> = {}
) => {
  const app = createSSRApp(MaaFWSourceStep, {
    type: 'MaaFW',
    choices: [],
    loading: false,
    error: null,
    value: 'new',
    ...props,
    ...listeners,
  })
  app.use(i18n)
  for (const [name, component] of Object.entries(stubs)) app.component(name, component)
  return (await renderToString(app))
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/ data-v-[0-9a-f]+(="")?/g, '')
}

const rows = (html: string) => [...html.matchAll(/<label class="([^"]*)">/g)].map(m => m[1])

afterEach(() => {
  delete actions.select
  delete actions.clickRetry
})

describe('MaaFWSourceStep 项目来源默认分节', () => {
  it('第一行永远是新建；复用行按列表顺序，在跑的那行禁用并标「运行中」', async () => {
    const html = await render({ choices, value: 'a1' })
    expect(rows(html)).toEqual(['choice-row', 'choice-row selected', 'choice-row disabled'])
    expect(html).toContain('<div class="ARadioGroup choice-list" data-value="a1">')
    expect(html).toContain(zhCN.scripts.create.mfwNewProject)
    expect(html).toContain(zhCN.scripts.create.mfwReuse)
    expect(html).toContain(JSON.stringify({ value: 'a1', disabled: false }).replace(/"/g, '&quot;'))
    expect(html).toContain(JSON.stringify({ value: 'b1', disabled: true }).replace(/"/g, '&quot;'))
    // 标题是项目名，读不出就用脚本名；副标题带来源脚本、版本与「运行中」（文案取词表，措辞改了不用跟着改）
    const { t } = i18n.global
    const fromMany = t('scripts.create.mfwReuseFromMany', { name: '早上', count: 2 })
    const fromOne = t('scripts.create.mfwReuseFrom', { name: '没读出来' })
    expect(html).toContain('<span class="choice-title">项目A</span>')
    expect(html).toContain(`<span class="choice-description">${fromMany} · v1</span>`)
    expect(html).toContain('<span class="choice-title">没读出来</span>')
    expect(html).toContain(
      `<span class="choice-description">${fromOne} · ${t('scripts.create.mfwReuseBusy')}</span>`
    )
    expect(html).not.toContain('choice-placeholder')
    expect(html).not.toContain('AAlert')
  })

  it('读列表时显示加载占位，不列复用行', async () => {
    const html = await render({ choices, loading: true })
    expect(rows(html)).toEqual(['choice-row selected'])
    expect(html).toContain(
      `<div class="choice-placeholder"><i class="ASpin"></i><span>${zhCN.scripts.create.mfwReuseLoading}</span></div>`
    )
  })

  it('没读出来：错误条 + 重试（交回 retry），不当成「没有可复用的项目」', async () => {
    const onRetry = vi.fn()
    actions.clickRetry = true
    const html = await render({ error: '读失败' }, { onRetry })
    expect(html).toContain(
      `<div class="AAlert template-alert">读失败<button>${zhCN.scripts.create.retry}</button></div>`
    )
    expect(onRetry).toHaveBeenCalledOnce()
    expect(html).not.toContain('choice-placeholder')
  })

  it('列表为空：按入口类型提示没有可复用的项目', async () => {
    const html = await render({ type: 'MaaFW' })
    expect(html).toContain(
      `<div class="choice-placeholder">${zhCN.scripts.create.mfwReuseEmpty.replace('{type}', 'MaaFW')}</div>`
    )
  })

  it('选择交回 update:value，选中状态不自己留', async () => {
    const onUpdate = vi.fn()
    actions.select = 'a1'
    const html = await render({ choices }, { 'onUpdate:value': onUpdate })
    expect(onUpdate.mock.calls).toEqual([['a1']])
    expect(html).toContain('data-value="new"')
  })
})
