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

  it('迟到回读不覆盖请求期间新编辑的目标', async () => {
    const failedSave = setup(false)
    const existing = '[{"operator_id":"existing","goals":[]}]'
    failedSave.task.CultivateTargets = existing
    await failedSave.controller.setManaged(true)
    expect(failedSave.task.CultivateAllOwned).toBe(false)
    expect(failedSave.task.CultivateTargets).toBe(existing)
    expect(getUser).not.toHaveBeenCalled()
    expect(failedSave.controller.managing.value).toBe(false)
    scope.stop()

    const failedRead = setup()
    let rejectRead: (reason: Error) => void = () => {}
    getUser.mockImplementationOnce(
      () =>
        new Promise((_resolve, reject) => {
          rejectRead = reject
        })
    )
    const readback = failedRead.controller.setManaged(true)
    await Promise.resolve()
    await failedRead.controller.setManaged(true)
    expect(failedRead.saveField).toHaveBeenCalledTimes(1)
    expect(failedRead.controller.managing.value).toBe(true)
    rejectRead(new Error('offline'))
    await expect(readback).rejects.toThrow('offline')
    expect(failedRead.task.CultivateAllOwned).toBe(true)
    expect(failedRead.task.CultivateTargets).toBe('[]')
    expect(failedRead.controller.managing.value).toBe(false)
    scope.stop()
    getUser.mockClear()

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
    const edited = '[{"operator_id":"new-edit","goals":[]}]'
    task.CultivateTargets = edited
    completeRead({ code: 200, data: { user: { Task: { CultivateTargets: '[]' } } } })
    await pending
    expect(task.CultivateTargets).toBe(edited)
    expect(controller.managing.value).toBe(false)
  })
})
