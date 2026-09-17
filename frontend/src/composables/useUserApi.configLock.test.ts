import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  states: vi.fn(),
  addUser: vi.fn(),
  updateUser: vi.fn(),
  deleteUser: vi.fn(),
  reorderUser: vi.fn(),
  warning: vi.fn(),
}))

vi.mock('@/api', () => ({
  Service: {
    addUserApiScriptsUserAddPost: mocks.addUser,
    updateUserApiScriptsUserUpdatePost: mocks.updateUser,
    deleteUserApiScriptsUserDeletePost: mocks.deleteUser,
    reorderUserApiScriptsUserOrderPost: mocks.reorderUser,
  },
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

const runningTask = {
  taskId: 'task-1',
  mode: 'ScriptConfig',
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
}

describe('useUserApi runtime config lock', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.states.mockReturnValue([runningTask])
    vi.stubGlobal('window', {
      electronAPI: {
        getLogger: () => ({ debug: vi.fn(), warn: vi.fn(), error: vi.fn() }),
      },
    })
  })

  it('rejects user creation without sending a request while the script is running', async () => {
    const { useUserApi } = await import('./useUserApi')
    const { addUser, addUserErrorCode, error, loading } = useUserApi()

    const result = await addUser('script-1')

    expect(result).toBeNull()
    expect(loading.value).toBe(false)
    expect(error.value).toBe('edit.configLocked')
    expect(addUserErrorCode.value).toBeNull()
    expect(mocks.warning).toHaveBeenCalledWith('edit.configLocked')
    expect(mocks.addUser).not.toHaveBeenCalled()
  })

  it('rejects user updates without sending a request while the script is running', async () => {
    const { useUserApi } = await import('./useUserApi')
    const { error, loading, updateUser } = useUserApi()

    const result = await updateUser('script-1', 'user-1', { Info: { Name: 'new-name' } })

    expect(result).toBe(false)
    expect(loading.value).toBe(false)
    expect(error.value).toBe('edit.configLocked')
    expect(mocks.warning).toHaveBeenCalledWith('edit.configLocked')
    expect(mocks.updateUser).not.toHaveBeenCalled()
  })

  it('rejects user deletion without sending a request while the script is running', async () => {
    const { useUserApi } = await import('./useUserApi')
    const { error, loading, deleteUser } = useUserApi()

    const result = await deleteUser('script-1', 'user-1')

    expect(result).toBe(false)
    expect(loading.value).toBe(false)
    expect(error.value).toBe('edit.configLocked')
    expect(mocks.warning).toHaveBeenCalledWith('edit.configLocked')
    expect(mocks.deleteUser).not.toHaveBeenCalled()
  })

  it('rejects user reordering without sending a request while the script is running', async () => {
    const { useUserApi } = await import('./useUserApi')
    const { error, reorderUser } = useUserApi()

    const result = await reorderUser('script-1', ['user-1', 'user-2'])

    expect(result).toBe(false)
    expect(error.value).toBe('edit.configLocked')
    expect(mocks.warning).toHaveBeenCalledWith('edit.configLocked')
    expect(mocks.reorderUser).not.toHaveBeenCalled()
  })
})
