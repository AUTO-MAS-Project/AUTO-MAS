import { i18n } from '@/i18n'
import { renderToString } from '@vue/server-renderer'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { createSSRApp, defineComponent } from 'vue'
import { useInitializationFlow } from './useInitializationFlow'
import { useRuntimeBinaryUpdate } from './useRuntimeBinaryUpdate'

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
        return () => null
      },
    })
  )
  app.use(i18n)
  await renderToString(app)
  for (const callback of lifecycle.mounted) await callback()
}
beforeEach(() => {
  vi.useFakeTimers()
  lifecycle.mounted.length = 0
  vi.stubGlobal('sessionStorage', { getItem: () => null })
  vi.stubGlobal('window', {
    electronAPI: {
      getLogger: () => logger,
      getRuntimeInitContext: async () => ({ mode: 'managed' }),
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

describe('initialization recovery', () => {
  it('preserves original failure details when restoring the workspace', async () => {
    await initialize()
    window.electronAPI.initialize = vi.fn().mockResolvedValue({
      success: false,
      failedStage: 'repository',
      error: 'fatal: 原始错误',
      logs: 'stderr: 原始输出',
      code: 'GIT_CLONE_FAILED',
      retryable: true,
    })
    await flow.handleFailureAction('restore-workspace')
    expect(flow.hasFailed.value).toBe(true)
    expect(flow.currentStep.value.key).toBe('repository')
    expect(flow.failureProps.value.message).toBe('fatal: 原始错误')
    expect(flow.failureProps.value.failureLogs).toBe('stderr: 原始输出')
  })

  it.each(['failed', 'cancelled'] as const)(
    'keeps %s recovery and a subsequent retry compatible',
    async status => {
      let update!: ReturnType<typeof useRuntimeBinaryUpdate>
      let finish!: (value: unknown) => void
      const onUpdated = vi.fn()
      const remove = vi.fn()
      Object.assign(window.electronAPI, {
        checkRuntimeBinaryUpdate: async () => ({
          status: 'available',
          target: { version: 'v0.1.99' },
        }),
        onRuntimeBinaryProgress: vi.fn(),
        removeRuntimeBinaryProgressListener: remove,
        updateRuntimeBinary: () =>
          new Promise(resolve => {
            finish = resolve
          }),
      })
      const app = createSSRApp({
        setup() {
          update = useRuntimeBinaryUpdate(onUpdated)
          return () => null
        },
      })
      app.use(i18n)
      await renderToString(app)
      await update.checkForUpdate()
      const first = update.updateRuntime()
      expect(update.updating.value).toBe(true)
      finish({ status, error: 'HTTP 503: original error' })
      await first
      expect(update.updating.value).toBe(false)
      expect(onUpdated).not.toHaveBeenCalled()
      expect(remove).toHaveBeenCalledTimes(1)
      if (status === 'failed')
        expect(logger.error).toHaveBeenCalledWith('更新 Runtime 失败: HTTP 503: original error')
      const retry = update.updateRuntime()
      expect(update.updating.value).toBe(true)
      finish({ status: 'cancelled' })
      await retry
      expect(update.updating.value).toBe(false)
      expect(remove).toHaveBeenCalledTimes(2)
      expect(onUpdated).not.toHaveBeenCalled()
    }
  )
})

describe('main-process startup progress', () => {
  it.each(['event', 'snapshot'] as const)(
    'switches to backend startup before completion from %s progress',
    async source => {
      const backendProgress = {
        stage: 'backend',
        status: 'started' as const,
        stageIndex: 7,
        totalStages: 7,
        progress: 0,
        message: '正在启动后端服务...',
      }
      let finishStartup!: (result: { success: boolean }) => void
      const startup = new Promise<{ success: boolean }>(resolve => {
        finishStartup = resolve
      })
      let waiting!: () => void
      const joined = new Promise<void>(resolve => {
        waiting = resolve
      })
      const api = window.electronAPI
      api.desktopStartupStatus = async () => ({
        runtimeMode: 'managed',
        flowKind: 'update',
        fullInitialization: true,
        state: 'running',
        progress: [
          {
            stage: 'dependency',
            stageIndex: 6,
            totalStages: 7,
            progress: 100,
            status: 'completed',
            message: '运行环境准备完成',
          },
          ...(source === 'snapshot' ? [backendProgress] : []),
        ],
      })
      api.waitDesktopStartup = () => {
        waiting()
        return startup
      }

      const mounting = initialize()
      await joined
      try {
        if (source === 'event') receive(backendProgress)
        expect(flow.isBackendStep.value).toBe(true)
        expect(flow.hasFailed.value).toBe(false)
      } finally {
        finishStartup({ success: true })
        await mounting
      }
    }
  )
})

describe('managed recovery routing', () => {
  it.each(['startup', 'backend'] as const)(
    'reinstalls a missing Runtime after a failure from %s, keeping failed downloads retryable',
    async origin => {
      const missing = {
        success: false,
        failedStage: 'backend',
        error: 'Runtime executable is missing',
        code: 'RUNTIME_NOT_FOUND',
        retryable: false,
        remediation: ['update-desktop', 'contact-support'],
      }
      const api = window.electronAPI
      api.desktopStartupStatus = async () => ({
        runtimeMode: 'managed',
        flowKind: 'startup',
        fullInitialization: false,
        state: origin === 'startup' ? 'failed' : 'ready',
        progress: [],
      })
      api.waitDesktopStartup = async () => (origin === 'startup' ? missing : { success: true })
      api.initialize = vi
        .fn()
        .mockResolvedValueOnce({
          success: false,
          completedStages: [],
          failedStage: 'python',
          failureOrigin: 'runtime_binary',
          code: 'RUNTIME_BINARY_ALIGN_ERROR',
          retryable: true,
          remediation: ['retry', 'open-log'],
          error: 'Download interrupted',
        })
        .mockResolvedValueOnce({
          success: true,
          completedStages: ['python', 'repository', 'dependency'],
        })
      await initialize()
      if (origin === 'backend') await flow.handleBackendError(missing.error, missing)
      expect(flow.currentStep.value.key).toBe('python')
      expect(flow.flowKind.value).toBe('startup')
      expect(flow.failureProps.value.failureActions.map(action => action.kind)).toEqual([
        'retry',
        'open-log',
      ])
      expect(api.initialize).not.toHaveBeenCalled()
      await flow.handleFailureAction('retry')
      expect(flow.flowKind.value).toBe('update')
      expect(flow.currentStep.value.key).toBe('python')
      expect(flow.hasFailed.value).toBe(true)
      expect(flow.failureProps.value.message).toBe('Download interrupted')
      expect(flow.failureProps.value.failureActions.map(action => action.kind)).toEqual([
        'retry',
        'open-log',
      ])
      await flow.handleFailureAction('retry')
      expect(api.initialize).toHaveBeenCalledTimes(2)
      expect(flow.currentStep.value.key).toBe('backend')
      expect(flow.hasFailed.value).toBe(false)
    }
  )

  it('does not offer managed Runtime installation in development mode', async () => {
    window.electronAPI.getRuntimeInitContext = async () => ({
      mode: 'development',
      fallbackLogPath: '',
    })
    await initialize()
    await flow.handleBackendError('Runtime executable is missing', {
      code: 'RUNTIME_NOT_FOUND',
      retryable: false,
    })
    expect(flow.currentStep.value.key).toBe('backend')
    expect(flow.flowKind.value).toBe('startup')
  })

  it('retries the environment through full initialization without repeating completed stages', async () => {
    await initialize()
    receive({ stage: 'python', status: 'failed', message: 'download interrupted' })
    const api = window.electronAPI
    api.initialize = vi.fn(async () => ({ success: true, completedStages: [] }))
    api.installPython = vi.fn(async () => ({ success: true }))
    api.pullRepository = vi.fn(async () => ({ success: true }))
    api.installDependencies = vi.fn(async () => ({ success: true }))
    await flow.handleFailureAction('retry')
    expect(api.initialize).toHaveBeenCalledOnce()
    expect(api.installPython).not.toHaveBeenCalled()
    expect(api.pullRepository).not.toHaveBeenCalled()
    expect(api.installDependencies).not.toHaveBeenCalled()
    expect(flow.currentStep.value.key).toBe('backend')
  })

  it('shows the actual failed stage when dependency recovery has to restore program files', async () => {
    await initialize()
    receive({ stage: 'dependency', status: 'failed', message: 'lockfile missing' })
    window.electronAPI.installDependencies = vi.fn(async () => ({
      success: false,
      failedStage: 'repository',
      error: 'Program files could not be restored',
      code: 'WORKSPACE_RESTORE_FAILED',
      retryable: false,
    }))
    await flow.handleFailureAction('retry')
    expect(flow.currentStep.value.key).toBe('repository')
    expect(flow.failureProps.value.failureActions.map(action => action.kind)).toEqual([
      'restore-workspace',
      'open-log',
    ])
  })
})
