import { effectScope, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => {
  const logger = { debug: () => {}, info: () => {}, warn: () => {}, error: () => {} }
  ;(globalThis as { window?: unknown }).window = {
    electronAPI: { getLogger: () => logger },
    addEventListener: () => {},
    removeEventListener: () => {},
  }
  ;(globalThis as { localStorage?: unknown }).localStorage = {
    getItem: () => null,
    setItem: () => {},
  }
  return {
    route: { name: 'MaaFWUserEdit', params: {} as Record<string, string> },
    mounted: [] as Array<() => unknown>,
    replace: vi.fn(),
    push: vi.fn(),
    getScript: vi.fn(),
    previewInterface: vi.fn(),
    addUser: vi.fn(),
    getUsers: vi.fn(),
    updateUser: vi.fn(),
    ensureBackup: vi.fn(async () => ({ code: 200 })),
    /** 页面宿主交来的上下文；null 表示不在宿主里 */
    host: null as unknown,
  }
})

vi.mock('vue', async original => ({
  ...(await original<typeof import('vue')>()),
  onMounted: (hook: () => unknown) => mocks.mounted.push(hook),
  onBeforeUnmount: vi.fn(),
  onUnmounted: vi.fn(),
}))
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }))
vi.mock('@/i18n', () => ({ translate: (key: string) => key }))
vi.mock('vue-router', () => ({
  useRoute: () => mocks.route,
  useRouter: () => ({ replace: mocks.replace, push: mocks.push }),
}))
vi.mock('ant-design-vue', () => ({
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  Modal: { confirm: vi.fn() },
}))
vi.mock('@/api', () => ({
  Service: { ensureConfigBackupApiApiScriptsBackupEnsurePost: mocks.ensureBackup },
}))
vi.mock('@/composables/useScriptApi', () => ({
  useScriptApi: () => ({ getScript: mocks.getScript }),
}))
vi.mock('@/composables/useUserApi', () => ({
  useUserApi: () => ({
    addUser: mocks.addUser,
    getUsers: mocks.getUsers,
    updateUser: mocks.updateUser,
  }),
}))
vi.mock('@/composables/useMaaFWApi', () => ({
  buildMaaFWAssetUrl: () => '',
  useMaaFWApi: () => ({ loading: ref(false), previewInterface: mocks.previewInterface }),
}))
vi.mock('../../MaaFWFlavor/pageHostContext', () => ({
  useMaaFWPageHostContext: () => mocks.host,
}))
vi.mock('@/composables/useScriptConfigLock', () => ({
  useScriptConfigLock: () => ({ configLocked: ref(false) }),
}))

import { useMaaFWUserPage } from './useMaaFWUserPage'
import { useMaaFWUserPersistence } from './useMaaFWUserPersistence'
import { useMaaFWUserSaveStatus } from './useMaaFWUserSaveStatus'
import { useMaaFWUserForm } from './useMaaFWUserForm'
import type { MaaFWTaskSnapshot } from '@/types/script'

const task = (name: string) => ({
  name,
  entry: name,
  group: [],
  controller: [],
  resource: [],
  option: [],
  defaultCheck: false,
})

const preview = {
  path: 'D:/project',
  project: { name: 'demo', icon: null },
  controllers: [{ name: 'Win', type: 'Win32' }],
  resources: [{ name: 'Official', controller: [] }],
  groups: [],
  tasks: [task('Daily'), task('Weekly')],
  options: [],
  presets: [],
}

const userResponse = (userId: string) => ({
  code: 200,
  index: [{ uid: userId, type: 'MaaFWUserConfig' }],
  data: {
    [userId]: {
      Info: { Name: 'Alice' },
      Task: {
        SelectedPreset: '',
        TaskSnapshot: JSON.stringify({ taskOrder: ['Daily', 'Gone'], taskChecked: {} }),
      },
    },
  },
})

const deferred = <T>() => {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(resolvePromise => {
    resolve = resolvePromise
  })
  return { promise, resolve }
}

