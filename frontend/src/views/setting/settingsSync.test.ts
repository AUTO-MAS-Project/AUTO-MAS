import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  createRenderer,
  createSSRApp,
  defineComponent,
  h,
  ref,
  ssrContextKey,
  type ComponentOptions,
  type PropType,
} from 'vue'
import { renderToString } from '@vue/server-renderer'
import type { SettingsCategory, SettingsViewModel } from '@/types/settings'
import type { SettingsSyncPayload } from '../../../electron/ipc/settingsSync.types'
import SettingsPage from './index.vue'
import { useSettingsApi } from '@/composables/useSettingsApi'
import { ApiError } from '@/api'

type SettingChange = (category: SettingsCategory, key: string, value: unknown) => Promise<boolean>

const initialBackend = () => ({
  appearance: { if_show_tray: false, if_to_tray: false, if_hide_close_button: false },
  start: { if_self_start: false, if_minimize_directly: false },
  updates: { source: 'GitHub', if_auto_update: true, github_token: '', pause_until: '' },
  notify: { koishi_server_address: '' },
  function: { if_silence: false, if_allow_sleep: true },
  voice: { enabled: true, type: 'simple' },
})

type BackendSettings = ReturnType<typeof initialBackend>
type UpdateRequest = {
  data: { [Group in keyof BackendSettings]?: Partial<BackendSettings[Group]> }
}

const mocks = vi.hoisted(() => ({
  getSettings: vi.fn<() => Promise<{ code: number; data: BackendSettings }>>(),
  updateSettings: vi.fn<(request: UpdateRequest) => Promise<{ code: number; message?: string }>>(),
  syncBackendConfig: vi.fn<(payload: SettingsSyncPayload) => Promise<boolean>>(),
  updateTraySettings: vi.fn<(patch: SettingsSyncPayload['UI']) => Promise<boolean>>(),
  syncUiPreferences: vi.fn<(ui: SettingsViewModel['UI']) => void>(),
  restartPolling: vi.fn<() => Promise<void>>(),
  invalidateVoiceSettingsCache: vi.fn(),
  setTelemetryEnabled: vi.fn(),
  toastError: vi.fn(),
  toastWarning: vi.fn(),
  updateInfo: { value: 'pending' as string | null },
}))

const bindings = vi.hoisted(() => ({
  load: null as (() => Promise<void>) | null,
  change: null as SettingChange | null,
  settings: null as SettingsViewModel | null,
}))

vi.mock('@/api', async () => {
  const { ApiError } =
    await vi.importActual<typeof import('@/api/core/ApiError')>('@/api/core/ApiError')
  return {
    ApiError,
    Service: {
      getSettingApiSettingGetPost: mocks.getSettings,
      updateSettingApiSettingUpdatePost: mocks.updateSettings,
      getGitVersionApiInfoVersionPost: async () => ({ current_hash: 'test' }),
    },
  }
})
vi.mock('@/i18n', () => ({ translate: (key: string) => key }))
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }))
vi.mock('vue-router', () => ({ useRoute: () => ({ query: {} }) }))
vi.mock('ant-design-vue', () => ({
  message: { error: mocks.toastError, warning: mocks.toastWarning },
  Modal: {},
}))
vi.mock('@/composables/useUiPreferences', () => ({
  useUiPreferences: () => ({ syncUiPreferences: mocks.syncUiPreferences }),
}))
vi.mock('@/composables/useAudioPlayer', () => ({
  invalidateVoiceSettingsCache: mocks.invalidateVoiceSettingsCache,
}))
vi.mock('@/utils/sentry', () => ({ setTelemetryEnabled: mocks.setTelemetryEnabled }))
vi.mock('@/composables/useUpdateChecker', () => ({
  useUpdateChecker: () => ({
    restartPolling: mocks.restartPolling,
    updateVisible: ref(false),
    updateData: ref(null),
    latestVersion: ref(''),
    checkUpdate: vi.fn(),
  }),
}))
vi.mock('@/composables/useVersionService', () => ({ updateInfo: mocks.updateInfo }))
vi.mock('@/stores/cursorEffect', () => ({
  useCursorEffectStore: () => ({ effect: 'none', load: async () => {} }),
}))
vi.mock('@/stores/performance', () => ({
  usePerformanceStore: () => ({
    lowPerformanceMode: false,
    saving: false,
    initialize: async () => {},
  }),
}))
vi.mock('./useAppearanceSettings', () => ({
  useAppearanceSettings: () => ({
    themeMode: ref('system'),
    themeColor: ref('blue'),
    appearances: ref([]),
    appearanceId: ref(null),
    activeAppearance: ref(null),
    modalContextHolder: null,
    appearanceBusy: ref(false),
    themeModeOptions: ref([]),
    appearanceValue: ref('system'),
    appearanceOptions: ref([]),
    themeColorOptions: ref([]),
  }),
}))

