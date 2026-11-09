import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { reactive } from 'vue'
import { message } from 'ant-design-vue'
import {
  CancelablePromise,
  GetService,
  UpdateService,
  type GlobalConfig,
  type OutBase,
  type SettingGetOut,
} from '@/api'

vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }))
vi.mock('@/i18n', () => ({ translate: (key: string) => key }))
vi.mock('ant-design-vue', () => ({ message: { error: vi.fn() } }))
vi.mock('@/utils/sentry', () => ({ setTelemetryEnabled: vi.fn() }))
vi.mock('@/composables/useVersionService', async () => {
  const { ref } = await import('vue')
  return { updateInfo: ref(null) }
})

const reply = <T>(value: T) => new CancelablePromise<T>(resolve => resolve(value))
const success: OutBase = { code: 200, status: 'success', message: '' }

function pending<T>() {
  let resolve!: (value: T) => void
  const promise = new CancelablePromise<T>(finish => {
    resolve = finish
  })
  return { promise, resolve }
}

let useSettingPersistence: (typeof import('./useSettingPersistence'))['useSettingPersistence']
const syncBackendConfig = vi.fn()

beforeEach(async () => {
  vi.clearAllMocks()
  syncBackendConfig.mockReset()
  vi.stubGlobal('window', {
    electronAPI: {
      getLogger: () => ({ info: vi.fn(), error: vi.fn() }),
      syncBackendConfig,
    },
  })
  ;({ useSettingPersistence } = await import('./useSettingPersistence'))
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('settings persistence contract', () => {
  it('applies only the confirmed field and sends cloneable desktop configuration', async () => {
    const settings = reactive<GlobalConfig>({
      Function: { IfSilence: false, IfAllowSleep: true },
      Notify: { IfSendStatistic: false },
    })
    const request = pending<OutBase>()
    const write = vi
      .spyOn(UpdateService, 'updateScriptApiSettingUpdatePost')
      .mockReturnValueOnce(request.promise)
      .mockImplementation(() => reply(success))
    const read = vi
      .spyOn(GetService, 'getScriptsApiSettingGetPost')
      .mockImplementation(() => reply<SettingGetOut>({ code: 200, data: settings }))
    const desktopConfigurations: unknown[] = []
    syncBackendConfig.mockImplementation(async data => {
      desktopConfigurations.push(structuredClone(data))
    })
    const persistence = useSettingPersistence(settings, vi.fn())

    const saved = persistence.handleSettingChange('Function', 'IfSilence', true)
    expect(persistence.loading.value).toBe(true)
    expect(settings.Function?.IfSilence).toBe(false)
    expect(desktopConfigurations).toEqual([])
    request.resolve(success)

    await expect(saved).resolves.toBe(true)
    expect(settings.Function).toEqual({ IfSilence: true, IfAllowSleep: true })
    expect(write).toHaveBeenCalledWith({ data: { Function: { IfSilence: true } } })
    expect(desktopConfigurations).toEqual([
      { UI: undefined, Start: undefined, Update: undefined, Function: settings.Function },
    ])
    expect(persistence.loading.value).toBe(false)

    await expect(
      persistence.handleDynamicSettingChange('Notify', 'IfSendStatistic', true)
    ).resolves.toBe(true)
    expect(settings.Notify?.IfSendStatistic).toBe(true)
    expect(read).not.toHaveBeenCalled()
  })

  it('waits for normalized values from the backend before confirming the save', async () => {
    const settings = reactive<GlobalConfig>({ Notify: { KoishiServerAddress: '' } })
    vi.spyOn(UpdateService, 'updateScriptApiSettingUpdatePost').mockImplementation(() =>
      reply(success)
    )
    const response = pending<SettingGetOut>()
    const read = vi
      .spyOn(GetService, 'getScriptsApiSettingGetPost')
      .mockReturnValue(response.promise)
    const persistence = useSettingPersistence(settings, vi.fn())
    const saved = persistence.handleSettingChange(
      'Notify',
      'KoishiServerAddress',
      'http://127.0.0.1:5140/'
    )
    let settled = false
    void saved.then(() => {
      settled = true
    })

    await vi.waitFor(() => expect(read).toHaveBeenCalledOnce())
    expect(settled).toBe(false)
    expect(settings.Notify?.KoishiServerAddress).toBe('')
    response.resolve({
      code: 200,
      data: { Notify: { KoishiServerAddress: 'http://127.0.0.1:5140' } },
    })

    await expect(saved).resolves.toBe(true)
    expect(settings.Notify?.KoishiServerAddress).toBe('http://127.0.0.1:5140')
    expect(syncBackendConfig).toHaveBeenCalledOnce()
  })

  it('preserves saved values on failure, allows retry and keeps replay rejection semantics', async () => {
    const settings = reactive<GlobalConfig>({
      Function: { IfSilence: false },
      Replay: { Port: 4455 },
    })
    const rejected: OutBase = { code: 500, status: 'error', message: 'setting rejected' }
    const write = vi
      .spyOn(UpdateService, 'updateScriptApiSettingUpdatePost')
      .mockImplementationOnce(() => reply(rejected))
      .mockImplementationOnce(() => reply(success))
      .mockImplementationOnce(() => reply(rejected))
    const read = vi
      .spyOn(GetService, 'getScriptsApiSettingGetPost')
      .mockImplementation(() => reply<SettingGetOut>({ code: 200, data: settings }))
    const persistence = useSettingPersistence(settings, vi.fn())

    await expect(persistence.handleSettingChange('Function', 'IfSilence', true)).resolves.toBe(
      false
    )
    expect(settings.Function?.IfSilence).toBe(false)
    expect(syncBackendConfig).not.toHaveBeenCalled()
    expect(message.error).toHaveBeenCalledExactlyOnceWith('setting rejected')

    await expect(persistence.handleSettingChange('Function', 'IfSilence', true)).resolves.toBe(true)
    expect(settings.Function?.IfSilence).toBe(true)
    await expect(persistence.handleSettingChange('Replay', 'Port', 4456)).rejects.toThrow(
      'core.setting.toast.saveFailed'
    )
    expect(settings.Replay?.Port).toBe(4455)
    expect(write).toHaveBeenCalledTimes(3)
    expect(read).not.toHaveBeenCalled()
    expect(message.error).toHaveBeenCalledTimes(2)
    expect(persistence.loading.value).toBe(false)
  })
})