const mountPage = (userId: string) => {
  const scope = effectScope()
  const page = scope.run(() => useMaaFWUserPage({ scriptId: 's1', userId }))!
  expect(mocks.mounted).toHaveLength(1)
  void mocks.mounted[0]()
  return { scope, page }
}

describe('useMaaFWUserPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.mounted.length = 0
    mocks.host = null
    mocks.getScript.mockResolvedValue({
      type: 'MaaFW',
      name: 'Demo',
      config: { Info: { Path: 'D:/project', Controller: '', Resource: '' }, Emulator: { Id: '-' } },
    })
    mocks.previewInterface.mockResolvedValue(preview)
    mocks.updateUser.mockResolvedValue(true)
  })

  it('用户数据回填完之前不落盘，回填后照常保存', async () => {
    mocks.route.name = 'MaaFWUserEdit'
    mocks.route.params = { scriptId: 's1', userId: 'u1' }
    const users = deferred<ReturnType<typeof userResponse>>()
    mocks.getUsers.mockReturnValueOnce(users.promise)
    const { scope, page } = mountPage('u1')

    await vi.waitFor(() => expect(mocks.getUsers).toHaveBeenCalledWith('s1', 'u1'))
    // interface 已读到、用户数据还没回来：字段保存与队列保存都不写
    expect(page.previewData.value).not.toBeNull()
    await expect(page.handleFieldSave('Info.Notes', 'x')).resolves.toBeUndefined()
    await page.deleteTask('Daily')
    expect(mocks.updateUser).not.toHaveBeenCalled()

    users.resolve(userResponse('u1'))
    await vi.waitFor(() =>
      expect(mocks.ensureBackup).toHaveBeenCalledWith({
        scriptId: 's1',
        userId: 'u1',
        target: 'native',
      })
    )
    expect(mocks.updateUser).not.toHaveBeenCalled()
    expect(page.formData.userName).toBe('Alice')
    // interface 已没有的任务留成虚影
    expect(page.taskSnapshot.value.taskOrder).toEqual(['Daily', 'Gone'])
    expect(page.loading.value).toBe(false)

    await expect(page.handleFieldSave('Info.Notes', 'y')).resolves.toBe(true)
    expect(mocks.updateUser).toHaveBeenCalledWith('s1', 'u1', { Info: { Notes: 'y' } })
    scope.stop()
  })

  it('新建模式：建好用户后改写 userId 持有者并 replace 到脚本类型那条线的编辑路由', async () => {
    mocks.route.name = 'MaaFWUserAdd'
    mocks.route.params = { scriptId: 's1' }
    mocks.addUser.mockResolvedValue({ userId: 'u9' })
    mocks.getUsers.mockResolvedValue(userResponse('u9'))
    const { scope, page } = mountPage('')
    expect(page.isEdit.value).toBe(false)
    expect(page.userIdHolder.value).toBe('')

    await vi.waitFor(() =>
      expect(mocks.ensureBackup).toHaveBeenCalledWith({
        scriptId: 's1',
        userId: 'u9',
        target: 'native',
      })
    )
    expect(mocks.replace).toHaveBeenCalledWith({
      name: 'MaaFWUserEdit',
      params: { scriptId: 's1', userId: 'u9' },
    })
    expect(page.userIdHolder.value).toBe('u9')
    expect(page.isEdit.value).toBe(true)
    expect(mocks.getUsers).toHaveBeenCalledWith('s1', 'u9')
    // replace 发生在读用户数据之前
    expect(mocks.replace.mock.invocationCallOrder[0]).toBeLessThan(
      mocks.getUsers.mock.invocationCallOrder[0]
    )
    scope.stop()
  })

  it('在页面宿主里：脚本详情用宿主读好的，建好用户后按脚本实际类型去编辑路由（不看路由名）', async () => {
    const host = {
      scriptType: ref('M9A'),
      mode: 'userAdd',
      wizardStep: ref(0),
      takeInitialScript: vi.fn(() => ({
        type: 'M9A',
        name: 'Demo',
        config: {
          Info: { Path: 'D:/project', Controller: '', Resource: '' },
          Emulator: { Id: '-' },
        },
      })),
    }
    mocks.host = host
    // 路由名故意与脚本类型不符：跳转目标只看脚本类型
    mocks.route.name = 'MaaFWUserAdd'
    mocks.route.params = { scriptId: 's1' }
    mocks.addUser.mockResolvedValue({ userId: 'u9' })
    mocks.getUsers.mockResolvedValue(userResponse('u9'))
    const { scope, page } = mountPage('')

    await vi.waitFor(() => expect(mocks.replace).toHaveBeenCalled())
    expect(host.takeInitialScript).toHaveBeenCalledOnce()
    expect(mocks.getScript).not.toHaveBeenCalled()
    expect(mocks.addUser).toHaveBeenCalledOnce()
    expect(mocks.replace).toHaveBeenCalledWith({
      name: 'M9AUserEdit',
      params: { scriptId: 's1', userId: 'u9' },
    })
    expect(page.scriptType).toBe(host.scriptType)
    expect(page.scriptRoute.value).toEqual({ name: 'M9AScriptEdit', params: { id: 's1' } })
    scope.stop()
  })
})

