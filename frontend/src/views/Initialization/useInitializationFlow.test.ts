import { i18n } from '@/i18n'
import { renderToString } from '@vue/server-renderer'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { createSSRApp, defineComponent } from 'vue'
import { useInitializationFlow } from './useInitializationFlow'

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
vi.mock('@/utils/analytics', () => ({
  beginAnalyticsOperation: () => ({ finish: vi.fn() }),
  beginInitializationAnalytics: () => ({ finish: vi.fn() }),
}))
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

describe('managed recovery routing', () => {
  describe.each(['dependency-restore', 'missing-runtime'] as const)('%s', scenario => {
    it('shows the actual failed stage when dependency recovery has to restore program files', async () => {
      const api = window.electronAPI
      if (scenario === 'missing-runtime') {
        api.desktopStartupStatus = async () => ({
          runtimeMode: 'managed',
          flowKind: 'startup',
          fullInitialization: false,
          state: 'failed',
          progress: [],
        })
        api.waitDesktopStartup = async () => ({
          success: false,
          failedStage: 'backend',
          error: 'Runtime executable is missing',
          code: 'RUNTIME_NOT_FOUND',
          retryable: false,
          remediation: ['update-desktop', 'contact-support'],
        })
        const bootstrap = vi
          .fn()
          .mockResolvedValueOnce({
            success: false,
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
        api.initialize = bootstrap
        api.installPython = vi.fn()
        api.pullRepository = vi.fn()
        api.installDependencies = vi.fn()

        await initialize()
        expect(flow.failureProps.value.failureActions).toContainEqual(
          expect.objectContaining({ kind: 'retry' })
        )
        expect(bootstrap).not.toHaveBeenCalled()
        await flow.handleFailureAction('retry')
        expect(flow.hasFailed.value).toBe(true)
        expect(flow.currentStep.value.key).toBe('python')
        expect(flow.failureProps.value.message).toBe('Download interrupted')
        expect(flow.failureProps.value.failureActions).toContainEqual(
          expect.objectContaining({ kind: 'retry' })
        )

        await flow.handleFailureAction('retry')
        expect(bootstrap.mock.calls).toEqual([
          [expect.any(String), false],
          [expect.any(String), false],
        ])
        expect(api.installPython).not.toHaveBeenCalled()
        expect(api.pullRepository).not.toHaveBeenCalled()
        expect(api.installDependencies).not.toHaveBeenCalled()
        expect(flow.isBackendStep.value).toBe(true)
        expect(flow.hasFailed.value).toBe(false)
        return
      }

      await initialize()
      receive({ stage: 'dependency', status: 'failed', message: 'lockfile missing' })
      api.installDependencies = vi.fn(async () => ({
        success: false,
        failedStage: 'repository',
        error: 'Program files could not be restored',
        logs: 'git: program files unavailable',
        code: 'WORKSPACE_RESTORE_FAILED',
        retryable: false,
      }))
      await flow.handleFailureAction('retry')
      expect(flow.currentStep.value.key).toBe('repository')
      expect(flow.failureProps.value.failureActions.map(action => action.kind)).toEqual([
        'restore-workspace',
        'open-log',
      ])
      expect(flow.hasFailed.value).toBe(true)
      expect(flow.failureProps.value.message).toBe('Program files could not be restored')
      expect(flow.failureProps.value.failureLogs).toBe('git: program files unavailable')
      api.initialize = vi.fn().mockResolvedValueOnce({
        success: false,
        failedStage: 'repository',
        error: 'fatal: original restore error',
        logs: 'stderr: original restore output',
        code: 'GIT_CLONE_FAILED',
        retryable: true,
      })
      await flow.handleFailureAction('restore-workspace')
      expect(flow.currentStep.value.key).toBe('repository')
      expect(flow.hasFailed.value).toBe(true)
      expect(flow.failureProps.value.message).toBe('fatal: original restore error')
      expect(flow.failureProps.value.failureLogs).toBe('stderr: original restore output')
    })
  })
})
