import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { createSSRApp, defineComponent, h, nextTick } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { i18n } from '@/i18n'
import LaunchStatus from '@/components/LaunchStatus.vue'
import { useInitializationFlow } from './useInitializationFlow'
import { useRuntimeBinaryUpdate } from './useRuntimeBinaryUpdate'
import { formatRuntimeProgress } from './runtimeProgress'
import type { RuntimeBinaryProgress } from '@/types/electron'
import { RUNTIME_STAGES } from '../../../electron/services/runtime/protocol'

const lifecycle = vi.hoisted(() => ({ mounted: [] as Array<() => unknown> }))
vi.mock('vue', async importOriginal => ({
  ...(await importOriginal<typeof import('vue')>()),
  onMounted: (callback: () => unknown) => lifecycle.mounted.push(callback),
  onUnmounted: vi.fn(),
}))
vi.mock('ant-design-vue', () => ({
  message: { error: vi.fn(), warning: vi.fn(), success: vi.fn() },
}))
vi.mock('@/utils/environment', () => ({
  isDevelopmentEnvironment: false,
  isBrowserDevelopment: () => false,
  managesBackendProcess: () => true,
}))
vi.mock('@/utils/analytics', () => ({ beginAnalyticsOperation: () => ({ finish: vi.fn() }) }))
vi.mock('./finishInitializationEntry', () => ({ finishInitializationEntry: vi.fn() }))
vi.mock('@/composables/useVersionService', () => ({ getBackendVersion: vi.fn() }))

type Payload = Record<string, unknown>
let receive: (payload: Payload) => void
let flow: ReturnType<typeof useInitializationFlow>
const logger = { info: vi.fn(), warn: vi.fn(), error: vi.fn() }

async function initialize() {
  const app = createSSRApp(
    defineComponent({
      setup() {
        flow = useInitializationFlow()
        return () =>
          h(LaunchStatus, {
            title: flow.statusTitle.value,
            details: flow.statusDetails.value,
            progress: flow.statusProgress.value,
            steps: flow.launchSteps.value,
          })
      },
    })
  )
  app.use(i18n)
  await renderToString(app)
  for (const callback of lifecycle.mounted) await callback()
}
const render = () =>
  renderToString(
    createSSRApp({
      render: () =>
        h(LaunchStatus, {
          title: flow.statusTitle.value,
          details: flow.statusDetails.value,
          progress: flow.statusProgress.value,
          steps: flow.launchSteps.value,
        }),
    })
  )

