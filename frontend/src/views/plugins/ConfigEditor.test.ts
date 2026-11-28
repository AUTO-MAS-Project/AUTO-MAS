// @vitest-environment vue-client
import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { createSSRApp, defineComponent, h, onServerPrefetch } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import axios from 'axios'
import Antd, { message } from 'ant-design-vue'
import {
  BackgroundTaskState,
  BackupTargetHint,
  Service,
  TriggerUiState,
  type DeclarativeConfigUi,
  type FrontendSurfaceMount,
} from '@/api'
import { editorView } from '../../../tests/declarativeEditorView'
import { fire } from '../../../tests/vueRenderer'
import { pluginUiFrame } from '../../../tests/pluginUiFrame'
import type { ConfirmOptions } from '@/composables/useConfirm'
import * as confirmation from '@/composables/useConfirm'
import * as taskApi from '@/composables/useTaskApi'
import { genericEditorRoutes } from '@/router/scriptEditorRoutes'
import ConfigEditor from './ConfigEditor.vue'
import * as editorModule from './useDeclarativeConfigEditor'
import type { SettingsValues } from './settings/usePluginSettingsDraft'

vi.hoisted(() => {
  vi.stubGlobal(
    'window',
    Object.assign(new EventTarget(), {
      __AUTO_MAS_BROWSER_DEV_MODE__: true,
      setTimeout,
      clearTimeout,
      electronAPI: { getLogger: () => ({ error: vi.fn() }) },
    })
  )
})
vi.mock('@/composables/useAudioPlayer', () => ({ useAudioPlayer: () => ({ playSound: vi.fn() }) }))
vi.mock('@/components/DocLink.vue', () => ({ default: { render: () => null } }))
vi.mock('@/components/GameBindingSection.vue', () => ({ default: { render: () => null } }))
vi.mock('@/services/websocket/subscriptions', () => ({ subscribe: vi.fn(), unsubscribe: vi.fn() }))
vi.mock('@/services/websocket/connection', () => ({
  reconnectNow: vi.fn(),
  connectionState: () => ({ value: 'open' }),
  onConnected: () => () => {},
  onDisconnected: () => () => {},
  send: vi.fn(),
  request: vi.fn(),
  connectionInfo: vi.fn(),
}))
vi.mock('@/composables/useAppLifecycle', () => ({
  beginIntentionalBackendRestart: vi.fn(),
  endIntentionalBackendRestart: vi.fn(),
}))

const useEditor = editorModule.useDeclarativeConfigEditor
const namespace = 'plugins.demo15.config'
const masked = '__AUTO_MAS_CONFIG_MASKED__'
const planTables = [
  { key: 'tasks', columns: ['First', 'Second'], rows: ['Count'], transpose: true },
]
const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

beforeEach(() => {
  vi.spyOn(message, 'success').mockImplementation(vi.fn())
  vi.spyOn(message, 'error').mockImplementation(vi.fn())
  vi.spyOn(Service, 'getActiveConfigTriggersApiConfigTriggersActiveGet').mockResolvedValue({
    code: 200,
    data: [],
  })
  vi.spyOn(Service, 'getScriptLockApiScriptsLockPost').mockResolvedValue({
    code: 200,
    locked: false,
  })
})
afterEach(() => {
  client.clear()
  vi.restoreAllMocks()
})

function detail(
  id: string,
  values: SettingsValues,
  hints: DeclarativeConfigUi['hints'],
  tables: DeclarativeConfigUi['tables'] = []
) {
  return {
    code: 200,
    index: [],
    data: { [id]: values },
    ui: { configUid: id, i18nNamespace: namespace, hints, tables },
  }
}