describe('useMaaFWUserPersistence', () => {
  const setup = (userId: string, initializing: boolean) => {
    const scope = effectScope()
    const result = scope.run(() => {
      const status = useMaaFWUserSaveStatus()
      const { formData } = useMaaFWUserForm()
      const taskSnapshot = ref<MaaFWTaskSnapshot>({
        taskOrder: ['Managed'],
        taskChecked: { Managed: true },
        taskOptions: {},
      })
      const persistence = useMaaFWUserPersistence({
        scriptId: 's1',
        userIdHolder: { value: userId },
        formData,
        taskSnapshot,
        previewData: ref(null),
        isInitializing: ref(initializing),
        isManagedTaskId: () => true,
        enqueueSave: status.enqueueSave,
        pendingCount: status.pendingCount,
      })
      return { ...persistence, formData }
    })!
    return { scope, ...result }
  }

  beforeEach(() => {
    vi.clearAllMocks()
    mocks.updateUser.mockResolvedValue(true)
    mocks.getUsers.mockResolvedValue({ code: 200, data: {} })
  })

  it('没有用户 id 或初始化中：两条落盘路径都直接返回', async () => {
    for (const [userId, initializing] of [
      ['', false],
      ['u1', true],
    ] as const) {
      const { scope, handleFieldSave, savePresetAndSnapshot } = setup(userId, initializing)
      await expect(handleFieldSave('Info.Notes', 'x')).resolves.toBeUndefined()
      await savePresetAndSnapshot()
      scope.stop()
    }
    expect(mocks.updateUser).not.toHaveBeenCalled()
  })

  it('队列有受管任务时，只有排在最后的那次保存把后端结果拉回来', async () => {
    const { scope, savePresetAndSnapshot } = setup('u1', false)
    await Promise.all([savePresetAndSnapshot(), savePresetAndSnapshot()])
    expect(mocks.updateUser).toHaveBeenCalledTimes(2)
    expect(mocks.getUsers).toHaveBeenCalledOnce()
    expect(mocks.getUsers.mock.invocationCallOrder[0]).toBeGreaterThan(
      mocks.updateUser.mock.invocationCallOrder[1]
    )
    scope.stop()
  })

  it('userName 改的是 Info.Name，其余按点路径拼', async () => {
    const { scope, handleFieldSave } = setup('u1', false)
    await handleFieldSave('userName', 'Bob')
    await handleFieldSave('Info.Account', 'acc')
    expect(mocks.updateUser.mock.calls).toEqual([
      ['s1', 'u1', { Info: { Name: 'Bob' } }],
      ['s1', 'u1', { Info: { Account: 'acc' } }],
    ])
    scope.stop()
  })
})
