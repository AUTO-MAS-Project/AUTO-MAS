import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  states: vi.fn(),
  updateScript: vi.fn(),
  warning: vi.fn(),
}))

vi.mock('@/api', () => ({
  Service: {
    updateScriptApiScriptsUpdatePost: mocks.updateScript,
  },
  ScriptCreateIn: { type: {} },
  HsrService: {},
  MaaFwService: {},
}))

vi.mock('ant-design-vue', () => ({
  message: {
    warning: mocks.warning,
  },
}))

vi.mock('@/i18n', () => ({
  translate: (key: string) => key,
}))

vi.mock('@/composables/useTaskRuntimeState', () => ({
  getTaskRuntimeStates: mocks.states,
}))

describe('useScriptApi runtime config lock', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('window', {
      electronAPI: {
        getLogger: () => ({ warn: vi.fn(), error: vi.fn() }),
      },
    })
  })

  it('rejects script updates without sending a request while the script is running', async () => {
    mocks.states.mockReturnValue([
      {
        taskId: 'task-1',
        mode: 'AutoProxy',
        queueId: null,
        scriptId: 'script-1',
        userId: null,
        stopping: false,
        isCycle: false,
        scripts: [],
        taskInfo: [],
        cycleNextList: [],
        log: '',
        phase: 'active',
        taskName: null,
        taskType: null,
        result: null,
        outcome: null,
        error: null,
        completedAt: null,
      },
    ])
    const { useScriptApi } = await import('./useScriptApi')
    const { error, loading, updateScript } = useScriptApi()

    const result = await updateScript('script-1', { Info: { Name: 'new-name' } })

    expect(result).toBe(false)
    expect(loading.value).toBe(false)
    expect(error.value).toBe('edit.configLocked')
    expect(mocks.warning).toHaveBeenCalledWith('edit.configLocked')
    expect(mocks.updateScript).not.toHaveBeenCalled()
  })
})
