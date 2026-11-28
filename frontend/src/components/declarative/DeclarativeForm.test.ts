// @vitest-environment vue-client
import { afterEach, beforeEach, describe, expect, it, vi } from 'vite-plus/test'
import { computed, createSSRApp, defineComponent, h, nextTick, reactive, ref } from 'vue'
import axios, { type AxiosResponse } from 'axios'
import { deferred, fire, testView } from '../../../tests/vueRenderer'
import { renderToString } from '@vue/server-renderer'
import { createI18n } from 'vue-i18n'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import Antd, { InputNumber } from 'ant-design-vue'
import zhCN from '../../../../res/i18n/zh_CN.json'
import { PathKind, Service } from '@/api'
import { useDeclarativeOptions } from '@/composables/useDeclarativeOptions'
import { usePluginSettingsDraft } from '@/views/plugins/settings/usePluginSettingsDraft'
import { requestApi } from '@/utils/apiResult'
import { declarativeTables } from './declarativeLayout'
import DeclarativeForm from './DeclarativeForm.vue'

beforeEach(() => vi.stubGlobal('window', {}))
afterEach(() => vi.unstubAllGlobals())

function mountForm(
  props: () => InstanceType<typeof DeclarativeForm>['$props'],
  client: QueryClient
) {
  const view = testView(defineComponent(() => () => h(DeclarativeForm, props())))
  view.stub({
    ASteps: 'steps',
    AFlex: 'div',
    ATable: 'table',
    AButton: 'button',
    AInput: 'input',
    AInputPassword: 'input',
    ASelect: 'select',
  })
  view.app.use(VueQueryPlugin, { queryClient: client }).use(
    createI18n({
      legacy: false,
      locale: 'en',
      missingWarn: false,
      fallbackWarn: false,
      messages: { en: { demo: { steps: { start: { label: 'Translated start' } } } } },
    })
  )
  view.mount()
  return view
}

/** 经插件表单进入真实 AntD 表格，用同一组数据验证表头、可见字段和编辑坐标。 */
async function render(
  transpose: boolean,
  includeOptionsGroup = true,
  errors: Record<string, string> = {
    'alpha.enabled': 'invalid switch',
    'alpha.missing_dir': 'missing directory',
  }
) {
  const update = vi.fn()
  const action = vi.fn()
  const edit = new Map<string, (value: string) => void>()
  const selectAction = new Map<string, () => void>()
  const pick = new Map<string, () => void>()
  const groups = [
    {
      name: 'alpha',
      hints: [
        { field: 'name' },
        { field: 'note' },
        { field: 'on', component: 'switch' },
        { field: 'count', component: 'number', min: 0, step: 0.1 },
        { field: 'extra' },
        { field: 'enabled', component: 'switch' },
        { field: 'locked', component: 'switch', editable: false },
        {
          field: 'layout',
          component: 'segmented',
          widget: 'segmented',
          options: [{ value: false }],
        },
        {
          field: 'single',
          component: 'switch',
          description: 'Check for updates before starting each new run.',
        },
        { field: 'notes', widget: 'textarea' },
        {
          field: 'exe',
          component: 'path',
          path_kind: PathKind.FILE,
          path_must_exist: true,
          path_extensions: ['exe'],
        },
        {
          field: 'missing_dir',
          component: 'path',
          path_kind: PathKind.FOLDER,
          path_must_exist: true,
        },
      ],
    },
    { name: 'beta', hints: [{ field: 'name' }] },
    {
      name: 'other',
      hints: [
        { field: 'device', component: 'select', endpoint: '/api/plugin/options/games' },
        {
          field: 'refresh',
          component: 'dropdown-button',
          options: [{ value: 'refresh', label: 'Refresh now' }],
        },
      ],
    },
  ]
  const values = {
    alpha: {
      name: 'A1',
      note: 'A2',
      extra: 'outside',
      on: true,
      count: 4,
      enabled: true,
      exe: 'old.exe',
    },
    beta: { name: 'B1', note: 'hidden' },
  }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, enabled: false } } })
  await client.prefetchQuery({
    queryKey: ['plugins', 'field-options', 'uid', '/api/plugin/options/games', []],
    queryFn: () => Promise.reject(new Error('options unavailable')),
  })
  const app = createSSRApp(() =>
    h(DeclarativeForm, {
      groups: includeOptionsGroup ? groups : groups.slice(0, 2),
      values,
      uid: 'uid',
      namespace: 'demo',
      scope: 'script',
      tables: declarativeTables({
        tables: [
          {
            key: 'matrix',
            rows: ['name', 'note', 'on', 'count'],
            columns: ['alpha', 'beta'],
            transpose,
          },
          { key: 'invisible', rows: ['absent'], columns: ['beta'], transpose: false },
        ],
      }),
      errors,
      'onUpdate:value': update,
      onAction: action,
    })
  )
  app.use(Antd)
  app.use(VueQueryPlugin, { queryClient: client })
  app.use(
    createI18n({
      legacy: false,
      locale: 'en',
      missingWarn: false,
      fallbackWarn: false,
      messages: {
        en: {
          demo: { matrix: { label: 'Matrix' }, alpha: { label: 'First', name: { label: 'Name' } } },
        },
      },
    })
  )
  app.component(
    'ADropdown',
    defineComponent({
      setup(_, { slots }) {
        return () => slots.overlay?.()
      },
    })
  )
  app.component(
    'AMenuItem',
    defineComponent({
      setup(_, { emit, slots }) {
        selectAction.set(String(slots.default?.()[0]?.children), () => emit('click'))
        return () => h('span', slots.default?.())
      },
    })
  )
  let numeric: Record<string, unknown> = {}
  let columns: Array<{ key: string; width?: number; align?: string }> = []
  app.mixin({
    created() {
      if (this.$options.name === 'AButton' && this.$attrs['aria-label'])
        pick.set(String(this.$attrs['aria-label']), () => this.$emit('click'))
      if (this.$options.name === 'AInputNumber') numeric = this.$props
      if (this.$options.name === 'ATable') columns = this.$props.columns
      if (this.$options.name === 'AInput') {
        edit.set(String(this.$props.value), value => this.$emit('update:value', value))
      }
    },
  })
  const html = await renderToString(app)
  client.clear()
  return { html, edit, update, action, selectAction, pick, columns, numeric }
}

