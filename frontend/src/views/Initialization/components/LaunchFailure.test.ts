import { describe, expect, it } from 'vitest'
import { createSSRApp, defineComponent, h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createI18n } from 'vue-i18n'
import zhCN from '@/i18n/locales/zh-CN'
import { decideFailureActions } from '@/utils/initializationDecision'
import LaunchFailure from './LaunchFailure.vue'

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

// AButton（<a-button>）换成占位实现：默认插槽照渲染，这样断言的是 LaunchFailure 自己决定展示什么，
// 与 antd 的实现无关。跳过按钮是原生 button，不会混进下面的统计里。
const stub = (name: string) =>
  defineComponent({
    name,
    inheritAttrs: false,
    setup(_props, { slots }) {
      return () => h('div', { class: name }, slots.default?.())
    },
  })

/** 按渲染顺序取出所有 AButton 的文案。 */
const buttonLabels = (html: string): string[] =>
  [...html.matchAll(/<div class="AButton"[^>]*>(.*?)<\/div>/g)].map(match =>
    match[1].replace(/<!--.*?-->/g, '').trim()
  )

async function renderFailure(props: Record<string, unknown>): Promise<string> {
  const app = createSSRApp(LaunchFailure, {
    title: '安装依赖',
    message: '主项目依赖同步失败',
    ...props,
  })
  app.use(i18n)
  app.component('AButton', stub('AButton'))
  return renderToString(app)
}

describe('LaunchFailure', () => {
  it('按 remediation 渲染出对应的按钮集合，日志收在同一个折叠里', async () => {
    const plan = decideFailureActions({
      code: 'DEPENDENCY_SYNC_FAILED',
      retryable: true,
      remediation: ['retry-sync', 'rebuild-environment', 'open-log'],
      stage: 'dependency',
      runtimeMode: 'managed',
    })

    const html = await renderFailure({
      failureActions: plan.actions,
      failureNotice: plan.notice,
      showMirrorSelection: plan.showMirrorSelection,
      failureLogs: '[stdout]\nresolved 1 package\n\n[stderr]\nnetwork unreachable',
    })

    // 依赖段在 Runtime 下换不了镜像，所以是普通重试而不是换源重试，也不带源列表
    expect(buttonLabels(html)).toEqual(['重试', '重建运行环境', '查看日志'])
    expect(html).not.toContain('换一个源重试')
    // 日志仍然整块给出，只是收进「详细信息」
    expect(html).toContain('详细信息')
    expect(html).toContain('network unreachable')
  })

  it('INTERNAL_ERROR 只给打开日志，并附上内部错误说明', async () => {
    const plan = decideFailureActions({
      code: 'INTERNAL_ERROR',
      retryable: false,
      remediation: ['open-log', 'contact-support'],
      stage: 'python',
      runtimeMode: 'managed',
    })

    const html = await renderFailure({
      title: '运行环境',
      failureActions: plan.actions,
      failureNotice: plan.notice,
      showMirrorSelection: plan.showMirrorSelection,
    })

    expect(buttonLabels(html)).toEqual(['查看日志'])
    expect(html).toContain('这是程序内部的问题')
  })

  it('旧链路缺字段时仍是换源重试，并列出可选的源', async () => {
    const plan = decideFailureActions({ stage: 'repository' })

    const html = await renderFailure({
      title: '程序文件',
      failureActions: plan.actions,
      failureNotice: plan.notice,
      showMirrorSelection: plan.showMirrorSelection,
      mirrors: [
        { key: 'cnb', name: 'CNB 官方镜像', url: '', type: 'mirror', description: '国内直连' },
      ],
    })

    expect(buttonLabels(html)).toEqual(['换个下载源重试', '查看日志'])
    expect(html).toContain('换一个源重试')
    expect(html).toContain('CNB 官方镜像')
  })

  it('可重试且可跳过的失败仍保留查看日志入口', async () => {
    const plan = decideFailureActions({
      code: 'DIRECTORY_OCCUPIED',
      retryable: true,
      remediation: ['retry'],
    })

    const html = await renderFailure({
      failureActions: plan.actions,
      showSkipButton: true,
    })

    expect(buttonLabels(html)).toEqual(['重试', '查看日志'])
    expect(html).toContain('跳过此步骤')
  })

  it('运行环境检查的逐项结果按 status 字段着色展示', async () => {
    const html = await renderFailure({
      failureActions: [{ kind: 'run-doctor', labelKey: 'init.failure.runDoctor' }],
      doctorChecks: [
        { id: 'layout', name: '受管布局', message: 'repo 缺失', status: 'missing', details: {} },
        { id: 'python', name: 'Python', message: '3.12.6', status: 'ok', details: {} },
      ],
    })

    expect(buttonLabels(html)).toEqual(['检查运行环境'])
    expect(html).toContain('受管布局')
    expect(html).toContain('repo 缺失')
    expect(html).toContain('3.12.6')
  })

  it('可跳过的步骤把后果写在按钮旁边', async () => {
    const html = await renderFailure({ showSkipButton: true })

    expect(html).toContain('跳过此步骤')
    expect(html).toContain('程序可能无法正常运行')
  })
})