async function render(
  path: string,
  prepare?: (editor: ReturnType<typeof useEditor>) => Promise<void>
) {
  // SSR 在首次绘制前等详情请求完成，表单、路由、草稿和保存均走实际页面。
  vi.spyOn(editorModule, 'useDeclarativeConfigEditor').mockImplementation(target => {
    const editor = useEditor(target)
    onServerPrefetch(async () => {
      await editor.reload()
      await prepare?.(editor)
    })
    return editor
  })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      ...genericEditorRoutes,
      { path: '/plan', component: ConfigEditor, props: { mode: 'plan', planId: 'p' } },
      { path: '/scripts', name: 'Scripts', component: { render: () => null } },
    ],
  })
  await router.push(path)
  const app = createSSRApp(() => h(RouterView))
  app.use(router).use(Antd).use(VueQueryPlugin, { queryClient: client })
  app.use(
    createI18n({
      legacy: false,
      locale: 'en',
      missingWarn: false,
      fallbackWarn: false,
      messages: {
        en: {
          plugins: {
            demo15: {
              config: { Run: { Retries: { label: 'Retry count' } }, tasks: { label: 'Tasks' } },
            },
          },
        },
      },
    })
  )
  const edit = new Map<unknown, (value: unknown) => void>()
  let submit!: () => void
  app.mixin({
    created() {
      if (this.$options.__name === 'DeclarativeControl') {
        edit.set(this.$props.modelValue, value => this.$emit('update:modelValue', value))
      }
      if (this.$options.name === 'AButton' && this.$props.type === 'primary') {
        submit = () => this.$emit('click')
      }
    },
  })
  const html = await renderToString(app)
  async function save() {
    submit()
    await vi.waitFor(() => expect(message.success).toHaveBeenCalled())
  }
  return { html, edit, save }
}

