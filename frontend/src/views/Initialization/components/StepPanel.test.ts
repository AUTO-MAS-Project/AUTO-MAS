import { describe, expect, it } from 'vitest'
import { createSSRApp, defineComponent, h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createI18n } from 'vue-i18n'
import zhCN from '@/i18n/locales/zh-CN'
import { decideFailureActions } from '@/utils/initializationDecision'
import StepPanel from './StepPanel.vue'

// 仓库没有 @vue/test-utils，也没有 DOM 环境，用 vue 自带的 SSR 渲染器出一份 HTML，
// 断言「给定失败对象时渲染出哪些按钮」。
const i18n = createI18n({
  legacy: false,
  locale: 'zh-CN',
  fallbackLocale: 'zh-CN',
  missingWarn: false,
  fallbackWarn: false,
  messages: { 'zh-CN': zhCN },
})

// ant-design-vue 的组件换成占位实现：默认插槽照渲染，文案在 prop 上的（alert / result）
// 也一并吐出来，这样断言的就是 StepPanel 自己决定展示什么，与 antd 的实现无关。
const stub = (name: string) =>
  defineComponent({
    name,
    inheritAttrs: false,
    setup(_props, { slots, attrs }) {
      const text = ['message', 'description', 'title', 'sub-title'].map(key =>
        attrs[key] === undefined ? null : h('span', null, String(attrs[key]))
      )
      return () => h('div', { class: name }, [...text, slots.default?.()])
    },
  })

const ANTD_STUBS = ['a-alert', 'a-button', 'a-card', 'a-progress', 'a-result', 'a-space', 'a-tag']

/** 按渲染顺序取出所有按钮的文案。 */
const buttonLabels = (html: string): string[] =>
  [...html.matchAll(/<div class="a-button"[^>]*>(.*?)<\/div>/g)].map(match =>
    match[1].replace(/<!--.*?-->/g, '').trim()
  )

async function renderFailedPanel(props: Record<string, unknown>): Promise<string> {
  const app = createSSRApp(StepPanel, {
    title: '依赖安装',
    status: 'failed',
    message: '主项目依赖同步失败',
    ...props,
  })
  app.use(i18n)
  for (const name of ANTD_STUBS) app.component(name, stub(name))
  return renderToString(app)
}

describe('StepPanel 失败态', () => {
  it('按 remediation 渲染出对应的按钮集合，并整块展示日志', async () => {
    const plan = decideFailureActions({
      code: 'DEPENDENCY_SYNC_FAILED',
      retryable: true,
      remediation: ['retry-sync', 'rebuild-environment', 'open-log'],
      stage: 'dependency',
      runtimeMode: 'managed',
    })

    const html = await renderFailedPanel({
      failureActions: plan.actions,
      failureNotice: plan.notice,
      showMirrorSelection: plan.showMirrorSelection,
      failureLogs: '[stdout]\nresolved 1 package\n\n[stderr]\nnetwork unreachable',
    })

    // 依赖段在 Runtime 下换不了镜像，所以是普通重试而不是换镜像重试，也不带镜像面板
    expect(buttonLabels(html)).toEqual(['重试', '重建环境', '打开日志'])
    expect(html).not.toContain('请选择镜像源重试')
    // 失败日志仍整块展示
    expect(html).toContain('network unreachable')
    expect(html).toContain('失败日志')
  })

  it('INTERNAL_ERROR 只给打开日志，并附上内部错误说明', async () => {
    const plan = decideFailureActions({
      code: 'INTERNAL_ERROR',
      retryable: false,
      remediation: ['open-log', 'contact-support'],
      stage: 'python',
      runtimeMode: 'managed',
    })

    const html = await renderFailedPanel({
      title: '准备运行环境',
      failureActions: plan.actions,
      failureNotice: plan.notice,
      showMirrorSelection: plan.showMirrorSelection,
    })

    expect(buttonLabels(html)).toEqual(['打开日志'])
    expect(html).toContain('这是运行时内部错误，请携带日志反馈')
  })

  it('旧链路缺字段时仍是「用选中的镜像源重试」加镜像面板', async () => {
    const plan = decideFailureActions({ stage: 'repository' })

    const html = await renderFailedPanel({
      title: '源码拉取',
      failureActions: plan.actions,
      failureNotice: plan.notice,
      showMirrorSelection: plan.showMirrorSelection,
      mirrors: [
        { key: 'cnb', name: 'CNB 官方镜像', url: '', type: 'mirror', description: '国内直连' },
      ],
    })

    expect(buttonLabels(html)).toEqual(['使用选中的镜像源重试'])
    expect(html).toContain('请选择镜像源重试')
    expect(html).toContain('CNB 官方镜像')
  })

  it('运行诊断的逐项结果按 status 字段着色展示', async () => {
    const html = await renderFailedPanel({
      failureActions: [{ kind: 'run-doctor', labelKey: 'init.failure.runDoctor' }],
      doctorChecks: [
        { id: 'layout', name: '受管布局', message: 'repo 缺失', status: 'missing', details: {} },
        { id: 'python', name: 'Python', message: '3.12.6', status: 'ok', details: {} },
      ],
    })

    expect(buttonLabels(html)).toEqual(['运行诊断'])
    expect(html).toContain('运行环境诊断')
    expect(html).toContain('受管布局')
    expect(html).toContain('repo 缺失')
    expect(html).toContain('3.12.6')
  })
})
