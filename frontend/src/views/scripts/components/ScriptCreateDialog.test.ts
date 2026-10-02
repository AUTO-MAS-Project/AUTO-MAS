import { readFileSync } from 'node:fs'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createSSRApp, defineComponent, getCurrentInstance, h, type Component } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createI18n } from 'vue-i18n'
import zhCN from '@/i18n/locales/zh-CN'
import {
  defineMaaFWLazyComponent,
  defineMaaFWSection,
  type MaaFWFlavor,
  type MaaFWSection,
} from '@/composables/maafwFlavorTypes'
import { resolveMaaFWFlavor } from '@/composables/useMaaFWFlavor'
import ScriptCreateDialog from './ScriptCreateDialog.vue'

const source = readFileSync(new URL('./ScriptCreateDialog.vue', import.meta.url), 'utf8')

describe('ScriptCreateDialog structure', () => {
  it('does not render a sidebar for the linear create flow', () => {
    expect(source).not.toContain('<aside class="step-sidebar"')
  })

  it('keeps the modal below the title bar and scrolls content inside short windows', () => {
    expect(source).toContain(':z-index="900"')
    expect(source).toContain('top: 64px;')
    expect(source).toContain('height: min(500px, calc(100vh - 192px));')
    expect(source.match(/overflow-y: auto;/g)).toHaveLength(1)
  })

  it('centers template loading in a sized state container', () => {
    expect(source).toContain('<div v-if="templateLoading" class="template-loading-state">')
    expect(source).toContain('<a-spin size="large" :tip="t(\'scripts.create.templateLoading\')" />')
    expect(source).toContain('min-height: 240px;')
    expect(source).not.toContain('<a-spin :spinning="templateLoading">')
  })
})

// ---- MFW 家族第二步：分节替换与插入点 ----
// 仓库没有 DOM 测试环境，用 SSR 渲染整个对话框。对话框的步骤状态是内部的，由 AModal 的壳在
// 渲染插槽前直接改（开发构建下 setupState 暴露全部绑定）；antd 组件换成只渲染插槽的壳。

/** 按类型换掉注册表里的描述对象（只在本文件里） */
const fakeFlavors = vi.hoisted(() => new Map<string, unknown>())
vi.mock('@/composables/useMaaFWFlavor', async importOriginal => {
  const actual = await importOriginal<typeof import('@/composables/useMaaFWFlavor')>()
  return {
    ...actual,
    resolveMaaFWFlavor: (type: string | null | undefined) =>
      (type && fakeFlavors.get(type)) || actual.resolveMaaFWFlavor(type),
  }
})

const i18n = createI18n({
  legacy: false,
  locale: 'zh-CN',
  fallbackLocale: 'zh-CN',
  missingWarn: false,
  fallbackWarn: false,
  messages: { 'zh-CN': zhCN },
})

const shell = (name: string) =>
  defineComponent({
    name,
    inheritAttrs: false,
    setup(_props, { attrs, slots }) {
      return () =>
        h(
          'div',
          { class: [name, attrs.class] },
          Object.values(slots).map(slot => slot?.())
        )
    },
  })
const SHELLS = [
  'AInput',
  'ARadioGroup',
  'ARadio',
  'AEmpty',
  'AButton',
  'AAlert',
  'ASpin',
  'ADescriptions',
  'ADescriptionsItem',
  'ASpace',
]

/** 替换分节 / 插入点收到的入参 */
const received = new Map<string, Record<string, unknown>>()
const recordingStub = (name: string) =>
  defineComponent({
    name,
    inheritAttrs: false,
    setup(_props, { attrs }) {
      received.set(name, { ...attrs })
      return () => h('section', { 'data-section': name })
    },
  })

/** 测试里的替换分节不声明契约 props，绕开 defineMaaFWSection 的类型检查（运行时同一个函数） */
const fakeSourceSection = (load: () => Promise<Component>) =>
  (
    defineMaaFWSection as unknown as (
      part: 'create',
      key: 'source',
      load: () => Promise<Component>
    ) => MaaFWSection<'create', 'source'>
  )('create', 'source', load)

const sources = [
  { scriptId: 'a1', name: '甲', type: 'MSS', projectName: 'P', version: 'v1', busy: false },
  { scriptId: 'm1', name: '乙', type: 'MaaFW', projectName: 'Q', version: 'v2', busy: false },
]

