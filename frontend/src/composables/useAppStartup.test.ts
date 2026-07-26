import { describe, expect, it, beforeEach, vi } from 'vitest'

// 替换 window.electronAPI.getLogger，避免在 node 环境报错
vi.stubGlobal('window', {
  electronAPI: {
    getLogger: () => ({
      info: vi.fn(),
      warn: vi.fn(),
      error: vi.fn(),
      debug: vi.fn(),
    }),
  },
})

// 每次测试前重置模块状态
const loadUseAppStartup = async () => {
  vi.resetModules()
  const mod = await import('./useAppStartup')
  return mod
}

describe('useAppStartup 全局启动状态机', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('初始状态为 initializing，具备安全退出能力', async () => {
    const { useAppStartup } = await loadUseAppStartup()
    const { state } = useAppStartup()

    expect(state.value.status).toBe('initializing')
    expect(state.value.canExit).toBe(true)
    expect(state.value.canRetry).toBe(false)
    expect(state.value.canCopyDiagnostics).toBe(false)
    expect(state.value.canOpenLogs).toBe(false)
  })

  it('启动阶段可显式推进，并在未指定时保持当前阶段', async () => {
    const { useAppStartup } = await loadUseAppStartup()
    const { state, setStatus, beginRetry, reset } = useAppStartup()

    expect(state.value.stage).toBe('renderer')
    setStatus('backend-starting', { stage: 'runtime' })
    expect(state.value.stage).toBe('runtime')
    setStatus('backend-starting')
    expect(state.value.stage).toBe('runtime')
    beginRetry()
    expect(state.value.stage).toBe('connection')
    reset()
    expect(state.value.stage).toBe('renderer')
  })
  it('设置 backend-starting 时保留退出能力', async () => {
    const { useAppStartup } = await loadUseAppStartup()
    const { state, setStatus } = useAppStartup()

    setStatus('backend-starting', { message: '正在启动后端服务...' })
    expect(state.value.status).toBe('backend-starting')
    expect(state.value.canExit).toBe(true)
    expect(state.value.canRetry).toBe(false)
  })

  it('设置 connected 时禁用所有操作按钮', async () => {
    const { useAppStartup } = await loadUseAppStartup()
    const { state, setStatus } = useAppStartup()

    setStatus('connected')
    expect(state.value.status).toBe('connected')
    expect(state.value.canExit).toBe(false)
    expect(state.value.canRetry).toBe(false)
    expect(state.value.canCopyDiagnostics).toBe(false)
    expect(state.value.canOpenLogs).toBe(false)
  })

  it('失败状态同时具备重试、复制诊断、打开日志和安全退出能力', async () => {
    const { useAppStartup } = await loadUseAppStartup()
    const { state, setStatus, isFailure } = useAppStartup()

    const failureStatuses = ['offline', 'timeout', 'failed'] as const
    for (const status of failureStatuses) {
      setStatus(status, { message: '出错了', detail: '具体原因' })
      expect(state.value.status).toBe(status)
      expect(isFailure.value).toBe(true)
      expect(state.value.canRetry).toBe(true)
      expect(state.value.canCopyDiagnostics).toBe(true)
      expect(state.value.canOpenLogs).toBe(true)
      expect(state.value.canExit).toBe(true)
      expect(state.value.detail).toBe('具体原因')
    }
  })

  it('closing 状态禁用所有交互', async () => {
    const { useAppStartup } = await loadUseAppStartup()
    const { state, setStatus } = useAppStartup()

    setStatus('closing', { message: '正在关闭应用...' })
    expect(state.value.status).toBe('closing')
    expect(state.value.canExit).toBe(false)
    expect(state.value.canRetry).toBe(false)
    expect(state.value.canCopyDiagnostics).toBe(false)
    expect(state.value.canOpenLogs).toBe(false)
  })

  it('reset 回到 initializing 状态并递增 generation', async () => {
    const { useAppStartup } = await loadUseAppStartup()
    const { state, setStatus, reset, currentGeneration } = useAppStartup()

    setStatus('failed', { detail: 'xxx' })
    const genBefore = currentGeneration.value
    reset()
    expect(state.value.status).toBe('initializing')
    expect(state.value.detail).toBeUndefined()
    expect(state.value.canRetry).toBe(false)
    expect(currentGeneration.value).toBe(genBefore + 1)
  })

  it('beginRetry 进入 reconnecting 并递增 generation 与 retryCount', async () => {
    const { useAppStartup } = await loadUseAppStartup()
    const { state, beginRetry, currentGeneration, retryCount } = useAppStartup()

    const genBefore = currentGeneration.value
    const retryBefore = retryCount.value
    beginRetry()

    expect(state.value.status).toBe('reconnecting')
    expect(state.value.message).toBe('正在重新连接后端...')
    expect(state.value.canRetry).toBe(false)
    expect(state.value.canExit).toBe(true)
    expect(currentGeneration.value).toBe(genBefore + 1)
    expect(retryCount.value).toBe(retryBefore + 1)
  })

  it('连续 beginRetry 递增 generation 与 retryCount，旧 generation 不再匹配当前状态', async () => {
    const { useAppStartup } = await loadUseAppStartup()
    const { beginRetry, currentGeneration, retryCount } = useAppStartup()

    beginRetry()
    const gen1 = currentGeneration.value
    beginRetry()
    const gen2 = currentGeneration.value

    expect(gen2).toBe(gen1 + 1)
    expect(retryCount.value).toBe(2)
  })

  it('isRunning 在 initializing/backend-starting/reconnecting 时为 true', async () => {
    const { useAppStartup } = await loadUseAppStartup()
    const { setStatus, beginRetry, isRunning } = useAppStartup()

    setStatus('initializing')
    expect(isRunning.value).toBe(true)

    setStatus('backend-starting')
    expect(isRunning.value).toBe(true)

    beginRetry()
    expect(isRunning.value).toBe(true)

    setStatus('connected')
    expect(isRunning.value).toBe(false)

    setStatus('failed')
    expect(isRunning.value).toBe(false)

    setStatus('closing')
    expect(isRunning.value).toBe(false)
  })

  it('自定义 message 覆盖默认文案', async () => {
    const { useAppStartup } = await loadUseAppStartup()
    const { state, setStatus } = useAppStartup()

    setStatus('timeout', { message: '自定义超时提示' })
    expect(state.value.message).toBe('自定义超时提示')
  })
})
