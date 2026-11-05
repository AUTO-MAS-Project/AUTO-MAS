import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { effectScope, reactive, type EffectScope } from 'vue'
import { cultivateManagementKey } from './cultivateManagement'
import { useMaaCultivation } from './useMaaCultivation'

const { provided, getUser, getCatalog } = vi.hoisted(() => ({
  provided: new Map<unknown, unknown>(),
  getUser: vi.fn(),
  getCatalog: vi.fn(),
}))
vi.mock('vue', async importOriginal => ({
  ...(await importOriginal<typeof import('vue')>()),
  provide: (key: unknown, value: unknown) => provided.set(key, value),
}))
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }))
vi.mock('@/api', () => ({
  Service: {
    getUserApiScriptsUserGetPost: getUser,
    getMaaCultivateOperatorsApiScriptsMaaCultivateOperatorsPost: getCatalog,
  },
}))
vi.mock('@/composables/useMaaCultivateImportApi', () => ({
  useMaaCultivateImportApi: () => ({ parseImport: vi.fn() }),
}))
vi.mock('@/composables/useMaaCultivateDataApi', () => ({
  useMaaCultivateDataApi: () => ({ refresh: vi.fn() }),
}))

let scope: EffectScope
const setup = (saveResult = true) => {
  const task = reactive({
    CultivateTargets: '[]',
    CultivateAllOwned: false,
    CultivateSklandAccount: 'bound',
    CultivateSklandUid: 'bound',
    CultivateAutoRaise: true,
  })
  const saveField = vi.fn(async (_key: string, value: unknown) => {
    if (saveResult) task.CultivateAllOwned = Boolean(value)
    return saveResult
  })
  scope = effectScope()
  scope.run(() =>
    useMaaCultivation({
      scriptId: 'script',
      getUserId: () => 'user',
      task: () => task,
      isInitializing: () => true,
      isLocked: () => false,
      saveField,
      trackEdit: edit => edit(),
    })
  )
  const controller = provided.get(cultivateManagementKey) as {
    managed: { value: boolean }
    managing: { value: boolean }
    setManaged: (enabled: boolean) => Promise<void>
  }
  return { task, saveField, controller }
}

describe('全部已有干员托管', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    provided.clear()
    vi.stubGlobal('window', { electronAPI: { getLogger: () => ({ error: vi.fn() }) } })
    getCatalog.mockResolvedValue({ code: 200, data: [] })
  })
  afterEach(() => {
    scope.stop()
    vi.unstubAllGlobals()
  })

  it('保存失败不会回读或清空现有目标', async () => {
    const { task, controller } = setup(false)
    await controller.setManaged(true)
    expect(task.CultivateAllOwned).toBe(false)
    expect(task.CultivateTargets).toBe('[]')
    expect(getUser).not.toHaveBeenCalled()
    expect(controller.managing.value).toBe(false)
  })

  it('回读期间阻止重复操作，回读失败保留真实托管状态', async () => {
    const { task, saveField, controller } = setup()
    let rejectRead: (reason: Error) => void = () => {}
    getUser.mockImplementation(
      () =>
        new Promise((_resolve, reject) => {
          rejectRead = reject
        })
    )
    const pending = controller.setManaged(true)
    const failed = expect(pending).rejects.toThrow('offline')
    await Promise.resolve()
    await controller.setManaged(true)
    expect(saveField).toHaveBeenCalledTimes(1)
    expect(controller.managing.value).toBe(true)
    rejectRead(new Error('offline'))
    await failed
    expect(task.CultivateAllOwned).toBe(true)
    expect(task.CultivateTargets).toBe('[]')
    expect(controller.managing.value).toBe(false)
  })

  it('迟到回读不覆盖请求期间新编辑的目标', async () => {
    const { task, controller } = setup()
    let completeRead: (value: unknown) => void = () => {}
    getUser.mockImplementationOnce(
      () =>
        new Promise(resolve => {
          completeRead = resolve
        })
    )
    const pending = controller.setManaged(true)
    await Promise.resolve()
    expect(getUser).toHaveBeenCalledTimes(1)
    task.CultivateTargets = '[{"operator_id":"new-edit","goals":[]}]'
    completeRead({ code: 200, data: { user: { Task: { CultivateTargets: '[]' } } } })
    await pending
    expect(task.CultivateTargets).toContain('new-edit')
  })
})
