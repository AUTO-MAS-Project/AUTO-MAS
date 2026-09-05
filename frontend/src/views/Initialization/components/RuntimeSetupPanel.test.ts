import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { createSSRApp, defineComponent, h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createI18n } from 'vue-i18n'
import { describe, expect, it } from 'vitest'
import zhCN from '@/i18n/locales/zh-CN'
import { decideFailureActions } from '@/utils/initializationDecision'
import RuntimeSetupPanel from './RuntimeSetupPanel.vue'

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
      const propText = ['message', 'description', 'title'].map(key =>
        attrs[key] === undefined ? null : h('span', null, String(attrs[key]))
      )
      return () => h('div', { class: name }, [...propText, slots.default?.()])
    },
  })

async function renderPanel(props: Record<string, unknown>): Promise<string> {
  const app = createSSRApp(RuntimeSetupPanel, {
    title: '准备运行环境',
    status: 'processing',
    message: '正在准备固定版本运行组件',
    ...props,
  })
  app.use(i18n)
  for (const name of ['a-alert', 'a-button', 'a-card', 'a-space', 'a-tag']) {
    app.component(name, stub(name))
  }
  return renderToString(app)
}

describe('新版初始化状态面板', () => {
  it('有可靠数值时展示当前步骤进度、动作和计时', async () => {
    const html = await renderPanel({
      elapsedText: '01:24',
      progress: 42,
      progressIndeterminate: false,
    })

    expect(html).toContain('正在准备固定版本运行组件')
    expect(html).toContain('当前步骤进度')
    expect(html).toContain('42%')
    expect(html).toContain('首次准备约需 1–5 分钟')
    expect(html).toContain('已用时 01:24')
  })

  it('没有可靠总量时展示持续活动进度，不把兼容值当成百分比', async () => {
    const html = await renderPanel({ progress: 10, progressIndeterminate: true })

    expect(html).toContain('持续进行中')
    expect(html).toContain('role="progressbar"')
    expect(html).not.toContain('10%')
  })

  it('失败时保留 Runtime 给出的恢复动作和日志', async () => {
    const plan = decideFailureActions({
      code: 'DEPENDENCY_SYNC_FAILED',
      retryable: true,
      remediation: ['retry-sync', 'rebuild-environment', 'open-log'],
      stage: 'dependency',
      runtimeMode: 'managed',
    })

    const html = await renderPanel({
      status: 'failed',
      message: '运行依赖同步失败',
      failureActions: plan.actions,
      failureLogs: '[stderr]\nnetwork unreachable',
    })

    expect(html).toContain('运行依赖同步失败')
    expect(html).toContain('重试')
    expect(html).toContain('重建环境')
    expect(html).toContain('打开日志')
    expect(html).toContain('network unreachable')
  })

  it('实际路由保留分阶段布局，两个工作面板都展示当前步骤进度', () => {
    const pageSource = readFileSync(
      fileURLToPath(new URL('../RuntimeInitializationPage.vue', import.meta.url)),
      'utf8'
    )
    const setupSource = readFileSync(
      fileURLToPath(new URL('./RuntimeSetupPanel.vue', import.meta.url)),
      'utf8'
    )
    const backendSource = readFileSync(
      fileURLToPath(new URL('./RuntimeBackendStartPanel.vue', import.meta.url)),
      'utf8'
    )

    expect(pageSource).not.toContain('<a-steps')
    expect(setupSource).toContain('<a-progress')
    expect(backendSource).toContain('<a-progress')
  })

  it('初始化主区域和状态内容随窗口宽度伸缩', () => {
    const pageSource = readFileSync(
      fileURLToPath(new URL('../RuntimeInitializationPage.vue', import.meta.url)),
      'utf8'
    )
    const setupSource = readFileSync(
      fileURLToPath(new URL('./RuntimeSetupPanel.vue', import.meta.url)),
      'utf8'
    )
    const backendSource = readFileSync(
      fileURLToPath(new URL('./RuntimeBackendStartPanel.vue', import.meta.url)),
      'utf8'
    )

    expect(pageSource).toContain('grid-template-columns: clamp(15rem, 24%, 19rem) minmax(0, 1fr)')
    expect(pageSource).not.toContain('max-width: 980px')
    expect(setupSource).toContain('inline-size: min(100%, 72ch)')
    expect(setupSource).not.toContain('max-width: 560px')
    expect(backendSource).toContain('inline-size: min(100%, 72ch)')
    expect(backendSource).not.toContain('max-width: 560px')
  })

  it('初始化页只保留必要状态信息，并在主状态区提示首次耗时', () => {
    const pageSource = readFileSync(
      fileURLToPath(new URL('../RuntimeInitializationPage.vue', import.meta.url)),
      'utf8'
    )
    const setupSource = readFileSync(
      fileURLToPath(new URL('./RuntimeSetupPanel.vue', import.meta.url)),
      'utf8'
    )
    const backendSource = readFileSync(
      fileURLToPath(new URL('./RuntimeBackendStartPanel.vue', import.meta.url)),
      'utf8'
    )

    expect(pageSource).not.toContain('page-eyebrow')
    expect(pageSource).not.toContain('stageDescriptions')
    expect(pageSource).not.toContain('sidebar-note')
    expect(setupSource).toContain("t('init.page.firstRunEstimate')")
    expect(setupSource).not.toContain("t('init.page.longWaitHint')")
    expect(setupSource).not.toContain('state-eyebrow')
    expect(backendSource).not.toContain('state-eyebrow')
  })
})