// 捕获实际页面传给子组件的回调，保留真实设置 API 和查询合并行为。
vi.mock('@/components/ApiRetryAlert.vue', () => ({
  default: defineComponent({
    props: { onRetry: { type: Function as PropType<() => Promise<void>>, required: true } },
    setup(props) {
      bindings.load = props.onRetry
      return () => null
    },
  }),
}))
vi.mock('./TabBasic.vue', () => ({
  default: defineComponent({
    props: {
      settings: { type: Object as PropType<SettingsViewModel>, required: true },
      handleSettingChange: { type: Function as PropType<SettingChange>, required: true },
    },
    setup(props) {
      bindings.change = props.handleSettingChange
      bindings.settings = props.settings
      return () => null
    },
  }),
}))
vi.mock('./TabFunction.vue', () => ({ default: () => null }))
vi.mock('./TabNotify.vue', () => ({ default: () => null }))
vi.mock('./TabAdvanced.vue', () => ({ default: () => null }))
vi.mock('./TabOthers.vue', () => ({ default: () => null }))

let backend: BackendSettings
let electronConfig: {
  UI: NonNullable<SettingsSyncPayload['UI']> & { size: string }
  Start: NonNullable<SettingsSyncPayload['Start']>
  Update: NonNullable<SettingsSyncPayload['Update']>
  Function: NonNullable<SettingsSyncPayload['Function']>
}
let trayVisible: boolean
let snapshots: SettingsSyncPayload[]

const deferred = () => {
  let resolve!: () => void
  const promise = new Promise<void>(done => {
    resolve = done
  })
  return { promise, resolve }
}

// 只排空当前异步调用链；请求是否完成由下面的 Promise 屏障决定。
const flushAsyncWork = () => new Promise<void>(resolve => setImmediate(resolve))

function holdNextRead() {
  const started = deferred()
  const response = deferred()
  mocks.getSettings.mockImplementationOnce(async () => {
    const data = structuredClone(backend)
    started.resolve()
    await response.promise
    return { code: 200, data }
  })
  return { started: started.promise, release: response.resolve }
}

async function renderPage() {
  const slots = defineComponent({
    inheritAttrs: false,
    setup(_props, { slots }) {
      return () => h('div', slots.default?.())
    },
  })
  const app = createSSRApp(SettingsPage)
  app.component('ATabs', slots)
  app.component('ATabPane', slots)
  await renderToString(app)
  if (!bindings.load || !bindings.change || !bindings.settings) {
    throw new Error('设置页回调未绑定')
  }
  return { load: bindings.load, change: bindings.change, settings: bindings.settings }
}

interface HostNode {
  parent: HostNode | null
  children: HostNode[]
}

const hostNode = (): HostNode => ({ parent: null, children: [] })
const mountedPages = new Set<() => void>()

function mountPage() {
  const renderer = createRenderer<HostNode, HostNode>({
    createElement: hostNode,
    createText: hostNode,
    createComment: hostNode,
    patchProp() {},
    setText() {},
    setElementText() {},
    insert(child, parent) {
      child.parent = parent
      parent.children.push(child)
    },
    remove(child) {
      if (child.parent) {
        child.parent.children = child.parent.children.filter(node => node !== child)
        child.parent = null
      }
    },
    parentNode: node => node.parent,
    nextSibling: () => null,
  })
  type PageState = {
    loadSettings: () => Promise<void>
    handleSettingChange: SettingChange
    settings: SettingsViewModel
  }
  let state!: PageState
  const setup = (SettingsPage as ComponentOptions).setup!
  const app = renderer.createApp(
    defineComponent({
      setup(props, context) {
        // 在真实 Vue 实例中执行页面 setup，保留 mounted/unmount 生命周期。
        state = setup(props, context) as PageState
        return () => null
      },
    })
  )
  // Vite 为导入的 SFC 注入模块登记；实际挂载仍走普通 Vue 生命周期。
  app.provide(ssrContextKey, { modules: new Set<string>() })
  app.mount(hostNode())
  const unmount = () => {
    app.unmount()
    mountedPages.delete(unmount)
  }
  mountedPages.add(unmount)
  return {
    load: state.loadSettings,
    change: state.handleSettingChange,
    settings: state.settings,
    unmount,
  }
}