const renderSourceStep = async (type: string, selection = 'new') => {
  const Modal = defineComponent({
    inheritAttrs: false,
    setup(_props, { slots }) {
      const dialog = getCurrentInstance()!.parent as unknown as {
        setupState: Record<string, unknown>
      }
      Object.assign(dialog.setupState, {
        selectedType: type,
        currentStep: 'config',
        selectedMfwChoice: selection,
      })
      return () => h('div', { class: 'AModal' }, slots.default?.())
    },
  })
  const app = createSSRApp(ScriptCreateDialog, {
    open: true,
    templates: [],
    submitting: false,
    templateLoading: false,
    templateError: null,
    mfwSources: sources,
    mfwSourcesLoading: false,
    mfwSourcesError: null,
  })
  app.use(i18n)
  app.component('AModal', Modal)
  for (const name of SHELLS) app.component(name, shell(name))
  return (await renderToString(app))
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/ data-v-[0-9a-f]+(="")?/g, '')
}

/** 给某个特调换上 source 分节与 afterSourceStep 插入点 */
const withCreateParts = (type: string) => {
  const base = resolveMaaFWFlavor(type)
  const load = vi.fn(async () => recordingStub('flavor:source'))
  const flavor: MaaFWFlavor = {
    ...base,
    create: {
      ...base.create,
      sections: { source: fakeSourceSection(load) },
      slots: {
        afterSourceStep: [
          defineMaaFWLazyComponent(async () => recordingStub('slot:afterSourceStep')),
        ],
      },
    },
  }
  fakeFlavors.set(type, flavor)
  return load
}

afterEach(() => {
  fakeFlavors.clear()
  received.clear()
})

describe('ScriptCreateDialog · MFW 家族第二步', () => {
  it('默认：渲染 MFW 的项目来源分节，后面没有插入点内容', async () => {
    const html = await renderSourceStep('MaaFW')
    expect(html).toContain(`<h3>${zhCN.scripts.create.mfwSourceHeading}</h3>`)
    expect(html).toContain('<div class="ARadioGroup choice-list">')
    expect(html).toContain(zhCN.scripts.create.mfwNewProject)
    // 只列与入口同类型的项目
    expect(html).toContain('<span class="choice-title">Q</span>')
    expect(html).not.toContain('<span class="choice-title">P</span>')
    expect(html).not.toContain('data-section')
  })

  it('特调替换 source：替换分节顶上，收到契约里的全部入参与 v-model / retry 监听', async () => {
    const load = withCreateParts('MSS')
    const html = await renderSourceStep('MSS', 'a1')
    expect(load).toHaveBeenCalledOnce()
    expect(html).not.toContain('choice-list')
    // 替换分节之后紧跟插入点
    expect(html).toContain(
      '<section data-section="flavor:source"></section><section data-section="slot:afterSourceStep"></section>'
    )
    const attrs = received.get('flavor:source')!
    expect(Object.keys(attrs).sort()).toEqual(
      ['choices', 'error', 'loading', 'onRetry', 'onUpdate:value', 'type', 'value'].sort()
    )
    expect(attrs).toMatchObject({ type: 'MSS', value: 'a1', loading: false, error: null })
    expect(attrs.choices).toEqual([expect.objectContaining({ scriptId: 'a1', projectName: 'P' })])
    // 插入点只读：只收 context，没有任何监听
    expect(received.get('slot:afterSourceStep')).toEqual({
      context: { type: 'MSS', selection: 'a1' },
    })
  })

  it('替换与插入点只对声明它们的特调生效', async () => {
    withCreateParts('MSS')
    const html = await renderSourceStep('MaaFW')
    expect(html).toContain('<div class="ARadioGroup choice-list">')
    expect(html).not.toContain('data-section')
  })

  it('对话框不写特调类型字面量，按选中的类型卡片取特调', () => {
    expect(source).not.toMatch(/['"`](M9A|MSS)['"`]/)
    expect(source).toContain('resolveMaaFWFlavor(selectedType.value)')
    expect(source).toContain('<MaaFWFlavorSlot')
    expect(source).toContain('part="create"')
  })
})