describe('插件声明式表格与字段反馈', () => {
  it('运行次数支持步进和直接输入，零值显示不限制，普通数字保留小数步长', async () => {
    const values = reactive<Record<string, Record<string, unknown>>>({
      Run: { ProxyTimesLimit: 0, Ratio: 0.2 },
    })
    const client = new QueryClient()
    const view = testView(
      defineComponent(
        () => () =>
          h(DeclarativeForm, {
            uid: 'uid',
            namespace: 'demo',
            scope: 'script',
            groups: [
              {
                name: 'Run',
                hints: [
                  { field: 'ProxyTimesLimit', component: 'number', min: 0, max: 4, precision: 0 },
                  { field: 'Ratio', component: 'number', min: 0, max: 0.3, step: 0.1 },
                ],
              },
            ],
            values,
            'onUpdate:value': (group, field, value) => (values[group]![field] = value),
          })
      )
    )
    view.app.component('AInputNumber', InputNumber)
    view.app.use(VueQueryPlugin, { queryClient: client }).use(
      createI18n({
        legacy: false,
        locale: 'zh-CN',
        flatJson: true,
        missingWarn: false,
        messages: { 'zh-CN': { ...zhCN } },
      })
    )
    view.mount()
    const field = (name: string) => view.all().find(el => el.props['aria-label'] === name)!
    const spinbutton = (name: string) =>
      view.all(field(name)).find(el => el.props.role === 'spinbutton')!
    const button = (name: string, label: string) =>
      view.all(field(name)).find(el => el.tag === 'button' && el.props['aria-label'] === label)!
    const daily = zhCN['core.edit.runsPerDayThis']
    const input = spinbutton(daily)
    try {
      expect(input.props.value).toBe('0')
      expect(view.text(field(daily))).toContain('不限制')
      expect(button(daily, '减少').props.disabled).toBe(true)

      await fire(button(daily, '增加'), 'onClick')
      expect(input.props.value).toBe('1')
      expect(view.text(field(daily))).toContain('次 / 天')
      await fire(button(daily, '减少'), 'onClick')
      expect(spinbutton(daily)).toBe(input)
      expect(input.props.value).toBe('0')

      await fire(input, 'onFocus', {})
      expect(view.text(field(daily))).not.toContain('不限制')
      await fire(input, 'onInput', { target: { value: '3' } })
      await fire(input, 'onBlur', {})
      expect(values.Run?.ProxyTimesLimit).toBe(3)
      expect(input.props.value).toBe('3')

      await fire(button('Ratio', '增加'), 'onClick')
      expect(values.Run?.Ratio).toBe(0.3)
      expect(spinbutton('Ratio').props.value).toBe('0.3')
      expect(button('Ratio', '增加').props.disabled).toBe(true)
    } finally {
      view.app.unmount()
      client.clear()
    }
  })

  it('系统目录和文件选择保留筛选器，取消后保留草稿', async () => {
    const selectFolder = vi.fn().mockResolvedValueOnce(null).mockResolvedValueOnce('D:/folder')
    const selectFile = vi.fn().mockResolvedValueOnce([]).mockResolvedValueOnce(['D:/demo.exe'])
    vi.stubGlobal('window', { electronAPI: { selectFolder, selectFile } })
    const { pick, update } = await render(false, false)
    pick.get('core.edit.pickDirectory')!()
    pick.get('core.comp.pickFile')!()
    await nextTick()
    expect(update).not.toHaveBeenCalled()
    expect(selectFolder).toHaveBeenCalledOnce()
    expect(selectFile).toHaveBeenCalledWith([{ name: 'exe', extensions: ['exe'] }])
    pick.get('core.edit.pickDirectory')!()
    pick.get('core.comp.pickFile')!()
    await nextTick()
    expect(update.mock.calls).toEqual([
      ['alpha', 'missing_dir', 'D:/folder'],
      ['alpha', 'exe', 'D:/demo.exe'],
    ])
  })
  it('浏览器开发模式可以手动编辑和清空路径', async () => {
    vi.stubGlobal('window', { __AUTO_MAS_BROWSER_DEV_MODE__: true })
    const { html, pick, edit, update } = await render(false, false)
    expect(pick.has('core.comp.pickFile')).toBe(false)
    expect(pick.has('core.edit.pickDirectory')).toBe(false)
    expect(html.match(/<input\b[^>]*value="old.exe"[^>]*>/)?.[0]).not.toContain('readonly')
    edit.get('old.exe')!('new.exe')
    edit.get('old.exe')!('')
    expect(update.mock.calls).toEqual([
      ['alpha', 'exe', 'new.exe'],
      ['alpha', 'exe', null],
    ])
  })
  it('步骤保留同一编辑稿，错误定位到收起的表格，同 UID 重读保留展开选择', async () => {
    const draft = usePluginSettingsDraft()
    draft.reset({ Main: { Path: 'old' }, Run: { Count: 2 } }, { keepDraft: false })
    const uid = ref('uid')
    const groups = ref([
      { name: 'Main', hints: [{ field: 'Path' }] },
      { name: 'Run', hints: [{ field: 'Count' }] },
    ])
    const finish = vi.fn()
    const client = new QueryClient()
    const view = mountForm(
      () => ({
        uid: uid.value,
        namespace: 'demo',
        scope: 'script',
        groups: groups.value,
        values: draft.values,
        errors: draft.errors.value,
        steps: [
          { key: 'start', title: 'Ignored title' },
          { key: 'empty' },
          { key: 'run', title: 'Run options' },
        ],
        sections: {
          'group:Main': { collapsible: true, default_collapsed: true },
          'table:retries': { step: 'run', collapsible: true, default_collapsed: true },
        },
        tables: [{ key: 'retries', rows: ['Run'], columns: ['Count'] }],
        'onUpdate:value': draft.update,
        onFinish: finish,
      }),
      client
    )
    const click = (label: string) => fire(view.find('button', label)!, 'onClick')
    const toggle = () => view.all().find(node => 'aria-expanded' in node.props)!
    try {
      expect(view.find('steps')!.props.items).toMatchObject([
        { title: 'Translated start' },
        { title: 'Run options' },
      ])
      expect(toggle().props['aria-expanded']).toBe(false)
      await fire(toggle(), 'onClick')
      await fire(view.find('input')!, 'onUpdate:value', 'new')
      await click('core.edit.next')
      expect(toggle().props['aria-expanded']).toBe(false)
      await fire(toggle(), 'onClick')
      groups.value = [...groups.value]
      await nextTick()
      expect(toggle().props['aria-expanded']).toBe(true)
      await click('core.taskboard.complete')
      expect(finish).toHaveBeenCalledOnce()
      await fire(toggle(), 'onClick')
      await click('core.edit.previousStep')
      expect(toggle().props['aria-expanded']).toBe(true)
      expect(view.find('input')!.props.value).toBe('new')
      await requestApi(
        async () => ({ code: 422, fieldErrors: { 'Run.Count': 'invalid' } }),
        'save failed'
      ).catch(draft.saveFailed)
      await nextTick()
      expect(view.find('steps')!.props.current).toBe(1)
      expect(toggle().props['aria-expanded']).toBe(true)
      uid.value = 'other'
      await nextTick()
      expect(view.find('steps')!.props.current).toBe(0)
      await fire(view.find('steps')!, 'onUpdate:current', 1)
      expect(toggle().props['aria-expanded']).toBe(false)
    } finally {
      view.app.unmount()
      client.clear()
    }
  })

  it('级联查询只发送草稿里的可见依赖，迟到及失败的响应保留选择', async () => {
    const profile = {
      field: 'Profile',
      component: 'select',
      option_source: 'profiles',
      depends_on: {
        region: 'Setup.Region',
        limit: 'Setup.Limit',
        trial: 'Setup.Trial',
      },
    }
    const hints = [
      { field: 'Region' },
      { field: 'Limit' },
      { field: 'Trial' },
      profile,
      { field: 'Password', secret: true },
      { field: 'Token', masked: true },
      ...['Password', 'Token', 'Hidden'].map(field => ({
        field: 'By' + field,
        option_source: 'denied',
        depends_on: { q: 'Setup.' + field },
      })),
    ]
    const draft = reactive({
      Region: null as string | null,
      Limit: 0,
      Trial: false,
      Profile: 7 as number | boolean,
      Password: 'private',
      Token: 'masked',
      Hidden: 'hidden',
    })
    const pending = new Map<string, ReturnType<typeof deferred<AxiosResponse>>>()
    const urls: URL[] = []
    const http = vi.spyOn(axios, 'request').mockImplementation(config => {
      const url = new URL(config.url!, 'http://mas.test')
      urls.push(url)
      const response = deferred<AxiosResponse>()
      pending.set(url.searchParams.get('region')!, response)
      return response.promise
    })
    const complete = (region: string, values: Array<boolean | number>) =>
      pending.get(region)!.resolve({
        status: 200,
        data: { code: 200, data: values.map(value => ({ value })) },
      } as AxiosResponse)
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const invalid = vi.fn()
    const view = mountForm(
      () => ({
        uid: 'uid',
        namespace: 'demo',
        scope: 'script',
        pluginName: 'demo15',
        setupMode: true,
        groups: [{ name: 'Setup', hints }],
        values: { Setup: draft },
        'onUpdate:value': (_, field, value) => Object.assign(draft, { [field]: value }),
        'onUpdate:optionsInvalid': invalid,
      }),
      client
    )
    const region = (value: string) => fire(view.find('input')!, 'onUpdate:value', value)
    const submit = () => view.find('button', 'core.taskboard.complete')!
    try {
      await nextTick()
      expect(urls).toEqual([])
      await region('')
      await vi.waitFor(() => expect(pending.has('')).toBe(true))
      await region('B')
      await vi.waitFor(() => expect(pending.has('B')).toBe(true))
      expect(urls.map(url => [url.pathname, Object.fromEntries(url.searchParams)])).toEqual(
        ['', 'B'].map(region => [
          '/api/plugin/demo15/options/profiles',
          { region, limit: '0', trial: 'false', locale: 'en' },
        ])
      )
      expect(view.find('select')!.props.loading).toBe(true)
      expect(submit().props.disabled).toBe(true)
      complete('B', [true, 3, false])
      await vi.waitFor(() =>
        expect(view.find('p', 'core.plugins.optionUnavailable')?.props.role).toBe('alert')
      )
      expect(invalid).toHaveBeenLastCalledWith(true)
      expect(submit().props.disabled).toBe(true)
      expect(draft.Profile).toBe(7)
      await fire(view.find('select')!, 'onUpdate:value', true)
      complete('', [7])
      await vi.waitFor(() => expect(client.isFetching()).toBe(0))
      expect(view.find('select')!.props.options).toMatchObject([
        { value: true },
        { value: 3 },
        { value: false },
      ])
      expect(view.find('p', 'core.plugins.optionUnavailable')).toBeUndefined()
      expect(invalid).toHaveBeenLastCalledWith(false)
      expect(submit().props.disabled).toBe(false)
      await region('C')
      await vi.waitFor(() => expect(pending.has('C')).toBe(true))
      pending.get('C')!.reject(new Error('offline'))
      await vi.waitFor(() => expect(view.find('p', 'offline')?.props.role).toBe('alert'))
      expect(draft.Profile).toBe(true)
      expect(submit().props.disabled).toBe(true)
      const failed = pending.get('C')
      await fire(view.find('button', 'core.common.retry')!, 'onClick')
      await vi.waitFor(() => expect(pending.get('C')).not.toBe(failed))
      complete('C', [true])
      await vi.waitFor(() => expect(submit().props.disabled).toBe(false))
    } finally {
      view.app.unmount()
      client.clear()
      http.mockRestore()
    }
  })
  it.each([
    {
      transpose: false,
      headers: ['Name', 'note'],
      rows: [
        ['First', 'A1', 'A2'],
        ['beta', 'B1'],
      ],
    },
    {
      transpose: true,
      headers: ['First', 'beta'],
      rows: [
        ['Name', 'A1', 'B1'],
        ['note', 'A2'],
      ],
    },
  ])('转置=$transpose 时按展示坐标编辑同一个配置字段', async ({ transpose, headers, rows }) => {
    const { html, edit, update } = await render(transpose)
    const head = html.match(/<thead\b[^>]*>([\s\S]*?)<\/thead>/)![1]!
    expect(head).toMatch(new RegExp(headers.join('[\\s\\S]*')))
    const bodyRows = [...html.matchAll(/<tr\b[^>]*>([\s\S]*?)<\/tr>/g)].map(match => match[1]!)
    for (const row of rows) {
      expect(bodyRows.some(markup => new RegExp(row.join('[\\s\\S]*')).test(markup))).toBe(true)
    }
    expect(html).toContain('Matrix')
    expect(html.match(/value="B1"/g)).toHaveLength(1)
    expect(html).not.toContain('value="hidden"')
    expect(html).toContain('value="outside"')
    edit.get('B1')!('changed')
    expect(update).toHaveBeenCalledWith('beta', 'name', 'changed')
  })

  it('目录只计入实际渲染的卡片，表格字段与空表不重复占位', async () => {
    const three = await render(false)
    const nav = three.html.match(/<nav\b[^>]*>([\s\S]*?)<\/nav>/)![1]!
    const links = [...nav.matchAll(/href="#([^"]+)"/g)]
    expect(links).toHaveLength(3)
    for (const [, id] of links) expect(three.html).toContain(`id="${id}"`)
    expect(nav).toContain('Matrix')
    expect(nav).not.toContain('invisible')
    expect((await render(false, false)).html).not.toContain('<nav')
  })

  it('相邻与独立布尔字段均使用带标签的开关，保留字段顺序和反馈', async () => {
    const { html } = await render(false)
    const switches = html.match(/<button\b[^>]*role="switch"[^>]*>/g) ?? []
    const control = (label: string) =>
      switches.find(button => button.includes(`aria-label="${label}"`))
    expect(control('enabled')).toContain('aria-checked="true"')
    expect(control('locked')).toMatch(/\sdisabled(?:[\s>])/)
    expect(control('single')).toContain('aria-checked="false"')
    expect(html).toContain('aria-label="Check for updates before starting each new run."')
    expect(html).toMatch(
      /value="outside"[\s\S]*invalid switch[\s\S]*core.plugins.readOnly[\s\S]*ant-segmented[\s\S]*single[\s\S]*<textarea/
    )
    expect(html).toMatch(/exe[\s\S]*core.plugins.pathMustExistHint/)
    expect(html).toMatch(/missing_dir[\s\S]*role="alert"[^>]*>missing directory</)
  })

  it('常规与转置表格按可见列类型定宽，单元格使用紧凑控件', async () => {
    const { columns, html, numeric } = await render(false)
    expect(numeric).toMatchObject({ min: 0, step: 0.1 })
    expect(columns.map(({ width }) => width)).toEqual([108, undefined, undefined, 84, 116])
    expect(columns.find(column => column.key === 'on')?.align).toBe('center')
    const table = html.match(/<tbody\b[^>]*>([\s\S]*?)<\/tbody>/)![1]!
    expect(table).toContain('role="switch"')
    expect(table).toContain('ant-input-number')
    expect(table).not.toMatch(/ant-input(?:-number)?-lg/)
    expect((await render(true)).columns.map(({ width }) => width)).toEqual([
      108,
      undefined,
      undefined,
    ])
  })

  it('保存错误留在对应单元格，选项加载失败在普通字段内显示并可重试', async () => {
    const draft = usePluginSettingsDraft()
    await requestApi(
      async () => ({
        code: 422,
        message: 'invalid settings',
        fieldErrors: { 'beta.name': 'name already exists', 'alpha.extra': 'invalid extra' },
      }),
      'save failed'
    ).catch(draft.saveFailed)
    const { html } = await render(false, true, draft.errors.value)
    const cell = [...html.matchAll(/<td\b[^>]*>([\s\S]*?)<\/td>/g)].find(match =>
      match[1]!.includes('value="B1"')
    )
    expect(cell?.[1]).toMatch(/role="alert"[^>]*>name already exists</)
    const ordinary = html.slice(html.indexOf('</table>'))
    expect(ordinary).toMatch(/value="outside"[^<]*(?:<[^>]+>)*invalid extra</)
    expect(html).not.toContain('invalid settings')
    expect(ordinary).toMatch(
      /device[\s\S]*role="alert"[^>]*>options unavailable<[\s\S]*core.common.retry/
    )
  })

  it('同一表单的两种计划和未筛选计划各自请求并缓存选项', async () => {
    const endpoint = '/api/plugin/options/plans'
    const hints = [
      { field: 'first', endpoint, plan_type: 'FirstPlan' },
      { field: 'second', endpoint, plan_type: 'SecondPlan' },
      { field: 'all', endpoint },
    ]
    const request = vi.spyOn(Service, 'pluginPlanOptionsApiPluginOptionsPlansPost')
    const client = new QueryClient({
      defaultOptions: { queries: { enabled: false, retry: false } },
    })
    try {
      for (const label of ['first', 'second', 'all'])
        request.mockResolvedValueOnce({ code: 200, data: [{ value: label, label }] })
      const app = createSSRApp(
        defineComponent({
          async setup() {
            const target = computed(() => ({ uid: 'uid', ui: { hints: { plans: hints } } }))
            const { stateFor } = useDeclarativeOptions(target)
            const lists = await Promise.all(hints.map(hint => stateFor('plans', hint)!.execute()))
            return () => h('span', lists.map(list => list.data?.[0]?.label).join(','))
          },
        })
      )
      app.use(VueQueryPlugin, { queryClient: client })
      app.use(createI18n({ legacy: false, locale: 'en', missingWarn: false, fallbackWarn: false }))
      expect(await renderToString(app)).toContain('first,second,all')
      expect(request.mock.calls.map(([, body]) => body)).toEqual([
        { type: 'FirstPlan' },
        { type: 'SecondPlan' },
        undefined,
      ])
    } finally {
      request.mockRestore()
      client.clear()
    }
  })

  it('下拉动作携带分组和字段声明，走独立动作入口', async () => {
    const { action, selectAction, update } = await render(false)
    selectAction.get('Refresh now')!()
    expect(action).toHaveBeenCalledWith(
      'other',
      expect.objectContaining({ field: 'refresh', component: 'dropdown-button' }),
      'refresh'
    )
    expect(update).not.toHaveBeenCalled()
  })
})