beforeEach(() => {
  vi.resetAllMocks()
  bindings.load = null
  bindings.change = null
  bindings.settings = null
  mocks.updateInfo.value = 'pending'
  backend = initialBackend()
  electronConfig = {
    UI: { IfShowTray: false, IfToTray: false, IfHideCloseButton: false, size: '1600,1000' },
    Start: { IfSelfStart: false, IfMinimizeDirectly: false },
    Update: { IfAutoUpdate: true },
    Function: { IfEnableTelemetry: true },
  }
  snapshots = []
  trayVisible = false
  mocks.getSettings.mockImplementation(async () => ({ code: 200, data: structuredClone(backend) }))
  mocks.updateSettings.mockImplementation(async ({ data }) => {
    for (const group of Object.keys(backend) as (keyof BackendSettings)[]) {
      if (data[group]) Object.assign(backend[group], data[group])
    }
    if (data.updates?.github_token !== undefined) {
      backend.updates.github_token = `stored:${data.updates.github_token}`
    }
    if (data.notify?.koishi_server_address !== undefined) {
      backend.notify.koishi_server_address = data.notify.koishi_server_address.trim()
    }
    return { code: 200 }
  })
  mocks.syncBackendConfig.mockImplementation(async payload => {
    // 模拟 IPC 结构化克隆和四组补丁，记录不可变快照，避免后续 reactive 写入污染断言。
    const snapshot = structuredClone(payload)
    snapshots.push(snapshot)
    if (snapshot.UI) Object.assign(electronConfig.UI, snapshot.UI)
    if (snapshot.Start) Object.assign(electronConfig.Start, snapshot.Start)
    if (snapshot.Update) Object.assign(electronConfig.Update, snapshot.Update)
    if (snapshot.Function) Object.assign(electronConfig.Function, snapshot.Function)
    trayVisible = electronConfig.UI.IfShowTray === true
    return true
  })
  mocks.updateTraySettings.mockImplementation(async patch => {
    Object.assign(electronConfig.UI, patch)
    trayVisible = electronConfig.UI.IfShowTray === true
    return true
  })
  mocks.restartPolling.mockResolvedValue(undefined)
  vi.stubGlobal('window', {
    electronAPI: {
      getLogger: () => ({ info: vi.fn(), error: vi.fn() }),
      syncBackendConfig: mocks.syncBackendConfig,
      updateTraySettings: mocks.updateTraySettings,
    },
  })
})

afterEach(() => {
  for (const unmount of mountedPages) unmount()
  vi.unstubAllGlobals()
})

