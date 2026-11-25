import { describe, expect, it, vi } from 'vite-plus/test'
import { createSSRApp, h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createI18n } from 'vue-i18n'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import Antd from 'ant-design-vue'
import { pluginSettingsTables } from '../pluginCenterModel'
import PluginDeclarativeForm from './PluginDeclarativeForm.vue'

/** 经插件表单进入真实 AntD 表格，用同一组数据验证表头、可见字段和编辑坐标。 */
async function render(transpose: boolean, includeOptionsGroup = true) {
  const update = vi.fn()
  const edit = new Map<string, (value: string) => void>()
  const groups = [
    {
      name: 'alpha',
      hints: [
        { field: 'name' },
        { field: 'note' },
        { field: 'on', component: 'bool' },
        { field: 'count', component: 'number' },
        { field: 'extra' },
        { field: 'enabled', component: 'switch' },
        { field: 'locked', component: 'checkbox', editable: false },
        { field: 'layout', component: 'boolean', widget: 'segmented', options: [{ value: false }] },
        { field: 'single', component: 'boolean' },
        { field: 'notes', widget: 'textarea' },
      ],
    },
    { name: 'beta', hints: [{ field: 'name' }] },
    {
      name: 'other',
      hints: [{ field: 'device', component: 'select', endpoint: '/api/plugin/options/games' }],
    },
  ]
  const values = {
    alpha: { name: 'A1', note: 'A2', extra: 'outside', on: true, count: 4, enabled: true },
    beta: { name: 'B1', note: 'hidden' },
  }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, enabled: false } } })
  await client.prefetchQuery({
    queryKey: ['plugins', 'field-options', 'uid', '/api/plugin/options/games', []],
    queryFn: () => Promise.reject(new Error('options unavailable')),
  })
  const app = createSSRApp(() =>
    h(PluginDeclarativeForm, {
      groups: includeOptionsGroup ? groups : groups.slice(0, 2),
      values,
      uid: 'uid',
      namespace: 'demo',
      tables: pluginSettingsTables({
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
      errors: { 'beta.name': 'save failed', 'alpha.enabled': 'invalid switch' },
      'onUpdate:value': update,
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
  let columns: Array<{ key: string; width?: number; align?: string }> = []
  app.mixin({
    created() {
      if (this.$options.name === 'ATable') columns = this.$props.columns
      if (this.$options.name === 'AInput') {
        edit.set(String(this.$props.value), value => this.$emit('update:value', value))
      }
    },
  })
  const html = await renderToString(app)
  client.clear()
  return { html, edit, update, columns }
}

describe('插件声明式表格与字段反馈', () => {
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

  it('只聚合连续开关，控件覆盖与孤立开关保留在普通栅格', async () => {
    const { html } = await render(false)
    expect(
      [...html.matchAll(/class="declarative-(field|switch)-grid"/g)].map(match => match[1])
    ).toEqual(['field', 'switch', 'field', 'field'])
    const grids = html.split(/class="declarative-(?:field|switch)-grid"/)
    expect(grids[1]).toContain('value="outside"')
    expect(grids[2]!.match(/role="switch"/g)).toHaveLength(2)
    expect(grids[2]).toContain('switch-tile--on')
    expect(grids[2]).toMatch(
      /enabled[\s\S]*invalid switch[\s\S]*locked[\s\S]*core.plugins.readOnly/
    )
    expect(grids[3]).toMatch(
      /ant-segmented[\s\S]*single[\s\S]*setting-toggle-button[\s\S]*textarea/
    )
  })

  it('常规与转置表格按可见列类型定宽，单元格使用紧凑控件', async () => {
    const { columns, html } = await render(false)
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
    const { html } = await render(false)
    const cell = [...html.matchAll(/<td\b[^>]*>([\s\S]*?)<\/td>/g)].find(match =>
      match[1]!.includes('value="B1"')
    )
    expect(cell?.[1]).toMatch(/role="alert"[^>]*>save failed</)
    const ordinary = html.slice(html.indexOf('</table>'))
    expect(ordinary).toMatch(
      /device[\s\S]*role="alert"[^>]*>options unavailable<[\s\S]*core.common.retry/
    )
  })
})
