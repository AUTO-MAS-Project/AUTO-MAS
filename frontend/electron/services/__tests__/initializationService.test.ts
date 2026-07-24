import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  requiresBundledRuntimeLock: vi.fn(),
}))

vi.mock('../bundledRuntimePolicy', () => ({
  requiresBundledRuntimeLock: mocks.requiresBundledRuntimeLock,
}))

import { BackendService } from '../backendService'
import { DependencyService } from '../dependencyService'
import { InitializationService } from '../initializationService'
import { PluginBootstrapService } from '../pluginBootstrapService'
import { RepositoryService } from '../repositoryService'

interface FakeBackendOptions {
  running: boolean
  stopSuccess?: boolean
  startSuccess?: boolean
}

function createBackend(calls: string[], options: FakeBackendOptions): BackendService {
  return {
    getStatus: () => ({ isRunning: options.running }),
    stopBackendForRuntimeMutation: async () => {
      calls.push('stop')
      return options.stopSuccess === false
        ? { success: false, wasRunning: options.running, error: 'stop failed' }
        : { success: true, wasRunning: options.running }
    },
    startBackend: async () => {
      calls.push('start')
      return options.startSuccess === false
        ? { success: false, error: 'start failed' }
        : { success: true }
    },
  } as unknown as BackendService
}

describe('InitializationService.updateOnly', () => {
  let calls: string[]
  let service: InitializationService

  beforeEach(() => {
    calls = []
    service = new InitializationService('C:\\AUTO-MAS-test', 'dev_v2')
    const mirrorService = (
      service as unknown as {
        mirrorService: { initialize: () => Promise<void>; initializeLocal: () => void }
      }
    ).mirrorService
    mirrorService.initialize = async () => {
      calls.push('mirror')
    }
    mirrorService.initializeLocal = () => {
      calls.push('mirror-local')
    }
    mocks.requiresBundledRuntimeLock.mockReset()
    mocks.requiresBundledRuntimeLock.mockReturnValue(false)

    vi.spyOn(RepositoryService.prototype, 'pullRepository').mockImplementation(async () => {
      calls.push('repository')
      return { success: true }
    })
    vi.spyOn(DependencyService.prototype, 'installDependencies').mockImplementation(async () => {
      calls.push('dependency')
      return { success: true }
    })
    vi.spyOn(PluginBootstrapService.prototype, 'installPackages').mockImplementation(async () => {
      calls.push('plugin-bootstrap')
      return {
        success: true,
        installedPackages: [],
        failedPackages: [],
        warnings: [],
        summary: 'ok',
      }
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('stops a tracked backend before replacing source and starts it after bootstrap', async () => {
    service.setBackendService(createBackend(calls, { running: true }))

    const result = await service.updateOnly()

    expect(result.success).toBe(true)
    expect(calls).toEqual([
      'mirror',
      'stop',
      'repository',
      'dependency',
      'plugin-bootstrap',
      'start',
    ])
    expect(result.completedStages).toEqual([
      'backend-stop',
      'repository',
      'dependency',
      'plugin-bootstrap',
      'backend',
    ])
  })

  it('restores the backend after a repository-stage failure', async () => {
    service.setBackendService(createBackend(calls, { running: true }))
    vi.spyOn(RepositoryService.prototype, 'pullRepository').mockImplementation(async () => {
      calls.push('repository')
      return { success: false, error: 'repository failed' }
    })

    const result = await service.updateOnly()

    expect(result.success).toBe(false)
    expect(result.failedStage).toBe('repository')
    expect(result.error).toBe('repository failed')
    expect(calls).toEqual(['mirror', 'stop', 'repository', 'start'])
  })

  it('reports both the update error and a failed backend restore', async () => {
    service.setBackendService(createBackend(calls, { running: true, startSuccess: false }))
    vi.spyOn(RepositoryService.prototype, 'pullRepository').mockImplementation(async () => {
      calls.push('repository')
      return { success: false, error: 'repository failed' }
    })

    const result = await service.updateOnly()

    expect(result.success).toBe(false)
    expect(result.failedStage).toBe('repository')
    expect(result.error).toContain('repository failed')
    expect(result.error).toContain('后端恢复失败: start failed')
    expect(calls).toEqual(['mirror', 'stop', 'repository', 'start'])
  })

  it('keeps the backend stopped when a stage fails after repository deployment', async () => {
    service.setBackendService(createBackend(calls, { running: true }))
    vi.spyOn(DependencyService.prototype, 'installDependencies').mockImplementation(async () => {
      calls.push('dependency')
      return { success: false, error: 'dependency failed' }
    })

    const result = await service.updateOnly()

    expect(result.success).toBe(false)
    expect(result.failedStage).toBe('dependency')
    expect(result.error).toContain('dependency failed')
    expect(result.error).toContain('后端已保持停止，必须完成修复后再启动')
    expect(calls).toEqual(['mirror', 'stop', 'repository', 'dependency'])
  })

  it('does not stop or start a backend that was not running', async () => {
    service.setBackendService(createBackend(calls, { running: false }))

    const result = await service.updateOnly()

    expect(result.success).toBe(true)
    expect(calls).toEqual(['mirror', 'stop', 'repository', 'dependency', 'plugin-bootstrap'])
  })

  it('uses local mirrors for a bundled-runtime update', async () => {
    mocks.requiresBundledRuntimeLock.mockReturnValue(true)
    service.setBackendService(createBackend(calls, { running: false }))

    const result = await service.updateOnly()

    expect(result.success).toBe(true)
    expect(calls).toEqual(['mirror-local', 'stop', 'repository', 'dependency', 'plugin-bootstrap'])
  })
})