describe('设置页同步顺序', () => {
  it('旧规范化回读结束后再保存托盘开关，较新值不会被回滚', async () => {
    const page = await renderPage()
    await page.load()
    const read = holdNextRead()
    const normalized = page.change('Update', 'GithubToken', 'token-A')
    await read.started
    const tray = page.change('UI', 'IfShowTray', true)
    await flushAsyncWork()
    const writesWhileReading = mocks.updateSettings.mock.calls.length
    read.release()
    await expect(Promise.all([normalized, tray])).resolves.toEqual([true, true])

    expect(backend.appearance.if_show_tray).toBe(true)
    expect(page.settings.UI?.IfShowTray).toBe(true)
    expect(electronConfig.UI.IfShowTray).toBe(true)
    expect(trayVisible).toBe(true)
    expect(writesWhileReading).toBe(1)
    expect(snapshots.map(snapshot => snapshot.UI?.IfShowTray)).toEqual([false, false, true])
    expect(mocks.updateTraySettings).toHaveBeenCalledWith({ IfShowTray: true })
  })

  it('连续规范化保存分别读取新快照，不复用前一次在途读取', async () => {
    const page = await renderPage()
    await page.load()
    const read = holdNextRead()
    const address = page.change('Notify', 'KoishiServerAddress', ' https://koishi.invalid ')
    await read.started
    const token = page.change('Update', 'GithubToken', 'token-B')
    await flushAsyncWork()
    read.release()
    await expect(Promise.all([address, token])).resolves.toEqual([true, true])

    expect(page.settings.Update?.GithubToken).toBe('stored:token-B')
    expect(electronConfig.Update.GithubToken).toBe('stored:token-B')
    expect(page.settings.Notify?.KoishiServerAddress).toBe('https://koishi.invalid')
    expect(mocks.getSettings).toHaveBeenCalledTimes(3)
    expect(mocks.updateSettings).toHaveBeenNthCalledWith(2, {
      data: { updates: { github_token: 'token-B' } },
    })
  })

  it.each(['首次加载', '手动重试'])('%s与保存共享边界', async mode => {
    const page = await renderPage()
    if (mode === '手动重试') await page.load()
    const read = holdNextRead()
    const load = page.load()
    await read.started
    const save = page.change('UI', 'IfHideCloseButton', true)
    await flushAsyncWork()
    const writesWhileReading = mocks.updateSettings.mock.calls.length
    read.release()
    await load
    await expect(save).resolves.toBe(true)

    expect(page.settings.UI?.IfHideCloseButton).toBe(true)
    expect(electronConfig.UI.IfHideCloseButton).toBe(true)
    expect(writesWhileReading).toBe(0)
  })

  it('等待 Electron 同步完成才执行下一次保存', async () => {
    const page = await renderPage()
    await page.load()
    const started = deferred()
    const response = deferred()
    const sync = mocks.syncBackendConfig.getMockImplementation()!
    mocks.syncBackendConfig.mockImplementationOnce(async payload => {
      const snapshot = structuredClone(payload)
      started.resolve()
      await response.promise
      return sync(snapshot)
    })
    const first = page.change('UI', 'IfShowTray', true)
    await started.promise
    const second = page.change('Start', 'IfSelfStart', true)
    await flushAsyncWork()
    const writesWhileSyncing = mocks.updateSettings.mock.calls.length
    response.resolve()
    await expect(Promise.all([first, second])).resolves.toEqual([true, true])

    expect(electronConfig.Start.IfSelfStart).toBe(true)
    expect(writesWhileSyncing).toBe(1)
    expect(electronConfig.UI.size).toBe('1600,1000')
    expect(Object.keys(snapshots.at(-1)!)).toEqual(['UI', 'Start', 'Update', 'Function'])
  })

  it('额外托盘更新也包含在串行边界内', async () => {
    const page = await renderPage()
    await page.load()
    const started = deferred()
    const response = deferred()
    const updateTray = mocks.updateTraySettings.getMockImplementation()!
    mocks.updateTraySettings.mockImplementationOnce(async patch => {
      started.resolve()
      await response.promise
      return updateTray(patch)
    })
    const first = page.change('UI', 'IfToTray', false)
    await started.promise
    const second = page.change('Start', 'IfSelfStart', true)
    await flushAsyncWork()
    const writesWhileUpdatingTray = mocks.updateSettings.mock.calls.length
    response.resolve()
    await expect(Promise.all([first, second])).resolves.toEqual([true, true])

    expect(writesWhileUpdatingTray).toBe(1)
    expect(mocks.updateTraySettings).toHaveBeenCalledWith({ IfToTray: false })
  })

  it('保存失败仍返回 false，后续任务继续执行', async () => {
    const page = await renderPage()
    await page.load()
    mocks.updateSettings.mockResolvedValueOnce({ code: 500, message: 'Rejected' })
    const failed = page.change('UI', 'IfShowTray', true)
    const next = page.change('Start', 'IfSelfStart', true)
    await expect(Promise.all([failed, next])).resolves.toEqual([false, true])

    expect(page.settings.UI?.IfShowTray).toBe(false)
    expect(electronConfig.Start.IfSelfStart).toBe(true)
    expect(mocks.toastError).toHaveBeenCalled()
  })

  it('读取失败后允许重试，不阻塞后续保存', async () => {
    const page = await renderPage()
    mocks.getSettings.mockRejectedValueOnce(new Error('Read failed'))
    await page.load()
    await page.load()
    await expect(page.change('Start', 'IfSelfStart', true)).resolves.toBe(true)

    expect(electronConfig.Start.IfSelfStart).toBe(true)
    expect(mocks.getSettings).toHaveBeenCalledTimes(2)
  })

  it('首次读取失败后，保存可直接回读缺失分组并继续处理下一项', async () => {
    const page = await renderPage()
    mocks.getSettings.mockRejectedValueOnce(new Error('Read failed'))
    await page.load()
    const first = page.change('UI', 'IfShowTray', true)
    const second = page.change('Start', 'IfSelfStart', true)
    await expect(Promise.all([first, second])).resolves.toEqual([true, true])

    expect(page.settings.UI?.IfShowTray).toBe(true)
    expect(electronConfig.UI.IfShowTray).toBe(true)
    expect(electronConfig.Start.IfSelfStart).toBe(true)
    expect(mocks.getSettings).toHaveBeenCalledTimes(2)
  })

  it('任务抛出的异常传给原调用方，队列仍能执行下一项', async () => {
    const page = await renderPage()
    await page.load()
    const error = new Error('Preference failure')
    mocks.syncUiPreferences.mockImplementationOnce(() => {
      throw error
    })
    const failed = page.change('UI', 'IfShowTray', true)
    const next = page.change('Start', 'IfSelfStart', true)
    await Promise.all([expect(failed).rejects.toBe(error), expect(next).resolves.toBe(true)])

    expect(electronConfig.Start.IfSelfStart).toBe(true)
  })

  it('保留 false 值及自动更新、语音和暂停更新的现有后续行为', async () => {
    const page = await renderPage()
    await page.load()
    await expect(page.change('Update', 'IfAutoUpdate', false)).resolves.toBe(true)
    await expect(page.change('Voice', 'Enabled', false)).resolves.toBe(true)
    await expect(page.change('Update', 'PauseUntil', '2030-01-02')).resolves.toBe(true)

    expect(electronConfig.Update.IfAutoUpdate).toBe(false)
    expect(mocks.updateSettings).toHaveBeenNthCalledWith(1, {
      data: { updates: { if_auto_update: false } },
    })
    expect(mocks.restartPolling).toHaveBeenCalledOnce()
    expect(mocks.invalidateVoiceSettingsCache).toHaveBeenCalledOnce()
    expect(mocks.updateInfo.value).toBeNull()
  })
})

