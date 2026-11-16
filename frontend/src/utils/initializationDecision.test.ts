import { describe, expect, it, vi } from 'vite-plus/test'
import { decideFailureActions, getInitializationDecision } from './initializationDecision'

vi.mock('@/utils/environment', () => ({ managesBackendProcess: () => true }))
vi.mock('@/utils/analytics', () => ({ beginAnalyticsOperation: () => ({ finish: vi.fn() }) }))

it.each(['running', 'ready', 'failed'] as const)(
  'routes saved startup %s to its reachable recovery page',
  async state => {
    vi.stubGlobal('sessionStorage', { getItem: () => null })
    vi.stubGlobal('window', {
      electronAPI: {
        getLogger: () => ({ info: vi.fn(), warn: vi.fn() }),
        desktopStartupStatus: async () => ({
          runtimeMode: 'managed',
          flowKind: 'startup',
          fullInitialization: false,
          state,
          progress: [],
        }),
      },
    })
    try {
      expect((await getInitializationDecision()).mode).toBe(
        state === 'failed' ? 'full-init' : 'skip-home'
      )
    } finally {
      vi.unstubAllGlobals()
    }
  }
)

describe('Runtime 自动选源后的恢复入口', () => {
  it.each(['managed', 'development'] as const)(
    'only managed mode can reinstall a missing Runtime: %s',
    runtimeMode => {
      const plan = decideFailureActions({
        code: 'RUNTIME_NOT_FOUND',
        retryable: false,
        remediation: ['update-desktop', 'contact-support'],
        runtimeMode,
      })
      expect(plan.actions.map(action => action.kind)).toEqual(
        runtimeMode === 'managed' ? ['retry', 'open-log'] : ['open-log']
      )
    }
  )

  it('所有源失败时提供自动重试和日志，不再要求选择源', () => {
    const plan = decideFailureActions({
      code: 'MIRROR_EXHAUSTED',
      retryable: true,
      remediation: ['retry-other-mirror', 'retry'],
      stage: 'dependency',
      runtimeMode: 'managed',
    })
    expect(plan.actions.map(action => action.kind)).toEqual(['retry', 'open-log'])
  })

  it.each([
    {
      code: 'INTERNAL_ERROR',
      retryable: false,
      remediation: ['retry-other-mirror'],
      stage: 'python',
      runtimeMode: 'managed' as const,
    },
    { retryable: false },
  ])('不可重试结果 %# 不提供重试入口', context => {
    const plan = decideFailureActions(context)
    expect(plan.actions.map(action => action.kind)).toEqual(['open-log'])
  })

  it('源码损坏仍提供完整恢复，依赖重建仍保持独立', () => {
    expect(
      decideFailureActions({
        code: 'LOCKFILE_INVALID',
        runtimeMode: 'managed',
        retryable: false,
      }).actions.map(action => action.kind)
    ).toEqual(['restore-workspace', 'open-log'])
    expect(
      decideFailureActions({
        code: 'DEPENDENCY_SYNC_FAILED',
        retryable: true,
        remediation: ['retry-sync', 'rebuild-environment'],
        stage: 'dependency',
        runtimeMode: 'managed',
      }).actions.map(action => action.kind)
    ).toEqual(['retry', 'rebuild-environment', 'open-log'])
  })
})