beforeEach(() => {
  vi.useFakeTimers()
  lifecycle.mounted.length = 0
  vi.stubGlobal('sessionStorage', { getItem: () => null })
  vi.stubGlobal('window', {
    electronAPI: {
      getLogger: () => logger,
      getRuntimeInitContext: async () => ({ mode: 'managed' }),
      initMirrors: async () => {},
      getMirrors: async () => [],
      loadConfig: async () => ({}),
      getInitializedVersion: async () => '',
      onInitializationProgress: (callback: typeof receive) => {
        receive = callback
      },
    },
  })
  i18n.global.locale.value = 'zh-CN'
})
afterEach(() => {
  vi.clearAllTimers()
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

// Real IPC handler → flow state/computed → real LaunchStatus HTML, without a Runtime process.
describe('initialization progress language switching', () => {
  it('re-renders the same received repository event in Chinese, English and Japanese', async () => {
    await initialize()
    receive({
      stage: 'repository',
      status: 'running',
      progress: 42,
      runtimeStage: 'workspace.clone',
      runtimeStatus: 'running',
      message: '正在接收后端仓库数据',
    })
    for (const [locale, title] of [
      ['zh-CN', '正在接收后端仓库数据'],
      ['en-US', 'Receiving backend repository data'],
      ['ja-JP', 'バックエンドリポジトリのデータを受信中'],
    ] as const) {
      i18n.global.locale.value = locale
      await nextTick()
      expect(await render()).toContain(title)
      expect(flow.statusProgress.value).toBe(42)
    }
    expect(logger.info).toHaveBeenCalledWith('[repository] 正在接收后端仓库数据')
  })

  it('keeps the reported source order and transfer state while switching languages', async () => {
    await initialize()
    receive({
      stage: 'python',
      status: 'running',
      runtimeStage: 'network.probe',
      runtimeStatus: 'running',
      source: 'github',
      bytesPerSecond: 0,
    })
    receive({
      stage: 'python',
      status: 'running',
      runtimeStage: 'network.probe',
      runtimeStatus: 'running',
      source: 'cnb',
    })
    receive({
      stage: 'python',
      status: 'running',
      runtimeStage: 'network.probe',
      runtimeStatus: 'succeeded',
      message: 'git 源顺序：cnb → github',
    })
    for (const [locale, order, unavailable] of [
      ['zh-CN', 'git 源顺序：cnb → github', 'github 不可用'],
      ['en-US', 'git source order: cnb → github', 'github unavailable'],
      ['ja-JP', 'git ソースの順序：cnb → github', 'github は利用できません'],
    ] as const) {
      i18n.global.locale.value = locale
      const html = await render()
      expect(html).toContain(order)
      expect(html).toContain(unavailable)
    }
    receive({
      stage: 'python',
      status: 'running',
      runtimeStage: 'uv.download',
      runtimeStatus: 'running',
      message: '下载中',
      item: 'uv.zip',
      source: 'cnb',
      current: 1024,
      total: 2048,
      bytesPerSecond: 1024,
    })
    for (const locale of ['zh-CN', 'en-US', 'ja-JP'] as const) {
      i18n.global.locale.value = locale
      expect(await render()).toContain('uv.zip')
      expect(flow.statusDetails.value?.[1]).toContain('1 KB / 2 KB')
      expect(flow.statusDetails.value?.[1]).toContain('cnb')
    }
  })

  it('preserves legacy, unknown, diagnostic and failed messages verbatim', async () => {
    await initialize()
    for (const payload of [
      { message: '旧 Runtime 原始消息' },
      { runtimeStage: 'future.stage', runtimeStatus: 'running', message: '未知阶段' },
      { runtimeStage: 'workspace.clone', runtimeStatus: 'future-status', message: '未知状态' },
      { runtimeStage: 'workspace.clone', runtimeStatus: 'failed', message: '原始 git 错误' },
    ]) {
      receive({ stage: 'repository', status: 'running', ...payload })
      for (const locale of ['zh-CN', 'en-US', 'ja-JP'] as const) {
        i18n.global.locale.value = locale
        expect(await render()).toContain(payload.message)
      }
    }
    receive({
      stage: 'repository',
      status: 'running',
      runtimeStage: 'network.probe',
      runtimeStatus: 'succeeded',
      message: '无法识别的源摘要',
    })
    expect(flow.statusDetails.value).toContain('无法识别的源摘要')
    receive({ stage: 'repository', status: 'failed', message: 'fatal: 原始异常' })
    expect(flow.failureProps.value.message).toBe('fatal: 原始异常')
    expect(flow.hasFailed.value).toBe(true)
    receive({ stage: 'repository', status: 'failed' })
    for (const locale of ['zh-CN', 'en-US', 'ja-JP'] as const) {
      i18n.global.locale.value = locale
      expect(flow.failureProps.value.message).toBe(i18n.global.t('bootstrap.init.msg.execFailed'))
    }
  })

  it('keeps recovery prompts reactive and preserves original failure logs', async () => {
    await initialize()
    let finish!: (value: unknown) => void
    window.electronAPI.initialize = vi.fn(
      () =>
        new Promise(resolve => {
          finish = resolve
        })
    ) as typeof window.electronAPI.initialize
    const recovering = flow.handleFailureAction('restore-workspace')
    for (const locale of ['zh-CN', 'en-US', 'ja-JP'] as const) {
      i18n.global.locale.value = locale
      expect(await render()).toContain(i18n.global.t('bootstrap.init.failure.restoringWorkspace'))
    }
    finish({
      success: false,
      failedStage: 'repository',
      error: 'fatal: 原始错误',
      logs: 'stderr: 原始输出',
      code: 'GIT_CLONE_FAILED',
      retryable: true,
    })
    await recovering
    for (const locale of ['zh-CN', 'en-US', 'ja-JP'] as const) {
      i18n.global.locale.value = locale
      expect(flow.failureProps.value.message).toBe('fatal: 原始错误')
      expect(flow.failureProps.value.failureLogs).toBe('stderr: 原始输出')
      expect(flow.failureProps.value.title).toBe(i18n.global.t('bootstrap.init.steps.repository'))
    }
    const restarting = flow.handleRuntimeUpdated()
    await Promise.resolve()
    await Promise.resolve()
    for (const locale of ['zh-CN', 'en-US', 'ja-JP'] as const) {
      i18n.global.locale.value = locale
      expect(await render()).toContain(i18n.global.t('bootstrap.init.failure.runtimeRestarting'))
    }
    finish({ success: false, error: 'test failure' })
    await restarting
  })

  it('updates recovery download text reactively and preserves legacy update events', async () => {
    let update!: ReturnType<typeof useRuntimeBinaryUpdate>
    let progress!: (value: RuntimeBinaryProgress) => void
    let finish!: (value: unknown) => void
    Object.assign(window.electronAPI, {
      checkRuntimeBinaryUpdate: async () => ({
        status: 'available',
        target: { version: 'v0.1.99' },
      }),
      onRuntimeBinaryProgress: (callback: typeof progress) => {
        progress = callback
      },
      removeRuntimeBinaryProgressListener: vi.fn(),
      updateRuntimeBinary: () =>
        new Promise(resolve => {
          finish = resolve
        }),
    })
    const app = createSSRApp({
      setup() {
        update = useRuntimeBinaryUpdate(vi.fn())
        return () => h('p', update.updateMessage.value)
      },
    })
    app.use(i18n)
    await renderToString(app)
    await update.checkForUpdate()
    const pending = update.updateRuntime()
    const event = {
      progress: 20,
      phase: 'download' as const,
      message: '正在从 CNB（1/5）下载 Runtime v0.1.99',
      targetVersion: 'v0.1.99',
      source: 'cnb',
      sourceName: 'CNB',
      sourceIndex: 1,
      sourceCount: 5,
    }
    progress(event)
    for (const [locale, text] of [
      ['zh-CN', '正在从 CNB（1/5）下载 Runtime v0.1.99'],
      ['en-US', 'Downloading Runtime v0.1.99 from CNB (1/5)'],
      ['ja-JP', 'CNB（1/5）から Runtime v0.1.99 をダウンロード中'],
    ] as const) {
      i18n.global.locale.value = locale
      expect(update.updateMessage.value).toBe(text)
      expect(
        await renderToString(createSSRApp({ render: () => h('p', update.updateMessage.value) }))
      ).toContain(text)
      expect(update.updateProgress.value).toBe(20)
    }
    progress({
      ...event,
      source: 'github',
      sourceName: 'GitHub 官方',
      sourceIndex: 5,
      message: '正在从 GitHub 官方（5/5）下载 Runtime v0.1.99',
    })
    for (const [locale, source] of [
      ['zh-CN', 'GitHub 官方'],
      ['en-US', 'GitHub (official)'],
      ['ja-JP', 'GitHub 公式'],
    ] as const) {
      i18n.global.locale.value = locale
      expect(update.updateMessage.value).toContain(source)
      expect(update.updateMessage.value).toContain('5/5')
      expect(update.updateMessage.value).toContain('v0.1.99')
    }
    for (const incomplete of [
      { progress: 30, phase: 'download' as const, message: '旧事件仅有阶段' },
      { ...event, sourceCount: undefined, message: '旧事件没有总源数' },
    ]) {
      progress(incomplete)
      expect(update.updateMessage.value).toBe(incomplete.message)
    }
    progress({ progress: 30, message: '旧更新器原文' })
    expect(update.updateMessage.value).toBe('旧更新器原文')
    finish({ status: 'skipped' })
    await pending
    for (const locale of ['zh-CN', 'en-US', 'ja-JP'] as const) {
      i18n.global.locale.value = locale
      expect(update.updateMessage.value).toBe(
        i18n.global.t('bootstrap.init.failure.runtimeUpdateSkipped')
      )
    }
    expect(logger.info).toHaveBeenCalledWith(event.message)
    expect(logger.info).toHaveBeenCalledWith('正在从 GitHub 官方（5/5）下载 Runtime v0.1.99')
  })

  it.each(['failed', 'cancelled'] as const)(
    'keeps %s recovery and a subsequent retry compatible',
    async status => {
      let update!: ReturnType<typeof useRuntimeBinaryUpdate>
      let progress!: (value: RuntimeBinaryProgress) => void
      let finish!: (value: unknown) => void
      const onUpdated = vi.fn()
      const remove = vi.fn()
      Object.assign(window.electronAPI, {
        checkRuntimeBinaryUpdate: async () => ({
          status: 'available',
          target: { version: 'v0.1.99' },
        }),
        onRuntimeBinaryProgress: (callback: typeof progress) => {
          progress = callback
        },
        removeRuntimeBinaryProgressListener: remove,
        updateRuntimeBinary: () =>
          new Promise(resolve => {
            finish = resolve
          }),
      })
      const app = createSSRApp({
        setup() {
          update = useRuntimeBinaryUpdate(onUpdated)
          return () => h('p', update.updateMessage.value)
        },
      })
      app.use(i18n)
      await renderToString(app)
      await update.checkForUpdate()
      const first = update.updateRuntime()
      const event: RuntimeBinaryProgress = {
        phase: 'download',
        progress: 50,
        message: '完整下载日志',
        targetVersion: 'v0.1.99',
        source: 'cnb',
        sourceName: 'CNB',
        sourceIndex: 1,
        sourceCount: 5,
      }
      progress(event)
      finish({ status, error: 'HTTP 503: original error' })
      await first
      expect(update.updating.value).toBe(false)
      expect(onUpdated).not.toHaveBeenCalled()
      expect(remove).toHaveBeenCalledTimes(1)
      for (const locale of ['zh-CN', 'en-US', 'ja-JP'] as const) {
        i18n.global.locale.value = locale
        if (status === 'failed')
          expect(update.updateMessage.value).toContain('HTTP 503: original error')
        else
          expect(update.updateMessage.value).toBe(
            i18n.global.t('bootstrap.init.failure.runtimeUpdateSkipped')
          )
      }
      const retry = update.updateRuntime()
      expect(update.updateMessage.value).toBe(
        i18n.global.t('bootstrap.init.failure.runtimeUpdating')
      )
      progress({
        ...event,
        source: 'ghproxy_cloudflare',
        sourceName: 'gh-proxy (Cloudflare)',
        sourceIndex: 2,
      })
      expect(update.updateMessage.value).toContain('gh-proxy (Cloudflare)')
      expect(update.updateMessage.value).toContain('2/5')
      finish({ status: 'cancelled' })
      await retry
      expect(remove).toHaveBeenCalledTimes(2)
      expect(logger.info).toHaveBeenCalledWith(event.message)
      if (status === 'failed')
        expect(logger.error).toHaveBeenCalledWith('更新 Runtime 失败: HTTP 503: original error')
    }
  )

  it('localizes the reachable top-level states and keeps unrelated protocol stages raw', async () => {
    await initialize()
    for (const [stage, status, raw, texts] of [
      [
        'repair',
        'preparing_uv',
        '正在检查并修复运行环境',
        [
          '正在检查并修复运行环境',
          'Checking and repairing the runtime environment',
          '実行環境を確認・修復中',
        ],
      ],
      [
        'bootstrap',
        'ready_to_start',
        '当前运行环境已就绪',
        ['当前运行环境已就绪', 'The runtime environment is ready', '実行環境の準備が完了しました'],
      ],
    ] as const) {
      receive({
        stage: 'python',
        status: 'running',
        runtimeStage: stage,
        runtimeStatus: status,
        message: raw,
      })
      for (const [index, locale] of (['zh-CN', 'en-US', 'ja-JP'] as const).entries()) {
        i18n.global.locale.value = locale
        expect(await render()).toContain(texts[index])
      }
    }
    for (const stage of [
      'cleanup',
      'doctor',
      'runtime.handshake',
      'backend.spawn',
      'future.stage',
    ]) {
      receive({
        stage: 'python',
        status: 'running',
        runtimeStage: stage,
        runtimeStatus: 'running',
        message: '原始诊断',
      })
      expect(await render()).toContain('原始诊断')
    }
    for (const stage of ['bootstrap', 'repair']) {
      for (const status of ['failed', 'cancelled', 'future']) {
        expect(
          formatRuntimeProgress({ runtimeStage: stage, runtimeStatus: status }, i18n.global.t)
        ).toBeUndefined()
      }
    }
  })

  it('retains download details through the initialization IPC path', async () => {
    await initialize()
    receive({
      stage: 'python',
      status: 'running',
      runtimeStage: 'runtime.download',
      runtimeStatus: 'running',
      message: '原始下载信息',
      targetVersion: 'v0.1.99',
      source: 'cnb',
      sourceName: 'CNB',
      sourceIndex: 2,
      sourceCount: 5,
    })
    for (const locale of ['zh-CN', 'en-US', 'ja-JP'] as const) {
      i18n.global.locale.value = locale
      const html = await render()
      expect(html).toContain('CNB')
      expect(html).toContain('2/5')
      expect(html).toContain('v0.1.99')
    }
  })

  it('localizes known normal statuses while leaving failures and unknown events untouched', () => {
    const normalStages = [
      'runtime.check',
      'runtime.download',
      'network.probe',
      'uv.check',
      'uv.download',
      'uv.verify',
      'workspace.check',
      'workspace.clone',
      'workspace.verify',
      'workspace.swap',
      'workspace.cleanup',
      'python.check',
      'python.install',
      'dependencies.check',
      'dependencies.sync',
      'dependencies.rebuild',
    ]
    // Every protocol stage is deliberately classified; new ones require a display-path review.
    const otherPaths = [
      'runtime.handshake',
      'doctor',
      'cleanup',
      'backend.spawn',
      'backend.health',
      'backend.run',
      'backend.restart',
      'backend.shutdown',
      'backend.cleanup',
    ]
    expect(
      new Set([
        ...normalStages.filter(stage => !stage.startsWith('runtime.')),
        'bootstrap',
        'repair',
        ...otherPaths,
      ])
    ).toEqual(new Set(RUNTIME_STAGES))
    for (const locale of ['zh-CN', 'en-US', 'ja-JP'] as const) {
      i18n.global.locale.value = locale
      for (const stage of normalStages) {
        const text = formatRuntimeProgress(
          {
            runtimeStage: stage,
            runtimeStatus: 'running',
            targetVersion: 'v0.1.99',
            source: 'cnb',
            sourceName: 'CNB',
            sourceIndex: 1,
            sourceCount: 5,
          },
          i18n.global.t
        )
        for (const [status, key] of [
          ['succeeded', 'finished'],
          ['skipped', 'skipped'],
        ] as const) {
          expect(
            formatRuntimeProgress({ runtimeStage: stage, runtimeStatus: status }, i18n.global.t)
          ).toBe(i18n.global.t(`bootstrap.init.progress.${key}`))
        }
        expect(text).toBeTruthy()
        expect(text).not.toContain('bootstrap.')
        if (locale === 'en-US') expect(text).not.toMatch(/[\u4e00-\u9fff]/)
        for (const status of ['failed', 'cancelled', 'future'])
          expect(
            formatRuntimeProgress({ runtimeStage: stage, runtimeStatus: status }, i18n.global.t)
          ).toBeUndefined()
      }
    }
  })
})