describe('设置页跨实例生命周期', () => {
  it('卸载后立即结算尚未启动的保存，不等待旧读取也不写入', async () => {
    const page = mountPage()
    await page.load()
    const read = holdNextRead()
    const first = page.change('Update', 'GithubToken', 'token-A')
    await read.started
    let settled = false
    const queued = page.change('UI', 'IfShowTray', true).then(result => {
      settled = true
      return result
    })
    page.unmount()
    await flushAsyncWork()
    const settledBeforeResponse = settled
    read.release()
    const [, saved] = await Promise.all([first, queued])

    expect(saved).toBe(false)
    expect(settledBeforeResponse).toBe(true)
    expect(backend.appearance.if_show_tray).toBe(false)
    expect(mocks.updateSettings).toHaveBeenCalledTimes(1)
  })

  it('卸载后迟到的读取不再同步 UI 或 Electron，不影响重新进入的页面', async () => {
    const oldPage = mountPage()
    await oldPage.load()
    const read = holdNextRead()
    const pending = oldPage.change('Update', 'GithubToken', 'token-A')
    await read.started
    oldPage.unmount()
    const page = mountPage()
    await page.load()
    await page.change('UI', 'IfShowTray', true)
    const syncCount = snapshots.length
    const preferenceCount = mocks.syncUiPreferences.mock.calls.length
    read.release()
    const saved = await pending

    expect(saved).toBe(false)
    expect(oldPage.settings.Update?.GithubToken).toBe('')
    expect(snapshots).toHaveLength(syncCount)
    expect(mocks.syncUiPreferences).toHaveBeenCalledTimes(preferenceCount)
    expect(page.settings.UI?.IfShowTray).toBe(true)
    expect(electronConfig.UI.IfShowTray).toBe(true)
  })

  it('旧实例已发出的写入确认前，新实例不得发出覆盖写入', async () => {
    const oldPage = mountPage()
    await oldPage.load()
    const started = deferred()
    const response = deferred()
    const write = mocks.updateSettings.getMockImplementation()!
    mocks.updateSettings.mockImplementationOnce(async request => {
      started.resolve()
      await response.promise
      return write(request)
    })
    const pending = oldPage.change('UI', 'IfShowTray', true)
    await started.promise
    oldPage.unmount()
    const page = mountPage()
    const load = page.load()
    const save = page.change('UI', 'IfShowTray', false)
    await flushAsyncWork()
    const writesBeforeAcknowledgement = mocks.updateSettings.mock.calls.length
    response.resolve()
    const [oldResult] = await Promise.all([pending, load, save])
    await page.load()
    await expect(page.change('UI', 'IfShowTray', false)).resolves.toBe(true)

    expect(oldResult).toBe(false)
    expect(writesBeforeAcknowledgement).toBe(1)
    expect(backend.appearance.if_show_tray).toBe(false)
    expect(electronConfig.UI.IfShowTray).toBe(false)
  })

  it('旧写入收到明确失败响应后，新实例可以恢复保存', async () => {
    const oldPage = mountPage()
    await oldPage.load()
    const started = deferred()
    const response = deferred()
    mocks.updateSettings.mockImplementationOnce(async () => {
      started.resolve()
      await response.promise
      return { code: 500, message: 'Rejected' }
    })
    const pending = oldPage.change('UI', 'IfShowTray', true)
    await started.promise
    oldPage.unmount()
    const page = mountPage()
    const load = page.load()
    response.resolve()
    await expect(pending).resolves.toBe(false)
    await load
    await expect(page.change('Start', 'IfSelfStart', true)).resolves.toBe(true)

    expect(backend.start.if_self_start).toBe(true)
    expect(mocks.toastError).not.toHaveBeenCalledWith(expect.stringContaining('Rejected'))
  })

  it('在途保存的调用方立即取消，但新页面仍等待实际 HTTP 结算', async () => {
    const oldPage = mountPage()
    await oldPage.load()
    const started = deferred()
    const response = deferred()
    const write = mocks.updateSettings.getMockImplementation()!
    mocks.updateSettings.mockImplementationOnce(async request => {
      started.resolve()
      await response.promise
      return write(request)
    })
    const pending = oldPage.change('UI', 'IfShowTray', true)
    await started.promise
    oldPage.unmount()
    await expect(pending).resolves.toBe(false)
    const page = mountPage()
    const save = page.change('UI', 'IfShowTray', false)
    await flushAsyncWork()
    const writesBeforeResponse = mocks.updateSettings.mock.calls.length
    const readsBeforeResponse = mocks.getSettings.mock.calls.length
    response.resolve()
    await expect(save).resolves.toBe(true)

    expect(writesBeforeResponse).toBe(1)
    expect(readsBeforeResponse).toBe(2)
    expect(backend.appearance.if_show_tray).toBe(false)
    expect(electronConfig.UI.IfShowTray).toBe(false)
  })

  it.each(['IPC', '托盘'] as const)(
    '卸载时等待已经发出的%s，不提前放行新页面写入',
    async effect => {
      const oldPage = mountPage()
      await oldPage.load()
      const started = deferred()
      const response = deferred()
      if (effect === 'IPC') {
        const sync = mocks.syncBackendConfig.getMockImplementation()!
        mocks.syncBackendConfig.mockImplementationOnce(async payload => {
          const snapshot = structuredClone(payload)
          started.resolve()
          await response.promise
          return sync(snapshot)
        })
      } else {
        const updateTray = mocks.updateTraySettings.getMockImplementation()!
        mocks.updateTraySettings.mockImplementationOnce(async patch => {
          started.resolve()
          await response.promise
          return updateTray(patch)
        })
      }
      const pending = oldPage.change('UI', 'IfShowTray', true)
      await started.promise
      oldPage.unmount()
      await expect(pending).resolves.toBe(false)
      const page = mountPage()
      const save = page.change('Start', 'IfSelfStart', true)
      await flushAsyncWork()
      const writesBeforeResponse = mocks.updateSettings.mock.calls.length
      response.resolve()
      await expect(save).resolves.toBe(true)

      expect(writesBeforeResponse).toBe(1)
      expect(electronConfig.Start.IfSelfStart).toBe(true)
      expect(mocks.updateTraySettings).toHaveBeenCalledTimes(effect === 'IPC' ? 0 : 1)
    }
  )

  it('卸载后的旧回调不启动加载或保存', async () => {
    const page = mountPage()
    await page.load()
    page.unmount()
    const reads = mocks.getSettings.mock.calls.length
    await expect(page.change('UI', 'IfShowTray', true)).resolves.toBe(false)
    await expect(page.load()).resolves.toBeUndefined()

    expect(mocks.getSettings).toHaveBeenCalledTimes(reads)
    expect(mocks.updateSettings).not.toHaveBeenCalled()
  })

  it('卸载后旧读取失败不影响新页面，也不留下未处理异常', async () => {
    const oldPage = mountPage()
    await oldPage.load()
    const started = deferred()
    const response = deferred()
    mocks.getSettings.mockImplementationOnce(async () => {
      started.resolve()
      await response.promise
      throw new Error('Late read failure')
    })
    const load = oldPage.load()
    await started.promise
    oldPage.unmount()
    await expect(load).resolves.toBeUndefined()
    const page = mountPage()
    await expect(page.change('Start', 'IfSelfStart', true)).resolves.toBe(true)
    const syncCount = snapshots.length
    response.resolve()
    await flushAsyncWork()

    expect(snapshots).toHaveLength(syncCount)
    expect(mocks.toastError).not.toHaveBeenCalled()
    expect(electronConfig.Start.IfSelfStart).toBe(true)
  })

  it('旧实例的 IPC 失败结算后，新实例仍能保存且没有旧提示', async () => {
    const oldPage = mountPage()
    await oldPage.load()
    const started = deferred()
    const response = deferred()
    mocks.syncBackendConfig.mockImplementationOnce(async () => {
      started.resolve()
      await response.promise
      throw new Error('IPC failure')
    })
    const pending = oldPage.change('UI', 'IfShowTray', true)
    await started.promise
    oldPage.unmount()
    await expect(pending).resolves.toBe(false)
    const page = mountPage()
    const save = page.change('Start', 'IfSelfStart', true)
    response.resolve()
    await expect(save).resolves.toBe(true)

    expect(mocks.toastError).not.toHaveBeenCalled()
    expect(mocks.updateTraySettings).not.toHaveBeenCalled()
    expect(electronConfig.Start.IfSelfStart).toBe(true)
  })

  it('旧实例网络结果未知后释放已结算请求，后续保存不被永久锁定', async () => {
    const oldPage = mountPage()
    await oldPage.load()
    const started = deferred()
    const response = deferred()
    mocks.updateSettings.mockImplementationOnce(async () => {
      started.resolve()
      await response.promise
      throw new Error('Network Error')
    })
    const pending = oldPage.change('UI', 'IfShowTray', true)
    await started.promise
    oldPage.unmount()
    await expect(pending).resolves.toBe(false)
    const page = mountPage()
    const save = page.change('Start', 'IfSelfStart', true)
    await flushAsyncWork()
    const writesBeforeResponse = mocks.updateSettings.mock.calls.length
    response.resolve()
    await expect(save).resolves.toBe(true)

    expect(writesBeforeResponse).toBe(1)
    expect(mocks.updateSettings).toHaveBeenCalledTimes(2)
    expect(mocks.toastWarning).not.toHaveBeenCalled()
    expect(mocks.toastError).not.toHaveBeenCalled()
  })
})

