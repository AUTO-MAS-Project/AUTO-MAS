import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { createSSRApp, h, onServerPrefetch } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import Antd, { message } from 'ant-design-vue'
import { Service, type DeclarativeConfigUi } from '@/api'
import { genericEditorRoutes } from '@/router/scriptEditorRoutes'
import ConfigEditor from './ConfigEditor.vue'
import * as editorModule from './useDeclarativeConfigEditor'
import type { SettingsValues } from './settings/usePluginSettingsDraft'

vi.mock('@/components/DocLink.vue', () => ({ default: { render: () => null } }))
vi.mock('@/components/GameBindingSection.vue', () => ({ default: { render: () => null } }))
vi.mock('@/services/websocket/subscriptions', () => ({ subscribe: vi.fn(), unsubscribe: vi.fn() }))
vi.mock('@/services/websocket/connection', () => ({ reconnectNow: vi.fn() }))
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
