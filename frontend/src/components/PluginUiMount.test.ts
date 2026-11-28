// @vitest-environment vue-client
import { afterEach, describe, expect, it, vi } from 'vite-plus/test'
import { defineComponent, h, nextTick, shallowRef } from 'vue'
import { createI18n } from 'vue-i18n'
import { TriggerUiState } from '@/api'
import type {
  PluginUiEditor,
  PluginUiSaveResult,
  PluginUiTarget,
} from '@/composables/usePluginUiBridge'
import { pluginPanelTheme } from '@/composables/pluginPanelTheme'
import { deferred, testView } from '../../tests/vueRenderer'
import { pluginUiFrame } from '../../tests/pluginUiFrame'
import PluginUiMount from './PluginUiMount.vue'

const socket = vi.hoisted(() => ({
  disconnected: vi.fn(),
  capabilities: vi.fn(),
}))
vi.mock('@/services/websocket/connection', () => ({
  connectionState: () => ({ value: 'open' }),
  onConnected: () => () => {},
  onDisconnected: socket.disconnected,
}))
vi.mock('@/services/websocket/subscriptions', () => ({
  subscribe: socket.capabilities,
  unsubscribe: vi.fn(),
}))
const confirm = vi.hoisted(() => vi.fn())
vi.mock('@/composables/useConfirm', () => ({ useConfirm: () => ({ confirm }) }))
const lightTheme = { mode: 'light', tokens: { '--mas-bg-base': '#fff' } } as const

afterEach(() => vi.unstubAllGlobals())

function mountWheel() {
  vi.stubGlobal('window', new EventTarget())
  pluginPanelTheme.value = lightTheme
  socket.disconnected.mockReturnValue(() => {})
  const target = shallowRef<PluginUiTarget>({
    kind: 'plan',
    configUid: 'uid',
    planId: 'p',
    scriptId: null,
    userId: null,
  })
  const editor = shallowRef<PluginUiEditor>({
    locale: 'en-US',
    locked: false,
    busy: false,
    groups: [
      {
        name: 'Second',
        hints: [
          { field: 'Count', editable: true },
          { field: 'Password', editable: true, secret: true },
          { field: 'Masked', masked: true },
          { field: 'Run', editable: true, component: 'button', state: TriggerUiState.IDLE },
        ],
      },
    ],
    values: { Second: { Count: 3, Hidden: 'hi', Password: 'secret', Masked: 'masked' } },
    configRevision: 0,
    save: vi.fn().mockResolvedValue({ ok: true }),
    runAction: vi.fn().mockResolvedValue('success'),
    notify: vi.fn(),
  })
  const mount = {
    pageId: 'plan',
    artifacts: { web: { entry: 'plans/main.html', panelApi: 1 } },
    entry: 'plans/main.html',
    revision: 'rev',
    activationId: 'active',
    pluginName: 'demo15',
  }
  const refresh = vi.fn().mockResolvedValue(true)
  const view = testView(
    defineComponent(
      () => () => h(PluginUiMount, { target: target.value, mount, editor: editor.value, refresh })
    )
  )
  view.stub({ ASpin: 'div', AAlert: 'aside' })
  view.app.use(createI18n({ legacy: false, locale: 'en', missingWarn: false }))
  view.mount()
  return { view, target, editor, refresh }
}