describe('设置保存结果分类', () => {
  const validationBody = {
    detail: [
      {
        loc: ['body', 'data', 'appearance', 'if_show_tray'],
        msg: 'Input should be a valid boolean',
        type: 'bool_parsing',
        input: 'sensitive-input-must-not-be-shown',
      },
    ],
  }
  const validationReason = 'body.data.appearance.if_show_tray: Input should be a valid boolean'
  const httpError = (status: number, body: unknown = validationBody) =>
    new ApiError(
      { method: 'POST', url: '/api/setting/update' },
      {
        url: '/api/setting/update',
        ok: false,
        status,
        statusText: status === 422 ? 'Unprocessable Entity' : 'Server Error',
        body,
      },
      status === 422 ? 'Validation Error' : 'Server Error'
    )

  it('真实 HTTP 422 校验拒绝归类为明确失败，仅保留安全错误原因', async () => {
    const api = useSettingsApi()
    mocks.updateSettings.mockRejectedValueOnce(httpError(422))
    await expect(api.updateSettings({ UI: { IfShowTray: true } })).resolves.toBe(false)

    expect(api.saveFailure.value).toBe('rejected')
    expect(api.error.value).toBe(validationReason)
    expect(api.error.value).not.toContain(validationBody.detail[0].input)
    expect(api.loading.value).toBe(false)
    expect(mocks.updateSettings).toHaveBeenCalledOnce()
    expect(mocks.getSettings).not.toHaveBeenCalled()
  })

  it('页面展示 HTTP 422 的校验原因，后续排队保存仍可成功', async () => {
    const page = mountPage()
    await page.load()
    const reads = mocks.getSettings.mock.calls.length
    mocks.updateSettings.mockRejectedValueOnce(httpError(422))
    const failed = page.change('UI', 'IfShowTray', true)
    const next = page.change('Start', 'IfSelfStart', true)
    await expect(Promise.all([failed, next])).resolves.toEqual([false, true])

    expect(mocks.toastError).toHaveBeenCalledExactlyOnceWith(
      `setting.toast.saveFailed: ${validationReason}`
    )
    expect(mocks.toastWarning).not.toHaveBeenCalled()
    expect(page.settings.UI?.IfShowTray).toBe(false)
    expect(electronConfig.Start.IfSelfStart).toBe(true)
    expect(mocks.updateSettings).toHaveBeenCalledTimes(2)
    expect(mocks.getSettings).toHaveBeenCalledTimes(reads)
  })

  it.each([500, 502, 503])(
    '真实 HTTP %i 即使携带校验详情仍归类为未知，队列可恢复',
    async status => {
      const api = useSettingsApi()
      mocks.updateSettings.mockRejectedValueOnce(httpError(status))
      await expect(api.updateSettings({ UI: { IfShowTray: true } })).resolves.toBe(false)
      expect(api.saveFailure.value).toBe('unknown')
      expect(api.loading.value).toBe(false)

      const page = mountPage()
      await page.load()
      const reads = mocks.getSettings.mock.calls.length
      mocks.updateSettings.mockRejectedValueOnce(httpError(status))
      const failed = page.change('UI', 'IfShowTray', true)
      const next = page.change('Start', 'IfSelfStart', true)
      await expect(Promise.all([failed, next])).resolves.toEqual([false, true])

      expect(mocks.toastWarning).toHaveBeenCalledExactlyOnceWith('setting.toast.saveOutcomeUnknown')
      expect(mocks.toastError).not.toHaveBeenCalled()
      expect(page.settings.UI?.IfShowTray).toBe(false)
      expect(electronConfig.Start.IfSelfStart).toBe(true)
      expect(mocks.updateSettings).toHaveBeenCalledTimes(3)
      expect(mocks.getSettings).toHaveBeenCalledTimes(reads)
    }
  )

  it.each([
    ['HTML 错误页', '<html>Unprocessable Entity</html>'],
    ['空校验列表', { detail: [] }],
    ['不完整校验详情', { detail: [{ loc: ['body'], msg: 'Invalid' }] }],
  ])('HTTP 422 缺少可靠校验详情时保持未知：%s', async (_name, body) => {
    const api = useSettingsApi()
    mocks.updateSettings.mockRejectedValueOnce(httpError(422, body))
    await expect(api.updateSettings({ UI: { IfShowTray: true } })).resolves.toBe(false)

    expect(api.saveFailure.value).toBe('unknown')
    expect(mocks.updateSettings).toHaveBeenCalledOnce()
    expect(mocks.getSettings).not.toHaveBeenCalled()
  })

  it('明确失败和网络结果未知均返回 false，但保留不同的失败类别', async () => {
    const api = useSettingsApi()
    mocks.updateSettings.mockResolvedValueOnce({ code: 500, message: 'Rejected' })
    await expect(api.updateSettings({ UI: { IfShowTray: true } })).resolves.toBe(false)
    expect(api.saveFailure.value).toBe('rejected')
    expect(api.error.value).toBe('Rejected')

    mocks.updateSettings.mockRejectedValueOnce(new Error('Network Error'))
    await expect(api.updateSettings({ UI: { IfShowTray: true } })).resolves.toBe(false)
    expect(api.saveFailure.value).toBe('unknown')
    expect(api.error.value).toBe('Network Error')
    expect(api.loading.value).toBe(false)
    expect(mocks.updateSettings).toHaveBeenCalledTimes(2)
    expect(mocks.getSettings).not.toHaveBeenCalled()

    await expect(api.updateSettings({ UI: { IfShowTray: false } })).resolves.toBe(true)
    expect(api.saveFailure.value).toBeNull()
    expect(api.error.value).toBeNull()
  })

  it('活跃页面提示未知结果，不自动回读、重试或应用未确认值，后续保存可恢复', async () => {
    const page = mountPage()
    await page.load()
    const reads = mocks.getSettings.mock.calls.length
    const syncCount = snapshots.length
    mocks.updateSettings.mockRejectedValueOnce(new Error('Network Error'))
    await expect(page.change('UI', 'IfShowTray', true)).resolves.toBe(false)

    expect(mocks.toastWarning).toHaveBeenCalledExactlyOnceWith('setting.toast.saveOutcomeUnknown')
    expect(mocks.toastError).not.toHaveBeenCalled()
    expect(page.settings.UI?.IfShowTray).toBe(false)
    expect(snapshots).toHaveLength(syncCount)
    expect(mocks.getSettings).toHaveBeenCalledTimes(reads)
    expect(mocks.updateSettings).toHaveBeenCalledOnce()
    await expect(page.change('Start', 'IfSelfStart', true)).resolves.toBe(true)
    expect(electronConfig.Start.IfSelfStart).toBe(true)
  })
})