describe('Demo15 配置编辑器', () => {
  const scriptPath = '/scripts/s/edit/plugin/Demo15'
  const userPath = '/scripts/s/users/u/edit/plugin/Demo15'

  const wheel = {
    pageId: 'plan',
    pluginName: 'demo15',
    revision: 'r1',
    activationId: 'activation',
    artifacts: {
      'qt-quick': { entry: 'plan.qml', panelApi: 1 },
      web: { entry: 'plan.html', panelApi: 1 },
    },
  }

  it('没有声明式字段的托管仍挂载 wheel 界面', async () => {
    const state = detail('s', {}, {})
    vi.spyOn(Service, 'getScriptApiScriptsGetPost').mockResolvedValue({
      ...state,
      ui: { ...state.ui, frontendSurfaces: { script: wheel } },
    })
    const view = await editorView(scriptPath, client)
    view.mount()
    try {
      await vi.waitFor(() =>
        expect(view.find('iframe')?.props).toMatchObject({
          sandbox: 'allow-scripts allow-forms',
          referrerpolicy: 'no-referrer',
        })
      )
      expect(view.find('iframe')?.props.src).toMatch(/\/plan\.html#/)
      expect(view.find('input')).toBeUndefined()
    } finally {
      view.app.unmount()
    }
  })

  it.each([
    'missing web artifact',
    'incompatible panelApi',
    'iframe load failure',
    'handshake timeout',
  ])('uses the declarative editor after %s', async reason => {
    const fallback = '插件界面不可用，已切换到内置编辑器。'
    const state = detail(
      'p',
      { First: { Count: 1 } },
      {
        First: [{ field: 'Count', editable: true, component: 'number' }],
      }
    )
    const mount: FrontendSurfaceMount = { ...wheel, artifacts: { ...wheel.artifacts } }
    if (reason === 'missing web artifact') {
      delete mount.artifacts.web
    } else if (reason === 'incompatible panelApi') {
      mount.artifacts.web = { ...mount.artifacts.web, panelApi: 2 }
    }
    vi.spyOn(Service, 'getPlanApiPlanGetPost').mockResolvedValue({
      ...state,
      ui: { ...state.ui, frontendSurfaces: { plan: mount } },
    })
    if (reason === 'handshake timeout') vi.useFakeTimers()
    const view = await editorView('/plan', client)
    view.mount()
    try {
      if (reason === 'iframe load failure' || reason === 'handshake timeout') {
        await vi.waitFor(() => expect(view.find('iframe')).toBeDefined())
        if (reason === 'iframe load failure') await fire(view.find('iframe')!, 'onError')
        else await vi.advanceTimersByTimeAsync(10_000)
      }
      await vi.waitFor(() => expect(view.find('input')).toBeDefined())
      expect(view.find('iframe')).toBeUndefined()
      expect(view.find('aside')?.props).toMatchObject({ type: 'info', message: fallback })
    } finally {
      view.app.unmount()
      vi.useRealTimers()
    }
  })

  it('Demo15 计划用当前激活标识保存单字段，保留失败草稿并阻止锁定写入', async () => {
    const state = detail(
      'p',
      { First: { Count: 1 }, Second: { Count: 2 }, Third: { Count: 3 } },
      {
        First: [{ field: 'Count', editable: true }],
        Second: [
          { field: 'Count', editable: true },
          { field: 'Run', component: 'button', state: TriggerUiState.IDLE, editable: true },
        ],
        Third: [{ field: 'Count', editable: true }],
      }
    )
    const config = {
      ...state,
      ui: { ...state.ui, locked: false, frontendSurfaces: { plan: wheel } },
    }
    const read = vi
      .spyOn(Service, 'getPlanApiPlanGetPost')
      .mockResolvedValue(structuredClone(config))
    const writes: unknown[] = []
    const headers = {
      'X-Plugin-Ui-Provider': 'demo15',
      'X-Plugin-Ui-Activation': 'activation',
      'X-Plugin-Ui-Page': 'plan',
    }
    let fail = false
    const network = vi.spyOn(axios, 'request').mockImplementation(async request => {
      expect(request.headers).toMatchObject(headers)
      const path = new URL(request.url!, 'http://mas.test').pathname
      writes.push({ path, body: request.data })
      if (path === '/api/config/triggers/write')
        return { status: 200, data: { code: 200, data: 'job' } }
      if (fail)
        return {
          status: 200,
          data: { code: 422, message: 'Invalid count', fieldErrors: { 'Second.Count': 'invalid' } },
        }
      const body = request.data as { data: SettingsValues }
      config.data.p.Second.Count = body.data.Second.Count
      read.mockResolvedValue(structuredClone(config))
      return { status: 200, data: { code: 200 } }
    })
    const actionState = vi
      .spyOn(Service, 'getConfigTriggerResultApiConfigTriggersResultPost')
      .mockResolvedValue({ code: 200, data: { state: BackgroundTaskState.SUCCEEDED } })
    const view = await editorView('/plan', client)
    view.mount()
    const frame = await vi
      .waitFor(() => expect(view.find('iframe')).toBeDefined())
      .then(() => pluginUiFrame(view.find('iframe')!))
    const rpc = async (action: string, params?: object) => {
      const id = frame.request(action, params)
      await vi.waitFor(() => expect(frame.replies.has(id), `${action} #${id}`).toBe(true))
      return frame.replies.get(id)!
    }
    const change = (group: string, value: number) => ({ group, field: 'Count', value })
    try {
      frame.ready()
      expect(frame.url.pathname).toBe('/api/plugin/demo15/ui/r1/plan.html')
      expect(
        await rpc('saveConfig', { phase: 'draft', changes: [change('First', 4)] })
      ).toMatchObject({ result: { ok: true } })
      expect(network).not.toHaveBeenCalled()
      expect(
        await rpc('saveConfig', { phase: 'commit', changes: [change('Second', 5)] })
      ).toMatchObject({ result: { ok: true } })
      expect(writes).toEqual([
        { path: '/api/plan/update', body: { planId: 'p', data: { Second: { Count: 5 } } } },
      ])
      fail = true
      expect(
        await rpc('saveConfig', { phase: 'commit', changes: [change('Second', 6)] })
      ).toMatchObject({
        result: {
          ok: false,
          code: '422',
          message: 'Invalid count',
          fieldErrors: { 'Second.Count': 'invalid' },
        },
      })
      expect(await rpc('readConfig')).toMatchObject({
        result: { config: { First: { Count: 4 }, Second: { Count: 6 } } },
      })
      expect(await rpc('runAction', { group: 'Second', field: 'Run', value: true })).toMatchObject({
        result: 'success',
      })
      actionState.mockResolvedValue({ code: 200, data: { state: BackgroundTaskState.CANCELLED } })
      expect(await rpc('runAction', { group: 'Second', field: 'Run', value: true })).toMatchObject({
        result: 'cancelled',
      })
      expect(writes.slice(2)).toEqual(
        Array.from({ length: 2 }, () => ({
          path: '/api/config/triggers/write',
          body: { configUid: 'p', group: 'Second', field: 'Run', value: true },
        }))
      )
      config.ui.locked = true
      config.data.p.Third.Count = 8
      read.mockResolvedValue(structuredClone(config))
      await client.refetchQueries({ queryKey: ['declarative-config'] })
      await vi.waitFor(() => {
        expect(frame.events).toContainEqual({
          event: 'configReloaded',
          payload: { config: { First: { Count: 4 }, Second: { Count: 6 }, Third: { Count: 8 } } },
        })
        expect(frame.events).toContainEqual({
          event: 'stateChanged',
          payload: expect.objectContaining({ locked: true, busy: false }),
        })
      })
      network.mockClear()
      expect(
        await rpc('saveConfig', { phase: 'commit', changes: [change('Second', 7)] })
      ).toMatchObject({ error: 'read_only' })
      expect(network).not.toHaveBeenCalled()
    } finally {
      frame.close()
      view.app.unmount()
    }
  })
  it('普通保存也要等当前插件的新选项可用并修正失效选择', async () => {
    const state = detail(
      's',
      { Setup: { Region: 'cn', Profile: 'cn-profile' } },
      {
        Setup: [
          { field: 'Region' },
          {
            field: 'Profile',
            component: 'select',
            option_source: 'profiles',
            depends_on: { region: 'Setup.Region' },
          },
        ],
      }
    )
    vi.spyOn(Service, 'getScriptApiScriptsGetPost').mockResolvedValue({
      ...state,
      ui: { ...state.ui, pluginName: 'demo15' },
    })
    vi.spyOn(axios, 'request').mockImplementation(async config => {
      const url = new URL(config.url!, 'http://mas.test')
      expect(url.pathname).toBe('/api/plugin/demo15/options/profiles')
      const value = url.searchParams.get('region') + '-profile'
      return { status: 200, data: { code: 200, data: [{ value }] } }
    })
    const write = vi
      .spyOn(Service, 'updateScriptApiScriptsUpdatePost')
      .mockResolvedValue({ code: 200 })
    const view = await editorView(scriptPath, client)
    view.mount()
    try {
      await vi.waitFor(() =>
        expect(view.find('select')?.props.options).toMatchObject([{ value: 'cn-profile' }])
      )
      await fire(view.find('input')!, 'onUpdate:value', 'jp')
      await vi.waitFor(() => expect(view.find('p', 'core.plugins.optionUnavailable')).toBeDefined())
      expect(view.find('button', 'core.plugins.save')!.props.disabled).toBe(true)
      expect(view.find('select')!.props.value).toBe('cn-profile')
      await fire(view.find('select')!, 'onUpdate:value', 'jp-profile')
      expect(view.find('button', 'core.plugins.save')!.props.disabled).toBe(false)
      await view.click('core.plugins.save')
      await vi.waitFor(() => expect(view.find('input')!.props.disabled).toBe(false))
      expect(write.mock.calls).toEqual([
        [{ scriptId: 's', data: { Setup: { Region: 'jp', Profile: 'jp-profile' } } }],
      ])
    } finally {
      view.app.unmount()
    }
  })
  it('行内动作使用本配置的可见触发器，放弃路径草稿后回读并保留其他修改', async () => {
    const hints = {
      Info: [
        { field: 'Path', component: 'path', action_ref: 'Info.Discover' },
        { field: 'Name' },
        { field: 'Discover', component: 'button', editable: true },
      ],
    }
    const read = vi
      .spyOn(Service, 'getScriptApiScriptsGetPost')
      .mockResolvedValue(detail('s', { Info: { Path: 'old', Name: 'one' } }, hints))
    const command = vi
      .spyOn(Service, 'writeConfigTriggerApiConfigTriggersWritePost')
      .mockResolvedValue({ code: 200, data: 'job' })
    vi.spyOn(Service, 'getConfigTriggerResultApiConfigTriggersResultPost').mockResolvedValue({
      code: 200,
      data: { state: BackgroundTaskState.SUCCEEDED },
    })
    const confirm = vi.fn().mockResolvedValueOnce(false).mockResolvedValueOnce(true)
    vi.spyOn(confirmation, 'useConfirm').mockReturnValue({ confirm, alert: vi.fn() })
    const view = await editorView(scriptPath, client)
    view.mount()
    try {
      await vi.waitFor(() => expect(view.find('button', 'Discover')).toBeDefined())
      const owner = view
        .all()
        .find(node => node.tag === 'div' && node.props['aria-label'] === 'Path')!
      const triggers = view
        .all()
        .filter(node => node.tag === 'button' && view.text(node) === 'Discover')
      expect(triggers).toHaveLength(1)
      expect(view.all(owner)).toContain(triggers[0])
      const input = (value: string) =>
        view.all().find(node => node.tag === 'input' && node.props.value === value)!
      await fire(input('old'), 'onUpdate:value', 'draft')
      await fire(input('one'), 'onUpdate:value', 'unsaved')
      await view.click('Discover')
      await vi.waitFor(() => expect(confirm).toHaveBeenCalledOnce())
      expect(command).not.toHaveBeenCalled()
      expect(input('draft')).toBeDefined()
      read.mockResolvedValue(detail('s', { Info: { Path: 'discovered', Name: 'one' } }, hints))
      await view.click('Discover')
      await vi.waitFor(() => expect(input('discovered')).toBeDefined())
      expect(command).toHaveBeenCalledWith({
        configUid: 's',
        group: 'Info',
        field: 'Discover',
        value: true,
      })
      expect(input('unsaved')).toBeDefined()
      client.setQueryData(['config-triggers', 'active'], {
        code: 200,
        data: [{ configUid: 's', group: 'Info', field: 'Discover' }],
      })
      await vi.waitFor(() => expect(view.find('button', 'Discover')!.props.disabled).toBe(true))
    } finally {
      view.app.unmount()
    }
  })
  it('托管进入和保存后归档，强制恢复成功才回读并替换草稿', async () => {
    const state = detail(
      's',
      { Run: { Retries: 1 } },
      { Run: [{ field: 'Retries', component: 'number' }] }
    )
    const pool = { key: 'run', kind: BackupTargetHint.kind.SCRIPT }
    const get = vi
      .spyOn(Service, 'getScriptApiScriptsGetPost')
      .mockResolvedValue({ ...state, ui: { ...state.ui, backupTargets: [pool] } })
    const ensure = vi
      .spyOn(Service, 'ensureConfigBackupApiApiScriptsBackupEnsurePost')
      .mockResolvedValue({ code: 200, created: true, time: 't' })
    const time = '20261125_101112'
    const list = vi
      .spyOn(Service, 'listConfigBackupsApiApiScriptsBackupListGet')
      .mockResolvedValue({ code: 200, data: [{ time }] })
    const restore = vi
      .spyOn(Service, 'restoreConfigBackupApiApiScriptsBackupRestorePost')
      .mockResolvedValueOnce({ code: 409, target: 'run' })
      .mockResolvedValue({ code: 200, target: 'run' })
    vi.spyOn(Service, 'updateScriptApiScriptsUpdatePost').mockResolvedValue({ code: 200 })
    const confirm = vi.fn<(options: ConfirmOptions) => Promise<boolean>>()
    vi.spyOn(confirmation, 'useConfirm').mockReturnValue({ confirm, alert: vi.fn() })
    const view = await editorView(scriptPath, client)
    view.stub({ AListItem: 'div', ASegmented: 'div', NoData: 'div' })
    view.app.component(
      'AModal',
      defineComponent({
        props: ['open'],
        setup:
          (props, { slots }) =>
          () =>
            props.open && h('dialog', slots.default?.()),
      })
    )
    view.app.component(
      'AList',
      defineComponent({
        props: ['dataSource'],
        setup:
          (props, { slots }) =>
          () =>
            h(
              'div',
              props.dataSource.map((item: unknown) => slots.renderItem?.({ item }))
            ),
      })
    )
    view.mount()
    try {
      await vi.waitFor(() =>
        expect(ensure).toHaveBeenCalledWith({ scriptId: 's', userId: null, target: 'run' })
      )
      await fire(view.find('input')!, 'onUpdate:value', 2)
      await view.click('core.plugins.save')
      await vi.waitFor(() => {
        expect(ensure).toHaveBeenCalledTimes(2)
        expect(view.find('input')!.props.disabled).toBe(false)
      })
      await fire(view.find('input')!, 'onUpdate:value', 9)
      await view.click('core.edit.configRestoreTitle')
      await vi.waitFor(() =>
        expect(view.find('button', 'core.edit.configRestoreAction')).toBeDefined()
      )
      expect(list).toHaveBeenCalledWith('s', 'run', null)
      await view.click('core.edit.configRestoreAction')
      expect(restore).not.toHaveBeenCalled()
      await confirm.mock.lastCall![0].onOk!()
      expect(view.find('input')!.props.value).toBe(9)
      const updated = detail('s', { Run: { Retries: 6 } }, state.ui.hints)
      get.mockResolvedValue({ ...updated, ui: { ...updated.ui, backupTargets: [pool] } })
      await confirm.mock.lastCall![0].onOk!()
      expect(restore).toHaveBeenLastCalledWith({
        scriptId: 's',
        userId: null,
        target: 'run',
        time,
        force: true,
      })
      await vi.waitFor(() => expect(view.find('input')!.props.value).toBe(6))
      expect(view.find('button', 'core.plugins.save')!.props.disabled).toBe(true)
    } finally {
      view.app.unmount()
    }
  })

  it('只有归档池的配置仍有恢复入口', async () => {
    const state = detail('s', {}, {})
    vi.spyOn(Service, 'getScriptApiScriptsGetPost').mockResolvedValue({
      ...state,
      ui: { ...state.ui, backupTargets: [{ key: 'archive', kind: BackupTargetHint.kind.SCRIPT }] },
    })
    vi.spyOn(Service, 'ensureConfigBackupApiApiScriptsBackupEnsurePost').mockResolvedValue({
      code: 200,
      created: false,
      time: '',
    })
    const { html } = await render(scriptPath)
    const buttons = html.match(/<button\b[^>]*>[\s\S]*?<\/button>/g) ?? []
    expect(buttons.some(button => button.includes('core.edit.configRestoreTitle'))).toBe(true)
    expect(html).not.toContain('core.plugins.noConfigFields')
  })

  it.each([
    ['script', 'view'],
    ['user', 'config'],
  ] as const)('原生 %s 会话使用当前目标，停止时执行对应的关闭或保存动作', async (mode, session) => {
    const id = mode === 'script' ? 's' : 'u'
    const state = detail(id, {}, {})
    const response = { ...state, ui: { ...state.ui, nativeSession: session } }
    const read =
      mode === 'script'
        ? vi.spyOn(Service, 'getScriptApiScriptsGetPost')
        : vi.spyOn(Service, 'getUserApiScriptsUserGetPost')
    read.mockResolvedValue(response)
    const start = vi
      .spyOn(taskApi, 'requestScriptConfigStart')
      .mockResolvedValue({ code: 200, taskId: 'session' })
    const stop = vi.spyOn(taskApi, 'stopNativeConfig').mockResolvedValue({ code: 200 })
    const view = await editorView(mode === 'script' ? scriptPath : userPath, client)
    view.mount()
    try {
      const launch =
        session === 'view' ? 'core.scheduler.mode.scriptView' : 'core.edit.openConfigWindow'
      await vi.waitFor(() => expect(view.find('button', launch)).toBeDefined())
      await view.click(launch)
      expect(start).toHaveBeenCalledWith(id, session === 'view', mode, undefined)
      client.setQueryData(
        [
          'script-config-lock',
          mode === 'script' ? { scriptId: 's' } : { scriptId: 's', userId: 'u' },
        ],
        { code: 200, locked: true }
      )
      const stopLabel =
        session === 'view' ? 'core.edit.generalViewClose' : 'core.scripts.mask.saveConfig'
      await vi.waitFor(() => expect(view.all().some(node => node.props.inert === true)).toBe(true))
      const locked = view.all().find(node => node.props.inert === true)!
      const button = view.find('button', stopLabel)!
      expect(view.all(locked)).not.toContain(button)
      expect(button.props.disabled).toBeFalsy()
      read.mockResolvedValue(
        detail(id, { Run: { Name: 'after native' } }, { Run: [{ field: 'Name' }] })
      )
      await view.click(stopLabel)
      await vi.waitFor(() =>
        expect(stop).toHaveBeenCalledWith('session', session === 'view' ? 'close' : 'save')
      )
      await vi.waitFor(() => expect(view.find('input')?.props.value).toBe('after native'))
      expect(view.find('button', stopLabel)).toBeUndefined()
    } finally {
      view.app.unmount()
    }
  })
  it('读取托管声明和翻译，保存修改时省略掩码令牌', async () => {
    const get = vi.spyOn(Service, 'getScriptApiScriptsGetPost').mockResolvedValue(
      detail(
        's',
        { Run: { Retries: 1, Token: masked } },
        {
          Run: [
            { field: 'Retries', component: 'number' },
            { field: 'Token', secret: true, masked: true },
          ],
        }
      )
    )
    const update = vi
      .spyOn(Service, 'updateScriptApiScriptsUpdatePost')
      .mockResolvedValue({ code: 200 })
    const { html, edit, save } = await render(scriptPath)
    expect(get).toHaveBeenCalledWith({ scriptId: 's' })
    expect(html).toContain('Retry count')
    expect(html).not.toContain(masked)
    edit.get(1)!(3)
    await save()
    expect(update).toHaveBeenCalledWith({ scriptId: 's', data: { Run: { Retries: 3 } } })
  })

  it('编辑所选账号时只写入修改的凭据', async () => {
    const get = vi
      .spyOn(Service, 'getUserApiScriptsUserGetPost')
      .mockResolvedValue(
        detail(
          'u',
          { Info: { Id: 'alice', Password: masked } },
          { Info: [{ field: 'Id' }, { field: 'Password', masked: true, secret: true }] }
        )
      )
    const update = vi
      .spyOn(Service, 'updateUserApiScriptsUserUpdatePost')
      .mockResolvedValue({ code: 200 })
    const { html, edit, save } = await render(userPath)
    expect(get).toHaveBeenCalledWith({ scriptId: 's', userId: 'u' })
    expect(html).toContain('value="alice"')
    edit.get('alice')!('bob')
    await save()
    expect(update).toHaveBeenCalledWith({
      scriptId: 's',
      userId: 'u',
      data: { Info: { Id: 'bob' } },
    })
  })

  it('转置计划的列对应配置组，修改第二列只更新 Second.Count', async () => {
    const count = { field: 'Count', component: 'number' }
    const get = vi
      .spyOn(Service, 'getPlanApiPlanGetPost')
      .mockResolvedValue(
        detail(
          'p',
          { First: { Count: 2 }, Second: { Count: 5 } },
          { First: [count], Second: [count] },
          planTables
        )
      )
    const update = vi.spyOn(Service, 'updatePlanApiPlanUpdatePost').mockResolvedValue({ code: 200 })
    const { html, edit, save } = await render('/plan')
    expect(get).toHaveBeenCalledWith({ planId: 'p' })
    expect(html).toContain('Tasks')
    expect(html.match(/<thead\b[\s\S]*?<\/thead>/)?.[0]).toMatch(/First[\s\S]*Second/)
    edit.get(5)!(7)
    await save()
    expect(update).toHaveBeenCalledWith({ planId: 'p', data: { Second: { Count: 7 } } })
  })

  it('整批校验失败时保留两个编辑值，把错误放在被拒字段内', async () => {
    vi.spyOn(Service, 'getScriptApiScriptsGetPost').mockResolvedValue(
      detail(
        's',
        { Run: { Retries: 1, Mode: 'once' } },
        { Run: [{ field: 'Retries', component: 'number' }, { field: 'Mode' }] }
      )
    )
    const update = vi.spyOn(Service, 'updateScriptApiScriptsUpdatePost').mockResolvedValue({
      code: 422,
      message: 'Invalid settings',
      fieldErrors: { 'Run.Retries': 'Must be nonnegative' },
    })
    const { html } = await render(scriptPath, async editor => {
      editor.draft.update('Run', 'Retries', -1)
      editor.draft.update('Run', 'Mode', 'repeat')
      expect(await editor.save()).toBe(false)
    })
    expect(update).toHaveBeenCalledWith({
      scriptId: 's',
      data: { Run: { Retries: -1, Mode: 'repeat' } },
    })
    const field = html.slice(
      html.indexOf('aria-label="Retry count"'),
      html.indexOf('aria-label="Mode"')
    )
    expect(field).toContain('value="-1"')
    expect(field).toMatch(/role="alert"[^>]*>Must be nonnegative</)
    expect(html).toContain('value="repeat"')
  })

  it('锁定的账号字段保留原值并禁用输入', async () => {
    vi.spyOn(Service, 'getUserApiScriptsUserGetPost').mockResolvedValue(
      detail('u', { Info: { Id: 'alice' } }, { Info: [{ field: 'Id', editable: false }] })
    )
    const { html } = await render(userPath)
    expect(html).toMatch(/<input\b(?=[^>]*\bdisabled\b)(?=[^>]*value="alice")[^>]*>/)
  })
})