describe('wheel iframe', () => {
  it('authenticates ready and requests, and projects only visible non-secret fields', async () => {
    const { view, target } = mountWheel()
    await nextTick()
    const frame = view.find('iframe')!
    const child = pluginUiFrame(frame)
    try {
      expect(frame.props).toMatchObject({
        sandbox: 'allow-scripts allow-forms',
        referrerpolicy: 'no-referrer',
      })
      expect(child.url.pathname).toBe('/api/plugin/demo15/ui/rev/plans/main.html')
      expect(child.envelope.mountToken).toMatch(/^[0-9a-f]{32}$/)
      expect(child.envelope.target).toEqual(target.value)
      // 用后续有效请求作为屏障，确认先前发给未握手端口的写入没有执行。
      const wrongWindow = child.request('resize', { height: 333 })
      child.ready({}, 'null', {})
      const wrongOrigin = child.request('resize', { height: 444 })
      child.ready({}, 'http://mas.test')
      const wrongToken = child.request('resize', { height: 555 })
      child.ready({ mountToken: 'bad' })
      const wrongTarget = child.request('resize', { height: 666 })
      child.ready({ target: { ...target.value, configUid: 'other' } })
      // 握手前端口中的消息会被结构化克隆并排队，先使用其它端口测试拒绝。
      child.close()
      const active = pluginUiFrame(frame)
      try {
        active.ready()
        const unauthenticated = active.request('resize', { height: 999 }, { source: 'other' })
        const wrongRequestTarget = active.request('resize', { height: 999 }, { target: {} })
        const good = active.request('readConfig')
        await vi.waitFor(() =>
          expect(active.replies.get(good)?.result).toEqual({
            target: target.value,
            surface: 'plan',
            locale: 'en-US',
            locked: false,
            busy: false,
            theme: lightTheme,
            config: { Second: { Count: 3 } },
          })
        )
        expect([...active.replies.keys()]).toEqual([good])
        expect(
          [wrongWindow, wrongOrigin, wrongToken, wrongTarget].some(id => child.replies.has(id))
        ).toBe(false)
        expect(active.replies.has(unauthenticated)).toBe(false)
        expect(active.replies.has(wrongRequestTarget)).toBe(false)
        expect(frame.props.style).toEqual({ height: '320px' })
      } finally {
        active.close()
      }
    } finally {
      child.close()
      view.app.unmount()
    }
  })

  it.each(['settings', 'notification'] as const)(
    'binds dialogs to the active %s target',
    async kind => {
      const { view, target, editor } = mountWheel()
      target.value = {
        kind,
        scriptId: null,
        userId: null,
        planId: null,
        configUid: 'uid',
        ...(kind === 'settings' ? { pluginId: 'record' } : { channelId: 'mail' }),
      }
      await nextTick()
      const child = pluginUiFrame(view.find('iframe')!)
      try {
        child.ready()
        const ask = async (action: string, params: object) => {
          const id = child.request(action, params)
          await vi.waitFor(() => expect(child.replies.has(id)).toBe(true))
          return child.replies.get(id)
        }
        const foreign = child.request(
          'getContext',
          {},
          { target: { ...target.value, extra: true } }
        )
        expect((await ask('getContext', {}))?.result).toMatchObject({
          surface: kind,
          target: target.value,
        })
        expect(child.replies.has(foreign)).toBe(false)
        expect((await ask('pickPath', { mode: 'file' }))?.result).toEqual({
          ok: false,
          code: 'unavailable',
        })
        const selectFile = vi.fn().mockResolvedValue(['chosen'])
        Object.assign(window, {
          electronAPI: { selectFile, selectFolder: vi.fn().mockResolvedValue(null) },
        })
        expect(
          (await ask('pickPath', { mode: 'file', title: 'Pick', defaultPath: 'here' }))?.result
        ).toEqual({ cancelled: false, path: 'chosen' })
        expect(selectFile).toHaveBeenCalledWith(undefined, { title: 'Pick', defaultPath: 'here' })
        expect((await ask('pickPath', { mode: 'folder' }))?.result).toEqual({
          cancelled: true,
          path: null,
        })
        expect(
          (await ask('pickPath', { mode: 'file', filters: [{ name: 'File', extensions: [42] }] }))
            ?.error
        ).toBe('invalid_params')
        confirm.mockResolvedValueOnce(false)
        expect((await ask('confirm', { message: 'Continue?', danger: true }))?.result).toEqual({
          confirmed: false,
        })
        expect(confirm).toHaveBeenCalledWith(
          expect.objectContaining({ description: 'Continue?', tone: 'danger' })
        )
        expect((await ask('confirm', { message: ' '.repeat(501) }))?.error).toBe('invalid_params')
        editor.value = { ...editor.value, locked: true }
        expect((await ask('pickPath', { mode: 'file' }))?.error).toBe('read_only')
        expect((await ask('confirm', { message: 'Continue?' }))?.error).toBe('read_only')
      } finally {
        child.close()
        view.app.unmount()
      }
    }
  )

  it('pushes lock, busy, locale, theme and projected config changes without a new request', async () => {
    const { view, editor } = mountWheel()
    await nextTick()
    const child = pluginUiFrame(view.find('iframe')!)
    try {
      child.ready()
      const theme = { mode: 'dark', tokens: { '--mas-bg-base': '#141414' } } as const
      pluginPanelTheme.value = theme
      editor.value = { ...editor.value, locked: true, busy: true, locale: 'ja-JP' }
      await vi.waitFor(() =>
        expect(child.events).toContainEqual({
          event: 'stateChanged',
          payload: { locked: true, busy: true, locale: 'ja-JP', theme },
        })
      )
      editor.value = {
        ...editor.value,
        configRevision: 1,
        values: { Second: { Count: 7, Masked: 'updated secret' } },
      }
      await vi.waitFor(() =>
        expect(child.events.at(-1)).toEqual({
          event: 'configReloaded',
          payload: { config: { Second: { Count: 7 } } },
        })
      )
      expect(child.replies.size).toBe(0)
    } finally {
      child.close()
      view.app.unmount()
    }
  })

  it('deduplicates the latest 512 request IDs and evicts the oldest', async () => {
    const { view } = mountWheel()
    await nextTick()
    const child = pluginUiFrame(view.find('iframe')!)
    try {
      child.ready()
      for (let id = 0; id < 512; id++) child.request('resize', { height: 350 }, {}, id)
      child.request('resize', { height: 500 }, {}, 0)
      const newest = child.request('resize', { height: 400 }, {}, 512)
      await vi.waitFor(() => expect(child.replies.get(newest)?.result).toBe(400))
      expect(child.replies.get(0)?.result).toBe(350)
      child.request('resize', { height: 500 }, {}, 1)
      child.request('resize', { height: 600 }, {}, 0)
      await vi.waitFor(() => expect(child.replies.get(0)?.result).toBe(600))
      expect(child.replies.get(1)?.result).toBe(350)
    } finally {
      child.close()
      view.app.unmount()
    }
  })

  it('enforces trigger, toast and size allowlists and rejects duplicate request IDs', async () => {
    const { view, editor } = mountWheel()
    await nextTick()
    const frame = view.find('iframe')!
    const child = pluginUiFrame(frame)
    try {
      child.ready()
      const run = child.request('runAction', { group: 'Second', field: 'Run', value: true })
      child.request('runAction', { group: 'Second', field: 'Run', value: true }, {}, run)
      const undeclared = child.request('runAction', {
        group: 'Second',
        field: 'Count',
        value: true,
      })
      const hidden = child.request('saveConfig', {
        phase: 'commit',
        changes: [{ group: 'Second', field: 'Hidden', value: 'new' }],
      })
      const toast = child.request('notify', { severity: 'info', message: '<b>plain text</b>' })
      const tooLong = child.request('notify', { severity: 'success', message: 'x'.repeat(501) })
      const severity = child.request('notify', { severity: 'debug', message: 'hi' })
      const size = child.request('resize', { height: 10000 })
      const invalid = child.request('resize', { height: Infinity })
      const unknown = child.request('openUrl', {})
      await vi.waitFor(() => expect(child.replies.get(unknown)?.error).toBe('unknown_action'))
      expect(child.replies.get(run)?.result).toBe('success')
      expect(child.replies.get(undeclared)?.error).toBe('invalid_action')
      expect(editor.value.runAction).toHaveBeenCalledOnce()
      expect(child.replies.get(hidden)?.error).toBe('invalid_changes')
      expect(editor.value.save).not.toHaveBeenCalled()
      expect(editor.value.notify).toHaveBeenCalledExactlyOnceWith('info', '<b>plain text</b>')
      expect(child.replies.get(toast)?.result).toBe(true)
      expect(child.replies.get(tooLong)?.error).toBe('invalid_message')
      expect(child.replies.get(severity)?.error).toBe('invalid_severity')
      expect(child.replies.get(size)?.result).toBe(4000)
      expect(child.replies.get(invalid)?.error).toBe('invalid_height')
      expect(frame.props.style).toEqual({ height: '4000px' })
    } finally {
      child.close()
      view.app.unmount()
    }
  })

  it('revokes old channels after a target switch, capability update and disconnect', async () => {
    const { view, editor, target, refresh } = mountWheel()
    const saving = deferred<PluginUiSaveResult>()
    vi.mocked(editor.value.save).mockReturnValue(saving.promise)
    await nextTick()
    const oldFrame = view.find('iframe')!
    const old = pluginUiFrame(oldFrame)
    try {
      old.ready()
      const stale = old.request('saveConfig', {
        phase: 'commit',
        changes: [{ group: 'Second', field: 'Count', value: 7 }],
      })
      await vi.waitFor(() => expect(editor.value.save).toHaveBeenCalledOnce())
      target.value = { ...target.value, planId: 'other', configUid: 'other-uid' }
      await nextTick()
      saving.resolve({ ok: true })
      expect(view.find('iframe')).not.toBe(oldFrame)
      const current = pluginUiFrame(view.find('iframe')!)
      try {
        expect(current.envelope.mountToken).not.toBe(old.envelope.mountToken)
        current.ready()
        const context = current.request('getContext')
        await vi.waitFor(() =>
          expect(current.replies.get(context)?.result).toMatchObject({
            target: { planId: 'other', configUid: 'other-uid' },
          })
        )
        expect(old.replies.has(stale)).toBe(false)
        await socket.capabilities.mock.lastCall![1]()
        await nextTick()
        expect(refresh).toHaveBeenCalledOnce()
        expect(view.find('iframe')?.props.src).not.toBe(current.url.pathname + current.url.hash)
        socket.disconnected.mock.lastCall![0]()
        await nextTick()
        expect(view.find('iframe')).toBeUndefined()
      } finally {
        current.close()
      }
    } finally {
      old.close()
      view.app.unmount()
    }
  })
})
